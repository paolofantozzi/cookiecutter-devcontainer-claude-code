from pathlib import Path

from typer.testing import CliRunner

from cdforge.cli import app

FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_python_uv_tool.json'

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


def test_list_types_lists_both_project_types() -> None:
    result = runner.invoke(app, ['list-types'])

    assert result.exit_code == 0
    assert 'python_uv_tool' in result.output
    assert 'django_drf' in result.output


def test_list_skills_lists_optional_skills() -> None:
    result = runner.invoke(app, ['list-skills'])

    assert result.exit_code == 0
    assert 'commit-craftsman' in result.output
    assert 'api-docs-writer' in result.output


def test_version_flag_prints_a_version() -> None:
    result = runner.invoke(app, ['--version'])

    assert result.exit_code == 0
    assert result.output.strip()
