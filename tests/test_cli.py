from pathlib import Path

from typer.testing import CliRunner

from cdforge.cli import app

FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_python_uv_tool.json'
DJANGO_FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_django_drf.json'
DATA_SCIENCE_FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_data_science.json'
GENERIC_FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_generic.json'
ANGULAR_FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_angular.json'
STATIC_SITE_FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_static_site.json'

runner = CliRunner()


def test_new_with_answers_file_scaffolds_project(tmp_path: Path) -> None:
    output_dir = tmp_path / 'widget-tool'

    result = runner.invoke(
        app,
        ['new', '--answers-file', str(FIXTURE), '--output-dir', str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / 'pyproject.toml').exists()


def test_new_non_interactive_without_answers_file_fails(tmp_path: Path) -> None:
    result = runner.invoke(app, ['new', '--non-interactive'])

    assert result.exit_code == 1


def test_list_types_lists_every_project_type() -> None:
    result = runner.invoke(app, ['list-types'])

    assert result.exit_code == 0
    assert 'python_uv_tool' in result.output
    assert 'django_drf' in result.output
    assert 'data_science' in result.output
    assert 'generic' in result.output
    assert 'angular' in result.output
    assert 'static_site' in result.output


def test_list_skills_lists_optional_skills() -> None:
    result = runner.invoke(app, ['list-skills'])

    assert result.exit_code == 0
    assert 'commit-craftsman' in result.output
    assert 'api-docs-writer' in result.output


def test_version_flag_prints_a_version() -> None:
    result = runner.invoke(app, ['--version'])

    assert result.exit_code == 0
    assert result.output.strip()


def test_adopt_on_a_freshly_scaffolded_project_finds_nothing_to_change(tmp_path: Path) -> None:
    output_dir = tmp_path / 'widget-tool'
    runner.invoke(app, ['new', '--answers-file', str(FIXTURE), '--output-dir', str(output_dir)])

    result = runner.invoke(app, ['adopt', str(output_dir), '--dry-run'])

    assert result.exit_code == 0, result.output
    assert 'already aligned' in result.output
    assert 'conflict' not in result.output


def test_adopt_on_a_freshly_scaffolded_generic_project_finds_nothing_to_change(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / 'scratch-space'
    runner.invoke(
        app, ['new', '--answers-file', str(GENERIC_FIXTURE), '--output-dir', str(output_dir)]
    )

    result = runner.invoke(app, ['adopt', str(output_dir), '--dry-run'])

    assert result.exit_code == 0, result.output
    assert 'already aligned' in result.output
    assert 'conflict' not in result.output


def test_adopt_on_a_freshly_scaffolded_notebook_project_finds_nothing_to_change(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / 'churn-lab'
    runner.invoke(
        app, ['new', '--answers-file', str(DATA_SCIENCE_FIXTURE), '--output-dir', str(output_dir)]
    )

    result = runner.invoke(app, ['adopt', str(output_dir), '--dry-run'])

    assert result.exit_code == 0, result.output
    assert 'already aligned' in result.output
    assert 'conflict' not in result.output


def test_adopt_on_a_freshly_scaffolded_angular_project_finds_nothing_to_change(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / 'dashboard-ui'
    runner.invoke(
        app, ['new', '--answers-file', str(ANGULAR_FIXTURE), '--output-dir', str(output_dir)]
    )

    result = runner.invoke(app, ['adopt', str(output_dir), '--dry-run'])

    assert result.exit_code == 0, result.output
    assert 'already aligned' in result.output
    assert 'conflict' not in result.output


def test_adopt_on_a_freshly_scaffolded_static_site_project_finds_nothing_to_change(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / 'marketing-site'
    runner.invoke(
        app, ['new', '--answers-file', str(STATIC_SITE_FIXTURE), '--output-dir', str(output_dir)]
    )

    result = runner.invoke(app, ['adopt', str(output_dir), '--dry-run'])

    assert result.exit_code == 0, result.output
    assert 'already aligned' in result.output
    assert 'conflict' not in result.output


def test_adopt_on_a_freshly_scaffolded_django_project_finds_nothing_to_change(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / 'notes-api'
    runner.invoke(
        app, ['new', '--answers-file', str(DJANGO_FIXTURE), '--output-dir', str(output_dir)]
    )

    result = runner.invoke(app, ['adopt', str(output_dir), '--dry-run'])

    assert result.exit_code == 0, result.output
    assert 'already aligned' in result.output
    assert 'conflict' not in result.output
    # The generated docker-compose.yml is create-only, so a re-adopt leaves it untouched.
    assert 'docker-compose.cdforge.yml' not in result.output
