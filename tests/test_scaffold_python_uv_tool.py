import json
import os
import subprocess
from pathlib import Path

import pytest

from cdforge.answers import AnswersError
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
        '.githooks/pre-push',
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
    # dockerd is started from postStartCommand, not from the feature's container entrypoint:
    # that entrypoint would need "overrideCommand": false, which lets the base image's CMD
    # end the container as soon as it exits.
    assert 'overrideCommand' not in config
    assert config['postStartCommand'] == 'bash .devcontainer/docker-start.sh'
    start = (project_dir / '.devcontainer' / 'docker-start.sh').read_text()
    # The legacy iptables backend cannot create the `nat` table on nftables-only hosts.
    assert 'iptables-nft' in start
    assert '/usr/local/share/docker-init.sh' in start
    # The generated docs must warn that this re-introduces host access.
    assert 'privileged' in (project_dir / 'README.md').read_text()


def test_sysbox_mode_gives_docker_without_privilege(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['docker_mode'] = 'sysbox'
    output_dir = tmp_path / 'widget-tool-sysbox'

    project_dir = scaffold_project(answers, output_dir)
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    # Sysbox uses the runtime, not the privileged docker-in-docker feature.
    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']
    assert '--runtime=sysbox-runc' in config['runArgs']
    assert config['postStartCommand'] == 'bash .devcontainer/docker-start.sh'
    # The daemon bootstrap script ships and is executable.
    start = project_dir / '.devcontainer' / 'docker-start.sh'
    assert start.exists()
    assert os.access(start, os.X_OK)


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


def test_gpu_plus_sysbox_is_rejected(tmp_path: Path) -> None:
    # Sysbox has no NVIDIA-runtime support: a container with both --gpus=all and
    # --runtime=sysbox-runc fails to start, so the combination must be refused up front.
    answers = load_answers_file(FIXTURE)
    answers['gpu_enabled'] = True
    answers['docker_mode'] = 'sysbox'

    with pytest.raises(AnswersError, match='sysbox'):
        scaffold_project(answers, tmp_path / 'widget-tool-gpu-sysbox')


def test_claude_settings_json_denies_git_push(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    settings = json.loads((project_dir / '.claude' / 'settings.json').read_text())

    assert 'Bash(git push *)' in settings['permissions']['deny']


def test_gitignore_covers_claude_home(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    gitignore = (project_dir / '.gitignore').read_text()

    assert '/.devcontainer/claude-home/' in gitignore


def test_cli_defines_a_callback_so_subcommands_work(tmp_path: Path) -> None:
    # Without an @app.callback(), a single-command Typer app collapses and `tool version`
    # exits with code 2 instead of running the command.
    project_dir = _scaffold(tmp_path)

    cli = (project_dir / 'src' / 'widget_tool' / 'cli.py').read_text()

    assert '@app.callback()' in cli
    assert '@app.command()' in cli


def test_pyproject_has_required_style_conventions(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    pyproject = (project_dir / 'pyproject.toml').read_text()

    assert 'name = "widget-tool"' in pyproject
    assert 'quote-style = "single"' in pyproject
    assert 'force-single-line = true' in pyproject


def test_pyproject_declares_uv_build_module_name(tmp_path: Path) -> None:
    # The import package name can differ from the distribution name; uv_build must be told
    # where the module is, or `uv sync` fails with "Expected a Python module at ...".
    answers = load_answers_file(FIXTURE)
    answers['project_name'] = 'Totally Different Name'
    answers['package_import_name'] = 'widget_tool'
    project_dir = scaffold_project(answers, tmp_path / 'mismatch')

    pyproject = (project_dir / 'pyproject.toml').read_text()
    assert 'module-name = "widget_tool"' in pyproject


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


def test_network_egress_is_unrestricted_by_default(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert not (project_dir / '.devcontainer' / 'init-firewall.sh').exists()
    assert 'postStartCommand' not in config
    assert 'runArgs' not in config
    # The docs must say so rather than implying the sandbox covers the network too.
    assert 'not** network-isolated' in (project_dir / 'CLAUDE.md').read_text()


def test_allowlist_firewall_rejects_the_host_gateway(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['network_firewall'] = 'allowlist'

    project_dir = scaffold_project(answers, tmp_path / 'widget-tool-firewall')
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert config['runArgs'] == ['--cap-add=NET_ADMIN', '--cap-add=NET_RAW']
    assert config['postStartCommand'] == 'sudo /usr/local/bin/cdforge-firewall'

    script = project_dir / '.devcontainer' / 'init-firewall.sh'
    assert os.access(script, os.X_OK)
    firewall = script.read_text()
    # The rule the whole feature exists for: the host, one hop away at the bridge gateway.
    assert "ip route show default | awk '{print $3}'" in firewall
    assert 'api.anthropic.com' in firewall

    dockerfile = (project_dir / '.devcontainer' / 'Dockerfile').read_text()
    # The plain build layout's context is .devcontainer/ itself, and iptables must be there.
    assert 'COPY init-firewall.sh /usr/local/bin/cdforge-firewall' in dockerfile
    assert 'iptables' in dockerfile
    # This mode deliberately keeps sudo, and the docs must admit the rules are flushable.
    assert 'sudoers.d' not in dockerfile
    assert 'sudo iptables -F' in (project_dir / 'README.md').read_text()


def test_strict_firewall_removes_passwordless_sudo(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['network_firewall'] = 'strict'

    project_dir = scaffold_project(answers, tmp_path / 'widget-tool-strict')
    dockerfile = (project_dir / '.devcontainer' / 'Dockerfile').read_text()

    assert 'rm -f /etc/sudoers.d/vscode' in dockerfile
    assert 'NOPASSWD: /usr/local/bin/cdforge-firewall' in dockerfile


def test_strict_firewall_degrades_to_allowlist_with_in_container_docker(tmp_path: Path) -> None:
    # A Docker daemon inside the container needs root at runtime, so strict cannot hold.
    answers = load_answers_file(FIXTURE)
    answers['network_firewall'] = 'strict'
    answers['docker_mode'] = 'sysbox'

    project_dir = scaffold_project(answers, tmp_path / 'widget-tool-strict-docker')
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())
    dockerfile = (project_dir / '.devcontainer' / 'Dockerfile').read_text()

    assert 'sudoers.d' not in dockerfile
    # Docker comes up first; the firewall is applied last, so it has the final word.
    assert config['postStartCommand'] == (
        'bash .devcontainer/docker-start.sh && sudo /usr/local/bin/cdforge-firewall'
    )
