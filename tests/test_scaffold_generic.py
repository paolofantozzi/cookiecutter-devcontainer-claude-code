import json
import subprocess
from pathlib import Path

from cdforge.answers import load_answers_file
from cdforge.scaffold import scaffold_project

FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_generic.json'


def _scaffold(tmp_path: Path) -> Path:
    answers = load_answers_file(FIXTURE)
    return scaffold_project(answers, tmp_path / 'scratch-space')


def test_expected_files_are_created(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    for relative in [
        '.devcontainer/devcontainer.json',
        '.devcontainer/Dockerfile',
        '.devcontainer/post-create.sh',
        '.devcontainer/claude-home/.gitkeep',
        '.claude/settings.json',
        '.claude/skills/project-governance/SKILL.md',
        '.githooks/pre-commit',
        '.githooks/pre-push',
        '.gitignore',
        'CLAUDE.md',
        'README.md',
        'CHANGELOG.md',
        'pyproject.toml',
        'docs/.gitkeep',
        'tests/.gitkeep',
    ]:
        assert (project_dir / relative).exists(), f'missing {relative}'


def test_workspace_is_deliberately_empty(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    # No package, no CLI, no license file: this type ships almost nothing on purpose.
    assert not (project_dir / 'src').exists()
    assert not (project_dir / 'LICENSE').exists()


def test_pyproject_is_a_non_package_uv_project(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    pyproject = (project_dir / 'pyproject.toml').read_text()

    assert 'name = "scratch-space"' in pyproject
    assert 'package = false' in pyproject
    # Nothing to build - the bare workspace must not declare a build backend.
    assert '\n[build-system]' not in pyproject
    assert 'quote-style = "single"' in pyproject
    assert 'force-single-line = true' in pyproject


def test_precommit_hook_tolerates_an_empty_test_suite(tmp_path: Path) -> None:
    # A documents-only workspace has no tests; pytest's "no tests collected" exit status
    # (5) must not block a commit, while a real failure still does.
    project_dir = _scaffold(tmp_path)

    hook = (project_dir / '.githooks' / 'pre-commit').read_text()

    assert 'uv run pytest || [ "$?" -eq 5 ]' in hook


def test_devcontainer_stays_unprivileged(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']
    assert 'ghcr.io/anthropics/devcontainer-features/claude-code:1.0' in config['features']
    assert config['build'] == {'dockerfile': 'Dockerfile'}
    assert 'runArgs' not in config


def test_git_repository_is_initialized_with_one_clean_commit(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    log = subprocess.run(
        ['git', 'log', '--oneline'], cwd=project_dir, capture_output=True, text=True, check=True
    )
    status = subprocess.run(
        ['git', 'status', '--porcelain'],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=True,
    )

    assert len(log.stdout.strip().splitlines()) == 1
    assert status.stdout.strip() == ''
