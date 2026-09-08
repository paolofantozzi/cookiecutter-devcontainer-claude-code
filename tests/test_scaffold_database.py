"""The database backend is a shared question across every Python project type: `none` and
`sqlite` need no service, `postgres` and `mariadb` emit a root `docker-compose.yml` for that
engine and wire the software to it through `DATABASE_URL`."""

from pathlib import Path

import pytest

from cdforge.answers import AnswersError
from cdforge.answers import load_answers_file
from cdforge.scaffold import scaffold_project

FIXTURES = Path(__file__).parent / 'fixtures'

# project type -> (fixture file, src file that must exist so we know the tree rendered)
PYTHON_TYPES = {
    'python_uv_tool': 'answers_python_uv_tool.json',
    'generic': 'answers_generic.json',
    'data_science': 'answers_data_science.json',
    'django_drf': 'answers_django_drf.json',
}

SERVER_FACTS = {
    'postgres': ('postgres:16', '5432', 'psycopg[binary]', 'postgres://'),
    'mariadb': ('mariadb:11', '3306', 'mysqlclient', 'mysql://'),
}


def _answers(fixture: str, database: str) -> dict:
    answers = load_answers_file(FIXTURES / fixture)
    answers['database'] = database
    if database in SERVER_FACTS:
        # A database server runs from inside the devcontainer, which needs its own daemon.
        answers['docker_mode'] = 'sysbox'
    return answers


@pytest.mark.parametrize('project_type', sorted(PYTHON_TYPES))
@pytest.mark.parametrize('database', sorted(SERVER_FACTS))
def test_server_database_emits_a_root_compose_and_wires_the_url(
    tmp_path: Path, project_type: str, database: str
) -> None:
    image, port, driver, url_scheme = SERVER_FACTS[database]
    answers = _answers(PYTHON_TYPES[project_type], database)

    project_dir = scaffold_project(answers, tmp_path / f'{project_type}-{database}')

    compose = (project_dir / 'docker-compose.yml').read_text()
    assert 'app:' not in compose
    assert image in compose
    assert f'"127.0.0.1:{port}:{port}"' in compose

    env_example = (project_dir / '.env.example').read_text()
    assert f'DATABASE_URL={url_scheme}' in env_example
    assert f'@localhost:{port}/' in env_example

    assert driver in (project_dir / 'pyproject.toml').read_text()


@pytest.mark.parametrize('project_type', sorted(PYTHON_TYPES))
@pytest.mark.parametrize('database', ['none', 'sqlite'])
def test_serviceless_database_emits_no_compose(
    tmp_path: Path, project_type: str, database: str
) -> None:
    answers = _answers(PYTHON_TYPES[project_type], database)
    if project_type == 'django_drf':
        # The fixture defaults to Celery+sysbox; strip that so `none` needs no daemon.
        answers['include_celery'] = False
        answers['docker_mode'] = 'none'

    project_dir = scaffold_project(answers, tmp_path / f'{project_type}-{database}')

    assert not (project_dir / 'docker-compose.yml').exists()
    env_example = project_dir / '.env.example'
    if project_type == 'django_drf':
        # Django always ships an .env.example (DJANGO_SECRET_KEY etc.); it just points at a
        # local SQLite file when there is no server.
        assert 'sqlite://' in env_example.read_text()
    elif database == 'none':
        assert not env_example.exists()
    else:
        assert 'sqlite://' in env_example.read_text()
    pyproject = (project_dir / 'pyproject.toml').read_text()
    assert 'psycopg' not in pyproject
    assert 'mysqlclient' not in pyproject


@pytest.mark.parametrize('project_type', sorted(PYTHON_TYPES))
def test_mariadb_adds_the_client_build_dependency_to_the_image(
    tmp_path: Path, project_type: str
) -> None:
    answers = _answers(PYTHON_TYPES[project_type], 'mariadb')

    project_dir = scaffold_project(answers, tmp_path / f'{project_type}-mariadb-apt')

    dockerfile = (project_dir / '.devcontainer' / 'Dockerfile').read_text()
    # `mysqlclient` is a C extension built against libmariadb at `uv sync` time.
    assert 'default-libmysqlclient-dev' in dockerfile
    assert 'pkg-config' in dockerfile


@pytest.mark.parametrize('database', sorted(SERVER_FACTS))
def test_server_database_without_in_container_docker_is_rejected(
    tmp_path: Path, database: str
) -> None:
    answers = load_answers_file(FIXTURES / 'answers_python_uv_tool.json')
    answers['database'] = database
    answers['docker_mode'] = 'none'

    with pytest.raises(AnswersError, match='in-container Docker'):
        scaffold_project(answers, tmp_path / f'no-docker-{database}')
