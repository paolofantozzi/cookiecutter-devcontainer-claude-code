import json
from pathlib import Path

import pytest

from cdforge.answers import AnswersError
from cdforge.answers import load_answers_file
from cdforge.scaffold import scaffold_project

FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_django_drf.json'


def _scaffold(tmp_path: Path) -> Path:
    answers = load_answers_file(FIXTURE)
    output_dir = tmp_path / 'notes-api'
    return scaffold_project(answers, output_dir)


def test_expected_files_are_created(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    for relative in [
        '.devcontainer/devcontainer.json',
        '.devcontainer/Dockerfile',
        '.claude/settings.json',
        '.claude/skills/project-governance/SKILL.md',
        '.claude/skills/django-drf-conventions/SKILL.md',
        '.claude/skills/api-docs-writer/SKILL.md',
        '.claude/skills/security-audit-helper/SKILL.md',
        '.githooks/pre-commit',
        'manage.py',
        'pyproject.toml',
        'docker-compose.yml',
        '.env.example',
        'notes_api_config/settings.py',
        'notes_api_config/urls.py',
        'notes_api_config/wsgi.py',
        'notes_api_config/asgi.py',
        'notes_api_config/celery.py',
        'apps/__init__.py',
        'apps/core/models.py',
        'apps/core/serializers.py',
        'apps/core/views.py',
        'apps/core/urls.py',
        'apps/core/tests/test_health.py',
        'apps/core/tests/test_notes.py',
    ]:
        assert (project_dir / relative).exists(), f'missing {relative}'


def test_devcontainer_is_a_single_plain_container(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    # The devcontainer is only the dev/Claude environment: one plain build.dockerfile
    # container, never a compose service. Backing services are the developer's to run inside.
    assert config['build'] == {'dockerfile': 'Dockerfile'}
    assert 'dockerComposeFile' not in config
    assert 'service' not in config
    assert 'ghcr.io/anthropics/devcontainer-features/claude-code:1.0' in config['features']


def test_sysbox_project_gets_the_in_container_daemon_not_dind_feature(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    # Postgres/Redis run from inside via `docker compose up -d`; the fixture uses sysbox for
    # that daemon, so it is a runArg + docker-start.sh, never the privileged dind feature.
    assert config['runArgs'] == ['--runtime=sysbox-runc']
    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']
    assert 'bash .devcontainer/docker-start.sh' in config['postStartCommand']


def test_docker_compose_defines_only_backing_services(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    compose = (project_dir / 'docker-compose.yml').read_text()

    # docker-compose.yml is the app's own backing services, run from inside the container.
    # There is no `app` service: the devcontainer is not part of this file.
    assert 'app:' not in compose
    assert 'db:' in compose
    assert 'postgres:16' in compose
    assert 'redis:7' in compose
    assert 'privileged: true' not in compose
    assert 'sysbox-runc' not in compose


def test_postgres_or_celery_requires_in_container_docker(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['docker_mode'] = 'none'

    with pytest.raises(AnswersError, match='in-container Docker'):
        scaffold_project(answers, tmp_path / 'notes-api-none')


def test_privileged_mode_enables_the_dind_feature(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['docker_mode'] = 'privileged'
    output_dir = tmp_path / 'notes-api-privileged'

    project_dir = scaffold_project(answers, output_dir)
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' in config['features']
    assert 'runArgs' not in config or '--runtime=sysbox-runc' not in config.get('runArgs', [])


def test_gpu_passes_through_as_a_host_runarg(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['gpu_enabled'] = True
    answers['docker_mode'] = 'privileged'  # sysbox has no NVIDIA-runtime support
    output_dir = tmp_path / 'notes-api-gpu'

    project_dir = scaffold_project(answers, output_dir)
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert '--gpus=all' in config['runArgs']
    assert config['hostRequirements'] == {'gpu': 'optional'}
    # The compose file never carries the GPU reservation any more.
    assert 'nvidia' not in (project_dir / 'docker-compose.yml').read_text()


def test_settings_point_at_localhost_services(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    env_example = (project_dir / '.env.example').read_text()
    settings = (project_dir / 'notes_api_config' / 'settings.py').read_text()

    # The devcontainer is not on the services' network; it reaches them via published ports.
    assert '@localhost:5432' in env_example
    assert 'redis://localhost:6379' in env_example
    assert 'redis://localhost:6379' in settings
    assert '@db:5432' not in env_example


def test_docker_compose_is_omitted_without_postgres_or_celery(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['database'] = 'sqlite'
    answers['include_celery'] = False
    answers['docker_mode'] = 'none'  # no services, so no in-container Docker is required
    output_dir = tmp_path / 'notes-api-sqlite'

    project_dir = scaffold_project(answers, output_dir)

    assert not (project_dir / 'docker-compose.yml').exists()
    assert not (project_dir / 'notes_api_config' / 'celery.py').exists()
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())
    assert config['build'] == {'dockerfile': 'Dockerfile'}
    assert 'dockerComposeFile' not in config
    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']


def test_settings_reference_installed_apps_and_auth(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    settings = (project_dir / 'notes_api_config' / 'settings.py').read_text()

    assert "'apps.core'" in settings
    assert 'rest_framework_simplejwt' in settings
    assert 'drf_spectacular' in settings


def test_dev_services_are_published_on_the_loopback_only(tmp_path: Path) -> None:
    # Django reaches these at localhost via the published port; binding every host interface
    # would expose a fixed-password dev database to the whole LAN.
    compose = (_scaffold(tmp_path) / 'docker-compose.yml').read_text()

    assert '"127.0.0.1:5432:5432"' in compose
    assert '"127.0.0.1:6379:6379"' in compose


def test_firewall_adds_capabilities_as_host_runargs(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['network_firewall'] = 'allowlist'

    project_dir = scaffold_project(answers, tmp_path / 'notes-api-firewall')
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())
    dockerfile = (project_dir / '.devcontainer' / 'Dockerfile').read_text()

    # The plain layout expresses the firewall capability as host runArgs.
    assert '--cap-add=NET_ADMIN' in config['runArgs']
    assert '--cap-add=NET_RAW' in config['runArgs']
    assert 'sudo /usr/local/bin/cdforge-firewall' in config['postStartCommand']
    # The plain build context is .devcontainer/, so the COPY path is unprefixed.
    assert 'COPY init-firewall.sh /usr/local/bin/cdforge-firewall' in dockerfile
    firewall = (project_dir / '.devcontainer' / 'init-firewall.sh').read_text()
    assert 'ip -o -f inet addr show scope global' in firewall
