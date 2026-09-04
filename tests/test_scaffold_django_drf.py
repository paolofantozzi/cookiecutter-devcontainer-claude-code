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


def test_devcontainer_json_has_gpu_and_both_features(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert config['runArgs'] == ['--gpus=all']
    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' in config['features']
    assert 'ghcr.io/anthropics/devcontainer-features/claude-code:1.0' in config['features']


def test_docker_compose_includes_postgres_and_redis(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    compose = (project_dir / 'docker-compose.yml').read_text()

    assert 'postgres:16' in compose
    assert 'redis:7' in compose


def test_docker_compose_is_omitted_without_postgres_or_celery(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    answers['database'] = 'sqlite'
    answers['include_celery'] = False
    output_dir = tmp_path / 'notes-api-sqlite'

    project_dir = scaffold_project(answers, output_dir)

    assert not (project_dir / 'docker-compose.yml').exists()
    assert not (project_dir / 'notes_api_config' / 'celery.py').exists()


def test_settings_reference_installed_apps_and_auth(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    settings = (project_dir / 'notes_api_config' / 'settings.py').read_text()

    assert "'apps.core'" in settings
    assert 'rest_framework_simplejwt' in settings
    assert 'drf_spectacular' in settings
