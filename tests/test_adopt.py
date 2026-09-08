import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from cdforge.adopt import CONFLICT
from cdforge.adopt import UNCHANGED
from cdforge.adopt import apply_alignment
from cdforge.adopt import merge_gitignore
from cdforge.adopt import merge_settings_json
from cdforge.adopt import plan_alignment
from cdforge.cli import app
from cdforge.detect import detect_answers
from cdforge.manifest import read_manifest_answers
from cdforge.wizard import reselect_project_type

runner = CliRunner()

ANSWERS = {
    'project_name': 'Legacy Tool',
    'project_type': 'python_uv_tool',
    'package_import_name': 'legacy_tool',
    'cli_command_name': 'legacy',
    'author_name': 'Jane Doe',
    'author_email': 'jane@example.com',
}

ORIGINAL_README = '# Legacy Tool\n\nA pre-existing project.\n'
ORIGINAL_PYPROJECT = """[project]
name = "legacy-tool"
version = "0.3.0"
requires-python = ">=3.11"
authors = [{ name = "Jane Doe", email = "jane@example.com" }]
dependencies = ["typer>=0.15"]

[project.scripts]
legacy = "legacy_tool.cli:main"

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.8"]
"""


def make_legacy_project(tmp_path: Path, *, git: bool = False) -> Path:
    project_dir = tmp_path / 'legacy-tool'
    (project_dir / 'src' / 'legacy_tool').mkdir(parents=True)
    (project_dir / 'tests').mkdir()
    (project_dir / 'pyproject.toml').write_text(ORIGINAL_PYPROJECT)
    (project_dir / 'src' / 'legacy_tool' / '__init__.py').write_text("__version__ = '0.3.0'\n")
    (project_dir / 'src' / 'legacy_tool' / 'cli.py').write_text('def main():\n    pass\n')
    (project_dir / 'tests' / 'test_ok.py').write_text('def test_ok():\n    assert True\n')
    (project_dir / 'README.md').write_text(ORIGINAL_README)
    (project_dir / '.gitignore').write_text('.venv/\n__pycache__/\n')
    (project_dir / '.claude').mkdir()
    (project_dir / '.claude' / 'settings.json').write_text(
        json.dumps({'permissions': {'allow': ['Bash(ls)']}}, indent=2) + '\n'
    )
    if git:

        def run(*args: str) -> None:
            subprocess.run(['git', *args], cwd=project_dir, check=True, capture_output=True)

        run('init', '-q')
        run('config', 'user.name', 'Test')
        run('config', 'user.email', 'test@example.com')
        run('add', '-A')
        run('commit', '-q', '--no-verify', '-m', 'init')
    return project_dir


def _adopt(project_dir: Path) -> None:
    plan = plan_alignment(ANSWERS, project_dir)
    apply_alignment(plan, ANSWERS)


def test_adopt_adds_the_managed_sandbox_files(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)

    _adopt(project_dir)

    for relative in [
        '.devcontainer/devcontainer.json',
        '.devcontainer/Dockerfile',
        '.devcontainer/post-create.sh',
        '.devcontainer/claude-home/.gitkeep',
        '.claude/skills/project-governance/SKILL.md',
        '.claude/skills/python-uv-conventions/SKILL.md',
        '.githooks/pre-commit',
        '.githooks/pre-push',
        'CLAUDE.md',
        '.cdforge.json',
    ]:
        assert (project_dir / relative).exists(), f'missing {relative}'
    assert (project_dir / '.githooks' / 'pre-commit').stat().st_mode & 0o111


def test_adopt_never_rewrites_project_source_or_existing_documents(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)

    _adopt(project_dir)

    # Application code and packaging belong to the project, not to cdforge.
    assert (project_dir / 'pyproject.toml').read_text() == ORIGINAL_PYPROJECT
    assert (project_dir / 'src' / 'legacy_tool' / 'cli.py').read_text() == 'def main():\n    pass\n'
    assert not (project_dir / 'src' / 'legacy_tool' / '__init__.py').read_text().startswith('"""')
    # An existing README is reported as a conflict, never overwritten.
    assert (project_dir / 'README.md').read_text() == ORIGINAL_README


def test_adopt_reports_conflicts_and_can_write_suggestions(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)

    plan = plan_alignment(ANSWERS, project_dir)
    assert [change.relative_path for change in plan.conflicts] == ['README.md']

    apply_alignment(plan, ANSWERS, write_suggestions=True)
    suggestion = project_dir / 'README.md.cdforge-new'
    assert suggestion.exists()
    assert 'Legacy Tool' in suggestion.read_text()
    assert (project_dir / 'README.md').read_text() == ORIGINAL_README


