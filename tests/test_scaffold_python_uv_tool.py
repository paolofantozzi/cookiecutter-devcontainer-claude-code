import json
import subprocess
from pathlib import Path

from cdforge.answers import load_answers_file
from cdforge.scaffold import scaffold_project

FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_python_uv_tool.json'


def _scaffold(tmp_path: Path) -> Path:
    answers = load_answers_file(FIXTURE)
    output_dir = tmp_path / 'widget-tool'
    return scaffold_project(answers, output_dir)


def test_expected_files_are_created(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    for relative in [
        '.devcontainer/devcontainer.json',
        '.devcontainer/Dockerfile',
        '.devcontainer/post-create.sh',
        '.devcontainer/claude-home/.gitkeep',
        '.claude/settings.json',
        '.claude/skills/project-governance/SKILL.md',
        '.claude/skills/python-uv-conventions/SKILL.md',
        '.claude/skills/commit-craftsman/SKILL.md',
        '.githooks/pre-commit',
        '.gitignore',
        'CLAUDE.md',
        'README.md',
        'CHANGELOG.md',
        'LICENSE',
        'pyproject.toml',
        'src/widget_tool/__init__.py',
        'src/widget_tool/cli.py',
        'tests/test_cli.py',
    ]:
        assert (project_dir / relative).exists(), f'missing {relative}'


def test_devcontainer_json_is_valid_and_wired_for_sandboxing(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    # docker-in-docker is what forces the container to run --privileged; it must NOT be
    # present by default, so the devcontainer stays unprivileged and host-isolated.
    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']
    assert 'ghcr.io/anthropics/devcontainer-features/claude-code:1.0' in config['features']
    assert config['build'] == {'dockerfile': 'Dockerfile'}
    assert config['mounts'] == [
        'source=${localWorkspaceFolder}/.devcontainer,'
        'target=${containerWorkspaceFolder}/.devcontainer,type=bind,readonly',
        'source=${localWorkspaceFolder}/.devcontainer/claude-home,'
        'target=/home/vscode/.claude,type=bind',
    ]
    assert config['containerEnv']['CLAUDE_CONFIG_DIR'] == '/home/vscode/.claude'
    assert 'runArgs' not in config


def test_devcontainer_dir_is_read_only_inside_container(tmp_path: Path) -> None:
    # The .devcontainer directory (which defines the sandbox) is mounted read-only so
    # in-container Claude Code cannot rewrite devcontainer.json/Dockerfile/post-create.sh
    # and thereby run code on the host at the next rebuild.
    project_dir = _scaffold(tmp_path)
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    ro = [m for m in config['mounts'] if m.endswith('.devcontainer,type=bind,readonly')]
    assert len(ro) == 1
    # claude-home stays writable via a separate, more specific target path.
    assert any('target=/home/vscode/.claude,type=bind' in m for m in config['mounts'])


def test_enable_docker_opt_in_adds_docker_in_docker(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['enable_docker'] = True
    output_dir = tmp_path / 'widget-tool-docker'

    project_dir = scaffold_project(answers, output_dir)
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' in config['features']
    # The generated docs must warn that this re-introduces host access.
    assert 'privileged' in (project_dir / 'README.md').read_text()


def test_project_name_cannot_inject_devcontainer_json_keys(tmp_path: Path) -> None:
    # A project name crafted to break out of the JSON string literal must not be
    # able to inject extra devcontainer.json keys (e.g. runArgs/mounts/privileged).
    answers = load_answers_file(FIXTURE)
    answers['project_name'] = 'Pwn", "runArgs": ["--privileged", "-v", "/:/host"], "x": "y'
    output_dir = tmp_path / 'widget-tool-injection'

    project_dir = scaffold_project(answers, output_dir)
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    # The payload survives only as the (escaped) string value of "name"; it must
    # not have become real top-level keys such as runArgs.
    assert config['name'] == answers['project_name']
    assert 'runArgs' not in config
    assert 'x' not in config


def test_gpu_enabled_adds_run_args(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['gpu_enabled'] = True
    output_dir = tmp_path / 'widget-tool-gpu'

    project_dir = scaffold_project(answers, output_dir)
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert config['runArgs'] == ['--gpus=all']


def test_claude_settings_json_denies_git_push(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    settings = json.loads((project_dir / '.claude' / 'settings.json').read_text())

    assert 'Bash(git push *)' in settings['permissions']['deny']


def test_gitignore_covers_claude_home(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    gitignore = (project_dir / '.gitignore').read_text()

    assert '/.devcontainer/claude-home/' in gitignore


def test_pyproject_has_required_style_conventions(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    pyproject = (project_dir / 'pyproject.toml').read_text()

    assert 'name = "widget-tool"' in pyproject
    assert 'quote-style = "single"' in pyproject
    assert 'force-single-line = true' in pyproject


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
    remotes = subprocess.run(
        ['git', 'remote'], cwd=project_dir, capture_output=True, text=True, check=True
    )

    assert len(log.stdout.strip().splitlines()) == 1
    assert status.stdout.strip() == ''
    assert remotes.stdout.strip() == ''


def test_git_remote_is_set_when_provided(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['git_remote_url'] = 'https://example.com/widget-tool.git'
    output_dir = tmp_path / 'widget-tool-remote'

    project_dir = scaffold_project(answers, output_dir)
    remotes = subprocess.run(
        ['git', 'remote', '-v'], cwd=project_dir, capture_output=True, text=True, check=True
    )

    assert 'https://example.com/widget-tool.git' in remotes.stdout
