from __future__ import annotations

import json
import stat
import tempfile
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

from cdforge.answers import validate_common_answers
from cdforge.context_builder import build_context
from cdforge.git_ops import configure_hooks_path
from cdforge.git_ops import is_git_repository
from cdforge.git_ops import tracked_changes
from cdforge.manifest import write_manifest
from cdforge.project_types.registry import get_project_type
from cdforge.renderer import render_project
from cdforge.skills_catalog import get_optional_skill

SUGGESTION_SUFFIX = '.cdforge-new'

# How each generated file is treated when the target project already exists.
#
# MANAGED: files that *define* the sandbox and the workflow cdforge guarantees
#   (devcontainer, Dockerfile, hooks, skills). Aligning a project means these become
#   exactly what cdforge generates, so they are overwritten.
# MERGED: files that are cdforge's *and* the project's (gitignore, Claude settings).
#   cdforge's entries are added, existing ones are never removed.
# CREATE_ONLY: documents whose content belongs to the project (README, CLAUDE.md,
#   CHANGELOG, LICENSE, docker-compose.yml). Written only when missing; otherwise
#   reported as a conflict and left untouched.
# Everything else is application source code (src/, apps/, pyproject.toml, ...) and is
# never written into an existing project.
MANAGED_PREFIXES = ('.devcontainer/', '.githooks/', '.claude/')
MERGED_FILES = ('.gitignore', '.claude/settings.json')
CREATE_ONLY_FILES = (
    'CLAUDE.md',
    'README.md',
    'CHANGELOG.md',
    'LICENSE',
    'docker-compose.yml',
    '.env.example',
)

MANAGED = 'managed'
MERGED = 'merged'
CREATE_ONLY = 'create-only'
PROJECT_OWNED = 'project-owned'

CREATE = 'create'
UPDATE = 'update'
MERGE = 'merge'
UNCHANGED = 'unchanged'
CONFLICT = 'conflict'


class AdoptError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlannedChange:
    relative_path: str
    category: str
    action: str
    content: str
    executable: bool = False


@dataclass
class AlignmentPlan:
    project_dir: Path
    project_type_id: str
    changes: list[PlannedChange] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def by_action(self, action: str) -> list[PlannedChange]:
        return [change for change in self.changes if change.action == action]

    @property
    def writes(self) -> list[PlannedChange]:
        return [change for change in self.changes if change.action in (CREATE, UPDATE, MERGE)]

    @property
    def conflicts(self) -> list[PlannedChange]:
        return self.by_action(CONFLICT)


def classify(relative_path: str) -> str:
    if relative_path in MERGED_FILES:
        return MERGED
    if relative_path.startswith(MANAGED_PREFIXES):
        return MANAGED
    if relative_path in CREATE_ONLY_FILES:
        return CREATE_ONLY
    return PROJECT_OWNED


def merge_gitignore(existing: str, rendered: str) -> str:
    """Append the cdforge entries the project does not already ignore, keeping every
    line the project had."""
    present = {line.strip() for line in existing.splitlines()}
    missing: list[str] = []
    for line in rendered.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or stripped in present:
            continue
        present.add(stripped)
        missing.append(stripped)
    if not missing:
        return existing
    prefix = existing if existing.endswith('\n') else existing + '\n'
    block = '\n'.join(missing)
    return f'{prefix}\n# --- added by cdforge ---\n{block}\n'


def _merge_json_value(existing: Any, rendered: Any) -> Any:
    if isinstance(existing, dict) and isinstance(rendered, dict):
        merged = dict(existing)
        for key, value in rendered.items():
            merged[key] = _merge_json_value(existing.get(key), value) if key in existing else value
        return merged
    if isinstance(existing, list) and isinstance(rendered, list):
        merged = list(existing)
        merged += [item for item in rendered if item not in merged]
        return merged
    # A scalar the project already set wins: cdforge only fills in what is missing.
    return existing if existing is not None else rendered


def merge_settings_json(existing: str, rendered: str) -> str | None:
    """Deep-merge cdforge's Claude settings into the project's own. Returns None when
    the existing file cannot be parsed, so the caller can report a conflict."""
    try:
        existing_data = json.loads(existing)
        rendered_data = json.loads(rendered)
    except json.JSONDecodeError:
        return None
    merged = _merge_json_value(existing_data, rendered_data)
    return json.dumps(merged, indent=2) + '\n'


def _merged_content(relative_path: str, existing: str, rendered: str) -> str | None:
    if relative_path == '.gitignore':
        return merge_gitignore(existing, rendered)
    return merge_settings_json(existing, rendered)


def _render_to_dict(answers: dict[str, Any]) -> dict[str, tuple[str, bool]]:
    """Render a full project into a temporary directory and return
    {relative path: (content, is executable)}."""
    project_type = get_project_type(answers['project_type'])
    optional_skill_ids: list[str] = list(answers.get('optional_skills', []))
    optional_skill_dirs = [get_optional_skill(sid).template_dir for sid in optional_skill_ids]
    context = build_context(answers, project_type, optional_skill_ids)

    rendered: dict[str, tuple[str, bool]] = {}
    with tempfile.TemporaryDirectory(prefix='cdforge-render-') as tmp:
        tmp_root = Path(tmp)
        for path in render_project(project_type, context, tmp_root, optional_skill_dirs):
            relative = path.relative_to(tmp_root).as_posix()
            rendered[relative] = (
                path.read_text(encoding='utf-8'),
                bool(path.stat().st_mode & stat.S_IXUSR),
            )
    return rendered