def test_adopt_merges_gitignore_and_claude_settings(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)

    _adopt(project_dir)

    gitignore = (project_dir / '.gitignore').read_text()
    assert '.venv/' in gitignore
    assert '/.devcontainer/claude-home/' in gitignore

    settings = json.loads((project_dir / '.claude' / 'settings.json').read_text())
    assert 'Bash(ls)' in settings['permissions']['allow']
    assert 'Bash(git push)' in settings['permissions']['deny']


def test_adopt_is_idempotent(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)
    _adopt(project_dir)

    plan = plan_alignment(ANSWERS, project_dir)

    assert plan.writes == []
    assert all(change.action in (UNCHANGED, CONFLICT) for change in plan.changes)


def test_adopt_restores_a_managed_file_that_drifted(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)
    _adopt(project_dir)
    devcontainer = project_dir / '.devcontainer' / 'devcontainer.json'
    devcontainer.write_text('{ "name": "hand-edited" }\n')

    plan = plan_alignment(ANSWERS, project_dir)
    assert [
        change.action
        for change in plan.changes
        if change.relative_path.endswith('devcontainer.json')
    ] == ['update']

    apply_alignment(plan, ANSWERS)
    assert json.loads(devcontainer.read_text())['name'] == 'Legacy Tool'


def test_adopt_records_answers_for_later_runs(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)

    _adopt(project_dir)

    assert read_manifest_answers(project_dir) == ANSWERS


def test_cli_adopt_dry_run_writes_nothing(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)

    result = runner.invoke(app, ['adopt', str(project_dir), '--non-interactive', '--dry-run'])

    assert result.exit_code == 0, result.output
    assert 'create' in result.output
    assert not (project_dir / '.devcontainer').exists()
    assert not (project_dir / '.cdforge.json').exists()


def test_cli_adopt_non_interactive_uses_detected_answers(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)

    result = runner.invoke(app, ['adopt', str(project_dir), '--non-interactive'])

    assert result.exit_code == 0, result.output
    assert (project_dir / '.devcontainer' / 'devcontainer.json').exists()
    answers = read_manifest_answers(project_dir)
    assert answers['project_type'] == 'python_uv_tool'
    assert answers['package_import_name'] == 'legacy_tool'


def test_cli_adopt_type_flag_overrides_the_detected_type(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)

    result = runner.invoke(
        app, ['adopt', str(project_dir), '--non-interactive', '--type', 'generic']
    )

    assert result.exit_code == 0, result.output
    answers = read_manifest_answers(project_dir)
    assert answers['project_type'] == 'generic'


def test_cli_adopt_type_flag_rejects_an_unknown_type(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path)

    result = runner.invoke(app, ['adopt', str(project_dir), '--non-interactive', '--type', 'rust'])

    assert result.exit_code == 1
    assert 'Unknown project type' in result.output
    assert not (project_dir / '.devcontainer').exists()


def test_cli_adopt_non_interactive_type_flag_overrides_the_recorded_manifest(
    tmp_path: Path,
) -> None:
    project_dir = make_legacy_project(tmp_path)
    _adopt(project_dir)
    assert read_manifest_answers(project_dir)['project_type'] == 'python_uv_tool'

    result = runner.invoke(
        app, ['adopt', str(project_dir), '--non-interactive', '--type', 'generic']
    )

    assert result.exit_code == 0, result.output
    assert read_manifest_answers(project_dir)['project_type'] == 'generic'


def test_cli_adopt_refuses_a_dirty_worktree_unless_forced(tmp_path: Path) -> None:
    project_dir = make_legacy_project(tmp_path, git=True)
    (project_dir / 'README.md').write_text('# changed\n')

    result = runner.invoke(app, ['adopt', str(project_dir), '--non-interactive'])
    assert result.exit_code == 1
    assert not (project_dir / '.devcontainer').exists()

    forced = runner.invoke(app, ['adopt', str(project_dir), '--non-interactive', '--force'])
    assert forced.exit_code == 0, forced.output
    assert (project_dir / '.devcontainer' / 'devcontainer.json').exists()


