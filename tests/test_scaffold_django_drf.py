import json
from pathlib import Path

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


def test_devcontainer_uses_unprivileged_compose_workflow(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    # Backing services come from sibling containers via the compose workflow, so the
    # devcontainer stays unprivileged: no docker-in-docker, no host runArgs.
    assert config['dockerComposeFile'] == '../docker-compose.yml'
    assert config['service'] == 'app'
    assert config['workspaceFolder'] == '/workspaces/notes-api'
    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']
    assert 'ghcr.io/anthropics/devcontainer-features/claude-code:1.0' in config['features']
    assert 'runArgs' not in config


def test_docker_compose_defines_app_and_sibling_services(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    compose = (project_dir / 'docker-compose.yml').read_text()

    # The devcontainer itself is the unprivileged `app` service; db/redis are siblings.
    assert 'app:' in compose
    assert 'postgres:16' in compose
    assert 'redis:7' in compose
    assert 'privileged: true' not in compose
    # GPU (from the fixture) is expressed on the app service, not as a host runArg.
    assert 'nvidia' in compose


def test_sysbox_mode_sets_runtime_on_app_service(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['docker_mode'] = 'sysbox'
    output_dir = tmp_path / 'notes-api-sysbox'

    project_dir = scaffold_project(answers, output_dir)
    compose = (project_dir / 'docker-compose.yml').read_text()

    assert 'runtime: sysbox-runc' in compose
    assert 'privileged: true' not in compose
    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())
    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']


def test_settings_use_sibling_service_hostnames(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    env_example = (project_dir / '.env.example').read_text()
    settings = (project_dir / 'notes_api_config' / 'settings.py').read_text()

    assert '@db:5432' in env_example
    assert 'redis://redis:6379' in env_example
    assert 'redis://redis:6379' in settings


def test_docker_compose_is_omitted_without_postgres_or_celery(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['database'] = 'sqlite'
    answers['include_celery'] = False
    output_dir = tmp_path / 'notes-api-sqlite'

    project_dir = scaffold_project(answers, output_dir)

    assert not (project_dir / 'docker-compose.yml').exists()
    assert not (project_dir / 'notes_api_config' / 'celery.py').exists()
    # With no services, there is no compose project: the devcontainer builds directly
    # from the Dockerfile and still stays unprivileged.
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
