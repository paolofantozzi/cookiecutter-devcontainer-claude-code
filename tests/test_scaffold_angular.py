import json
import subprocess
from pathlib import Path

from cdforge.answers import load_answers_file
from cdforge.scaffold import scaffold_project

FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_angular.json'


def _scaffold(tmp_path: Path) -> Path:
    answers = load_answers_file(FIXTURE)
    return scaffold_project(answers, tmp_path / 'dashboard-ui')


def test_expected_files_are_created(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    for relative in [
        '.devcontainer/devcontainer.json',
        '.devcontainer/Dockerfile',
        '.devcontainer/post-create.sh',
        '.devcontainer/claude-home/.gitkeep',
        '.claude/settings.json',
        '.claude/skills/project-governance/SKILL.md',
        '.claude/skills/angular-conventions/SKILL.md',
        '.githooks/pre-commit',
        '.githooks/pre-push',
        '.gitignore',
        'CLAUDE.md',
        'README.md',
        'CHANGELOG.md',
        'LICENSE',
        'package.json',
        'angular.json',
        'karma.conf.js',
        'eslint.config.js',
        '.prettierrc.json',
        'tsconfig.json',
        'tsconfig.app.json',
        'tsconfig.spec.json',
        'src/main.ts',
        'src/index.html',
        'src/styles.scss',
        'src/app/app.component.ts',
        'src/app/app.component.html',
        'src/app/app.component.spec.ts',
        'src/app/app.config.ts',
        'src/app/app.routes.ts',
    ]:
        assert (project_dir / relative).exists(), f'missing {relative}'

    # This is a Node project: no Python manifest is generated.
    assert not (project_dir / 'pyproject.toml').exists()


def test_package_json_carries_the_answers(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    package = json.loads((project_dir / 'package.json').read_text())

    assert package['name'] == 'dashboard-ui'
    assert package['engines']['node'] == '>=22.0.0'
    assert package['license'] == 'MIT'
    assert '@angular/core' in package['dependencies']
    assert '@angular/cli' in package['devDependencies']
    assert package['scripts']['lint'] == 'ng lint'


def test_precommit_hook_runs_npm_not_ruff(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    hook = (project_dir / '.githooks' / 'pre-commit').read_text()

    assert 'npm run lint' in hook
    assert 'npm test -- --watch=false' in hook
    assert 'ruff' not in hook
    assert 'uv run' not in hook


def test_post_create_installs_node_dependencies(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    post_create = (project_dir / '.devcontainer' / 'post-create.sh').read_text()

    assert 'npm install' in post_create
    assert 'uv sync' not in post_create


def test_dockerfile_installs_chromium_for_headless_karma(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    dockerfile = (project_dir / '.devcontainer' / 'Dockerfile').read_text()

    assert 'chromium' in dockerfile
    assert 'CHROME_BIN=/usr/bin/chromium' in dockerfile
    assert 'astral-sh/uv' not in dockerfile


def test_gitignore_targets_the_node_toolchain(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    gitignore = (project_dir / '.gitignore').read_text()

    assert 'node_modules/' in gitignore
    assert '.angular/' in gitignore
    # The Python block must not leak into a Node project.
    assert '.venv/' not in gitignore
    assert '.ruff_cache/' not in gitignore


def test_devcontainer_stays_unprivileged(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']
    assert 'ghcr.io/anthropics/devcontainer-features/claude-code:1.0' in config['features']
    assert config['build'] == {'dockerfile': 'Dockerfile'}
    assert config['remoteUser'] == 'node'
    assert config['forwardPorts'] == [4200]
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
