from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from cdforge.answers import validate_common_answers
from cdforge.context_builder import build_context
from cdforge.git_ops import init_repository
from cdforge.manifest import write_manifest
from cdforge.project_types.registry import get_project_type
from cdforge.renderer import render_project
from cdforge.skills_catalog import get_optional_skill


class ScaffoldError(RuntimeError):
    pass


def _format_python_files(output_dir: Path) -> None:
    """Best-effort formatting pass so the initial commit is already canonically
    formatted; harmless to skip when ruff isn't reachable on the host."""
    try:
        subprocess.run(
            ['uvx', 'ruff', 'format', '--quiet', str(output_dir)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def scaffold_project(
    answers: dict[str, Any],
    output_dir: Path,
    *,
    force: bool = False,
) -> Path:
    validate_common_answers(answers)
    project_type = get_project_type(answers['project_type'])

    if output_dir.exists() and any(output_dir.iterdir()) and not force:
        raise ScaffoldError(f'{output_dir} already exists and is not empty')

    optional_skill_ids: list[str] = list(answers.get('optional_skills', []))
    optional_skill_dirs = [get_optional_skill(sid).template_dir for sid in optional_skill_ids]

    context = build_context(answers, project_type, optional_skill_ids)
    render_project(project_type, context, output_dir, optional_skill_dirs)

    claude_home = output_dir / '.devcontainer' / 'claude-home'
    claude_home.mkdir(parents=True, exist_ok=True)
    (claude_home / '.gitkeep').write_text('', encoding='utf-8')

    write_manifest(output_dir, answers)

    _format_python_files(output_dir)

    init_repository(
        output_dir,
        answers.get('git_remote_url', ''),
        author_name=context.get('author_name', 'Project Scaffold'),
        author_email=context.get('author_email', 'scaffold@localhost'),
    )
    return output_dir