def test_cli_adopt_fails_on_a_missing_directory(tmp_path: Path) -> None:
    result = runner.invoke(app, ['adopt', str(tmp_path / 'nope'), '--non-interactive'])

    assert result.exit_code == 1


def test_reselect_project_type_unchanged_type_returns_the_recorded_answers() -> None:
    recorded = {'project_name': 'Legacy Tool', 'project_type': 'python_uv_tool', 'x': 1}

    assert reselect_project_type(recorded, forced_type='python_uv_tool') is recorded


def test_reselect_project_type_forced_switch_keeps_common_answers_and_re_asks_the_type() -> None:
    recorded = {
        'project_name': 'Legacy Tool',
        'git_remote_url': 'git@example.com:me/legacy.git',
        'project_type': 'python_uv_tool',
        'gpu_enabled': True,
        'docker_mode': 'sysbox',
        'network_firewall': 'allowlist',
        'package_import_name': 'legacy_tool',
        'cli_command_name': 'legacy',
    }

    switched = reselect_project_type(
        recorded, {'python_version': '3.12'}, forced_type='data_science'
    )

    assert switched['project_type'] == 'data_science'
    for key in ('project_name', 'git_remote_url', 'gpu_enabled', 'docker_mode', 'network_firewall'):
        assert switched[key] == recorded[key]
    # python_uv_tool's own answers are dropped; data_science's are filled in.
    assert 'cli_command_name' not in switched
    assert switched['ml_stack'] == 'analysis'
    assert switched['python_version'] == '3.12'


def test_detect_answers_recognises_a_django_project(tmp_path: Path) -> None:
    project_dir = tmp_path / 'shop'
    (project_dir / 'shop_config').mkdir(parents=True)
    (project_dir / 'apps' / 'catalog').mkdir(parents=True)
    (project_dir / 'shop_config' / 'settings.py').write_text('DEBUG = True\n')
    (project_dir / 'apps' / 'catalog' / 'apps.py').write_text('class Config:\n    pass\n')
    (project_dir / 'manage.py').write_text('# manage\n')
    (project_dir / 'pyproject.toml').write_text(
        '[project]\nname = "shop"\ndependencies = ["django", "psycopg[binary]", "celery"]\n'
    )

    detected = detect_answers(project_dir)

    assert detected['project_type'] == 'django_drf'
    assert detected['django_project_slug'] == 'shop_config'
    assert detected['initial_app_name'] == 'catalog'
    assert detected['database'] == 'postgres'
    assert detected['include_celery'] is True


def test_detect_answers_recognises_a_notebook_project(tmp_path: Path) -> None:
    project_dir = tmp_path / 'lab'
    (project_dir / 'notebooks').mkdir(parents=True)
    (project_dir / 'src' / 'lab').mkdir(parents=True)
    (project_dir / 'src' / 'lab' / '__init__.py').write_text('')
    (project_dir / 'notebooks' / '01-explore.ipynb').write_text('{"cells": []}\n')
    (project_dir / 'pyproject.toml').write_text(
        '[project]\nname = "lab"\nrequires-python = ">=3.12"\n'
        'dependencies = ["pandas", "torch", "transformers", "wandb"]\n'
    )

    detected = detect_answers(project_dir)

    assert detected['project_type'] == 'data_science'
    assert detected['package_import_name'] == 'lab'
    assert detected['python_version'] == '3.12'
    assert detected['ml_stack'] == 'transformers'
    # No CPU-only index pinned, so the default (CUDA) wheels are what this project uses.
    assert detected['compute_target'] == 'cuda'
    assert detected['experiment_tracking'] == 'wandb'


def test_detect_answers_recognises_an_angular_project(tmp_path: Path) -> None:
    project_dir = tmp_path / 'webapp'
    project_dir.mkdir()
    (project_dir / 'package.json').write_text(
        '{\n'
        '  "name": "web-app",\n'
        '  "license": "Apache-2.0",\n'
        '  "author": "Jane Dev <jane@example.com>",\n'
        '  "engines": {"node": ">=20.0.0"},\n'
        '  "dependencies": {"@angular/core": "^20.0.0"},\n'
        '  "devDependencies": {"@angular/cli": "^20.0.0", "eslint": "^9.0.0"}\n'
        '}\n'
    )
    (project_dir / 'angular.json').write_text('{"projects": {"web-app": {}}}\n')

    detected = detect_answers(project_dir)

    assert detected['project_type'] == 'angular'
    assert detected['app_name'] == 'web-app'
    assert detected['node_version'] == '20'
    assert detected['license_id'] == 'Apache-2.0'
    assert detected['author_name'] == 'Jane Dev'
    assert detected['author_email'] == 'jane@example.com'


