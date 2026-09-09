import json
import subprocess
from pathlib import Path

from cdforge.answers import load_answers_file
from cdforge.scaffold import scaffold_project

FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_static_site.json'


def _scaffold(tmp_path: Path) -> Path:
    answers = load_answers_file(FIXTURE)
    return scaffold_project(answers, tmp_path / 'marketing-site')


def test_expected_files_are_created(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    for relative in [
        '.devcontainer/devcontainer.json',
        '.devcontainer/Dockerfile',
        '.devcontainer/post-create.sh',
        '.devcontainer/claude-home/.gitkeep',
        '.claude/settings.json',
        '.claude/skills/project-governance/SKILL.md',
        '.claude/skills/static-site-conventions/SKILL.md',
        '.githooks/pre-commit',
        '.githooks/pre-push',
        '.gitignore',
        'CLAUDE.md',
        'README.md',
        'CHANGELOG.md',
        'LICENSE',
        'index.html',
        '404.html',
        'styles.css',
        'main.js',
        'assets/favicon.svg',
    ]:
        assert (project_dir / relative).exists(), f'missing {relative}'

    # No toolchain: neither a Python nor a Node manifest is generated.
    assert not (project_dir / 'pyproject.toml').exists()
    assert not (project_dir / 'package.json').exists()


def test_index_html_carries_the_project_name(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    index = (project_dir / 'index.html').read_text()

    assert '<title>Marketing Site</title>' in index
    assert 'styles.css' in index
    assert 'assets/favicon.svg' in index


def test_precommit_hook_runs_no_linter_or_test_suite(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    hook = (project_dir / '.githooks' / 'pre-commit').read_text()

    assert 'index.html' in hook
    assert 'ruff' not in hook
    assert 'uv run' not in hook
    assert 'npm ' not in hook


def test_post_create_installs_nothing(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    post_create = (project_dir / '.devcontainer' / 'post-create.sh').read_text()

    assert 'uv sync' not in post_create
    assert 'npm install' not in post_create


def test_dockerfile_has_no_language_toolchain(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    dockerfile = (project_dir / '.devcontainer' / 'Dockerfile').read_text()

    assert 'astral-sh/uv' not in dockerfile
    assert 'npm' not in dockerfile


def test_gitignore_has_no_python_or_node_block(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    gitignore = (project_dir / '.gitignore').read_text()

    assert '.venv/' not in gitignore
    assert '.ruff_cache/' not in gitignore
    assert 'node_modules/' not in gitignore
    # The claude-home bind mount is still ignored.
    assert '/.devcontainer/claude-home/' in gitignore


def test_devcontainer_forwards_the_preview_port(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert config['forwardPorts'] == [8000]
    assert config['remoteUser'] == 'vscode'
    assert 'runArgs' not in config
    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']


def test_claude_md_describes_a_no_build_static_site(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    claude_md = (project_dir / 'CLAUDE.md').read_text()

    assert 'no build step' in claude_md.lower()
    assert 'python3 -m http.server' in claude_md


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