def _database_notes(project_dir: Path, database: str) -> list[str]:
    """A server database is wired through `DATABASE_URL` and a driver dependency; warn when
    the adopted project declares no driver (we never rewrite its pyproject.toml)."""
    if database not in ('postgres', 'mariadb'):
        return []
    pyproject = project_dir / 'pyproject.toml'
    text = pyproject.read_text(encoding='utf-8').lower() if pyproject.exists() else ''
    driver = 'psycopg' if database == 'postgres' else 'mysqlclient'
    if driver in text:
        return []
    return [
        f"database='{database}' expects the `{driver}` driver in pyproject.toml and a "
        '`DATABASE_URL` pointing at the `db` service in the generated docker-compose.yml; '
        'add the driver with `uv add` (adoption never edits pyproject.toml).'
    ]


def _tooling_notes(project_dir: Path, project_type_id: str) -> list[str]:
    """The generated pre-commit hook runs the project's linter and test suite; warn when
    the adopted project does not declare the tools it needs (we never rewrite its
    pyproject.toml / package.json)."""
    if project_type_id == 'static_site':
        # A plain static site has no linter or test suite; the pre-commit hook only checks
        # that an entry point exists, which needs nothing installed.
        return []
    if project_type_id == 'angular':
        package_json = project_dir / 'package.json'
        if not package_json.exists():
            return [
                'No package.json found: the .githooks/pre-commit hook runs `npm run lint` '
                'and `npm test`, which need an npm project with an Angular CLI setup.'
            ]
        text = package_json.read_text(encoding='utf-8').lower()
        missing = [tool for tool in ('eslint', '@angular/cli') if tool not in text]
        if missing:
            return [
                f'package.json does not mention {" or ".join(missing)}: the generated '
                '.githooks/pre-commit hook runs `npm run lint` / `npm test` and will fail '
                'until the Angular CLI and ESLint are added as devDependencies.'
            ]
        return []

    pyproject = project_dir / 'pyproject.toml'
    if not pyproject.exists():
        return [
            'No pyproject.toml found: the .githooks/pre-commit hook runs '
            '`uv run ruff check .` and `uv run pytest`, which need a uv-managed project.'
        ]
    text = pyproject.read_text(encoding='utf-8').lower()
    missing = [tool for tool in ('ruff', 'pytest') if tool not in text]
    if missing:
        return [
            f'pyproject.toml does not mention {" or ".join(missing)}: the generated '
            '.githooks/pre-commit hook runs them via uv and will fail until they are '
            'added as dev dependencies.'
        ]
    return []


def plan_alignment(answers: dict[str, Any], project_dir: Path) -> AlignmentPlan:
    """Compute, without touching the project, what aligning it with cdforge would do."""
    validate_common_answers(answers)
    if not project_dir.is_dir():
        raise AdoptError(f'{project_dir} is not an existing directory')

    plan = AlignmentPlan(project_dir=project_dir, project_type_id=answers['project_type'])
    rendered = _render_to_dict(answers)
    for relative, (content, executable) in sorted(rendered.items()):
        category = classify(relative)
        if category == PROJECT_OWNED:
            continue
        target = project_dir / relative
        if not target.exists():
            plan.changes.append(PlannedChange(relative, category, CREATE, content, executable))
            continue

        existing = target.read_text(encoding='utf-8')
        if category == MANAGED:
            action = UNCHANGED if existing == content else UPDATE
            plan.changes.append(PlannedChange(relative, category, action, content, executable))
        elif category == MERGED:
            merged = _merged_content(relative, existing, content)
            if merged is None:
                plan.changes.append(
                    PlannedChange(relative, category, CONFLICT, content, executable)
                )
            else:
                action = UNCHANGED if merged == existing else MERGE
                plan.changes.append(PlannedChange(relative, category, action, merged, executable))
        else:
            action = UNCHANGED if existing == content else CONFLICT
            plan.changes.append(PlannedChange(relative, category, action, content, executable))

    plan.notes = _tooling_notes(project_dir, answers['project_type'])
    plan.notes += _database_notes(project_dir, answers.get('database', 'none'))
    return plan


def _write(target: Path, content: str, executable: bool) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    if executable:
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def apply_alignment(
    plan: AlignmentPlan,
    answers: dict[str, Any],
    *,
    write_suggestions: bool = False,
) -> list[Path]:
    """Write the planned changes. Conflicting files are never overwritten; with
    write_suggestions they are written next to the original as `<name>.cdforge-new`."""
    written: list[Path] = []
    for change in plan.changes:
        target = plan.project_dir / change.relative_path
        if change.action in (CREATE, UPDATE, MERGE):
            _write(target, change.content, change.executable)
            written.append(target)
        elif change.action == CONFLICT and write_suggestions:
            suggestion = target.with_name(target.name + SUGGESTION_SUFFIX)
            _write(suggestion, change.content, change.executable)
            written.append(suggestion)

    claude_home = plan.project_dir / '.devcontainer' / 'claude-home'
    claude_home.mkdir(parents=True, exist_ok=True)
    gitkeep = claude_home / '.gitkeep'
    if not gitkeep.exists():
        gitkeep.write_text('', encoding='utf-8')
        written.append(gitkeep)

    if is_git_repository(plan.project_dir):
        configure_hooks_path(plan.project_dir)

    written.append(write_manifest(plan.project_dir, answers))
    return written


def dirty_tracked_files(project_dir: Path) -> list[str]:
    """Tracked files with uncommitted changes: aligning overwrites managed files, so
    the caller refuses to run over work that git could not restore."""
    if not is_git_repository(project_dir):
        return []
    return tracked_changes(project_dir)