def test_detect_answers_does_not_mistake_a_cli_tool_for_a_notebook_project(tmp_path: Path) -> None:
    project_dir = tmp_path / 'tool'
    (project_dir / 'src' / 'tool').mkdir(parents=True)
    (project_dir / 'src' / 'tool' / '__init__.py').write_text('')
    (project_dir / 'pyproject.toml').write_text(
        '[project]\nname = "tool"\ndependencies = ["typer", "pandas"]\n'
    )

    detected = detect_answers(project_dir)

    assert detected['project_type'] == 'python_uv_tool'


def test_merge_helpers_keep_existing_content() -> None:
    merged = merge_gitignore('.venv/\n', '# comment\n.venv/\ndist/\n')
    assert merged.splitlines()[0] == '.venv/'
    assert 'dist/' in merged

    settings = merge_settings_json('{"permissions": {"deny": ["Bash(rm)"]}}', '{"a": 1}')
    assert settings is not None
    assert json.loads(settings) == {'permissions': {'deny': ['Bash(rm)']}, 'a': 1}
    assert merge_settings_json('not json', '{}') is None


DJANGO_ANSWERS = {
    'project_name': 'Shop',
    'project_type': 'django_drf',
    'django_project_slug': 'shop_config',
    'initial_app_name': 'catalog',
    'database': 'postgres',
    'auth_method': 'simplejwt',
    'include_celery': False,
    'api_docs': 'drf-spectacular',
    'author_name': 'Jane Doe',
    'author_email': 'jane@example.com',
    # Postgres is now run from inside the devcontainer, which requires in-container Docker.
    'docker_mode': 'sysbox',
}

OWN_COMPOSE = 'services:\n  web:\n    image: mine\n'


def make_django_project(tmp_path: Path, *, compose: str | None = None) -> Path:
    project_dir = tmp_path / 'shop'
    (project_dir / 'shop_config').mkdir(parents=True)
    (project_dir / 'shop_config' / 'settings.py').write_text('DEBUG = True\n')
    (project_dir / 'manage.py').write_text('# manage\n')
    (project_dir / 'pyproject.toml').write_text(
        '[project]\nname = "shop"\ndependencies = ["django", "psycopg[binary]"]\n'
        '[dependency-groups]\ndev = ["pytest", "ruff"]\n'
    )
    if compose is not None:
        (project_dir / 'docker-compose.yml').write_text(compose)
    return project_dir


def _devcontainer_config(project_dir: Path):
    return json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())


def test_adopt_never_wires_compose_into_the_devcontainer(tmp_path: Path) -> None:
    project_dir = make_django_project(tmp_path, compose=OWN_COMPOSE)

    plan = plan_alignment(DJANGO_ANSWERS, project_dir)
    apply_alignment(plan, DJANGO_ANSWERS)

    # The devcontainer is always the plain single-container layout; it never loads a compose
    # file, and adopt never writes one into .devcontainer/.
    config = _devcontainer_config(project_dir)
    assert config['build'] == {'dockerfile': 'Dockerfile'}
    assert 'dockerComposeFile' not in config
    assert not (project_dir / '.devcontainer' / 'docker-compose.cdforge.yml').exists()

    # The project's own docker-compose.yml is create-only: left untouched, flagged as a
    # conflict (cdforge would otherwise ship its own db/redis-only file there).
    assert (project_dir / 'docker-compose.yml').read_text() == OWN_COMPOSE
    assert [c.relative_path for c in plan.conflicts] == ['docker-compose.yml']


def test_adopt_creates_a_backing_services_compose_file_when_the_project_has_none(
    tmp_path: Path,
) -> None:
    project_dir = make_django_project(tmp_path)

    plan = plan_alignment(DJANGO_ANSWERS, project_dir)
    apply_alignment(plan, DJANGO_ANSWERS)

    compose = (project_dir / 'docker-compose.yml').read_text()
    assert 'app:' not in compose
    assert 'postgres:16' in compose
    assert not (project_dir / '.devcontainer' / 'docker-compose.cdforge.yml').exists()
    assert 'dockerComposeFile' not in _devcontainer_config(project_dir)

    # Idempotent: a second pass has nothing to write.
    assert plan_alignment(DJANGO_ANSWERS, project_dir).writes == []
