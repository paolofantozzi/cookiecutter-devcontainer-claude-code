from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from cdforge import __version__
from cdforge.answers import AnswersError
from cdforge.answers import load_answers_file
from cdforge.project_types.registry import PROJECT_TYPES
from cdforge.scaffold import ScaffoldError
from cdforge.scaffold import scaffold_project
from cdforge.skills_catalog import OPTIONAL_SKILLS
from cdforge.wizard import run_wizard

app = typer.Typer(
    name='cdforge',
    help='Scaffold VS Code devcontainer projects with a sandboxed Claude Code inside.',
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option('--version', callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    return


@app.command()
def new(
    answers_file: Annotated[
        Path | None,
        typer.Option('--answers-file', help='JSON file with pre-filled answers.'),
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option('--output-dir', help='Directory to scaffold the project into.'),
    ] = None,
    non_interactive: Annotated[
        bool,
        typer.Option('--non-interactive', help='Fail instead of prompting for missing answers.'),
    ] = False,
    force: Annotated[
        bool,
        typer.Option('--force', help='Scaffold even if the output directory is not empty.'),
    ] = False,
) -> None:
    """Scaffold a new devcontainer + Claude Code project."""
    if answers_file is not None:
        try:
            answers = load_answers_file(answers_file)
        except AnswersError as exc:
            typer.secho(str(exc), fg=typer.colors.RED)
            raise typer.Exit(code=1) from exc
        resolved_output = output_dir or Path(answers.get('output_dir', answers['project_name']))
    elif non_interactive:
        typer.secho('--non-interactive requires --answers-file', fg=typer.colors.RED)
        raise typer.Exit(code=1)
    else:
        answers, wizard_output_dir = run_wizard()
        resolved_output = output_dir or wizard_output_dir

    try:
        project_dir = scaffold_project(answers, resolved_output, force=force)
    except ScaffoldError as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.secho(f'Project scaffolded at {project_dir}', fg=typer.colors.GREEN)
    typer.echo('Next steps:')
    typer.echo(f'  1. code {project_dir}')
    typer.echo('  2. Command Palette -> "Dev Containers: Reopen in Container"')
    typer.echo('  3. Open a terminal in the container and run `claude` to sign in once')


@app.command('list-types')
def list_types() -> None:
    """List the available project types."""
    for project_type in PROJECT_TYPES.values():
        typer.echo(f'{project_type.id}\t{project_type.label} — {project_type.description}')


@app.command('list-skills')
def list_skills() -> None:
    """List the optional skills that can be added to a generated project."""
    for skill in OPTIONAL_SKILLS:
        scope = ', '.join(skill.applicable_types) or 'all types'
        typer.echo(f'{skill.id}\t({scope})\t{skill.description}')


if __name__ == '__main__':
    app()
