from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer

from cdforge import __version__
from cdforge.adopt import CONFLICT
from cdforge.adopt import SUGGESTION_SUFFIX
from cdforge.adopt import UNCHANGED
from cdforge.adopt import AdoptError
from cdforge.adopt import AlignmentPlan
from cdforge.adopt import apply_alignment
from cdforge.adopt import dirty_tracked_files
from cdforge.adopt import plan_alignment
from cdforge.answers import AnswersError
from cdforge.answers import load_answers_file
from cdforge.detect import detect_answers
from cdforge.detect import detect_git_remote
from cdforge.detect import detect_optional_skills
from cdforge.manifest import MANIFEST_NAME
from cdforge.manifest import ManifestError
from cdforge.manifest import read_manifest_answers
from cdforge.project_types.registry import PROJECT_TYPES
from cdforge.scaffold import ScaffoldError
from cdforge.scaffold import scaffold_project
from cdforge.skills_catalog import OPTIONAL_SKILLS
from cdforge.wizard import reselect_project_type
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
        resolved_output = output_dir or wizard_output_dir or Path(answers['project_name'])

    try:
        project_dir = scaffold_project(answers, resolved_output, force=force)
    except (ScaffoldError, AnswersError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    typer.secho(f'Project scaffolded at {project_dir}', fg=typer.colors.GREEN)
    typer.echo('Next steps:')
    typer.echo(f'  1. code {project_dir}')
    typer.echo('  2. Command Palette -> "Dev Containers: Reopen in Container"')
    typer.echo('  3. Open a terminal in the container and run `claude` to sign in once')


_ACTION_COLORS = {
    'create': typer.colors.GREEN,
    'update': typer.colors.YELLOW,
    'merge': typer.colors.CYAN,
    'conflict': typer.colors.RED,
}


def _detected_answers(project_dir: Path) -> dict:
    answers = detect_answers(project_dir)
    answers['git_remote_url'] = detect_git_remote(project_dir)
    answers['optional_skills'] = detect_optional_skills(project_dir)
    return answers


def _stdin_is_interactive() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, ValueError):
        return False


def _resolve_adopt_answers(
    project_dir: Path,
    *,
    answers_file: Path | None,
    type_id: str | None,
    non_interactive: bool,
    reconfigure: bool,
) -> dict:
    """Work out the answers `cdforge adopt` should render from.

    Precedence: an explicit `--answers-file`, then the answers recorded in
    `.cdforge.json` (unless `--reconfigure`), then what `detect.py` infers. `--type`
    overrides the project type in every one of those, without prompting. An interactive
    run with a recorded manifest also offers to change the type (re-asking only the new
    type's own questions); a non-interactive one reuses the recorded answers untouched.
    """
    if answers_file is not None:
        answers = load_answers_file(answers_file)
        if type_id is not None:
            answers = {**answers, 'project_type': type_id}
        return answers

    recorded = None if reconfigure else read_manifest_answers(project_dir)
    if recorded is not None:
        same_type = type_id in (None, recorded.get('project_type'))
        if same_type and (non_interactive or not _stdin_is_interactive()):
            typer.echo(f'Reusing the answers recorded in {MANIFEST_NAME}.')
            return dict(recorded)
        # Either the type is being changed (--type), or this is an interactive run that
        # offers to change it. reselect_project_type only prompts when type_id is None.
        answers = reselect_project_type(
            recorded, _detected_answers(project_dir), forced_type=type_id
        )
        if answers is recorded:
            typer.echo(f'Reusing the answers recorded in {MANIFEST_NAME}.')
        else:
            typer.secho(
                f'Project type set to {answers["project_type"]}. adopt only rewrites the '
                'managed files (.devcontainer/, .githooks/, .claude/); it never scaffolds '
                "the new type's source code.",
                fg=typer.colors.YELLOW,
            )
        return answers

    if non_interactive or not _stdin_is_interactive():
        answers = _detected_answers(project_dir)
        if type_id is not None:
            answers['project_type'] = type_id
            typer.echo(f'Forcing project type: {type_id}')
        else:
            typer.echo(f'Detected project type: {answers["project_type"]}')
        return answers

    answers, _ = run_wizard(
        _detected_answers(project_dir), ask_output_dir=False, force_project_type=type_id
    )
    return answers


def _print_plan(plan: AlignmentPlan) -> None:
    typer.echo(f'Alignment plan for {plan.project_dir} ({plan.project_type_id}):')
    for change in plan.changes:
        if change.action == UNCHANGED:
            continue
        color = _ACTION_COLORS[change.action]
        suffix = ' (exists and differs — left untouched)' if change.action == CONFLICT else ''
        typer.secho(f'  {change.action:<9}{change.relative_path}{suffix}', fg=color)
    unchanged = len(plan.by_action(UNCHANGED))
    if unchanged:
        typer.echo(f'  unchanged {unchanged} file(s) already aligned')
    if not plan.writes and not plan.conflicts:
        typer.echo('  nothing to do — this project is already aligned')


@app.command()
def adopt(
    project_dir: Annotated[
        Path,
        typer.Argument(help='Existing project directory to align (default: current directory).'),
    ] = Path('.'),
    answers_file: Annotated[
        Path | None,
        typer.Option('--answers-file', help='JSON file with pre-filled answers.'),
    ] = None,
    type_id: Annotated[
        str | None,
        typer.Option(
            '--type',
            '-t',
            help='Force the project type, overriding what is detected or recorded in '
            f'{MANIFEST_NAME} (one of: {", ".join(PROJECT_TYPES)}).',
        ),
    ] = None,
    non_interactive: Annotated[
        bool,
        typer.Option('--non-interactive', help='Never prompt; use detected/recorded answers.'),
    ] = False,
    reconfigure: Annotated[
        bool,
        typer.Option(
            '--reconfigure', help=f'Re-ask the questions instead of reusing {MANIFEST_NAME}.'
        ),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option('--dry-run', help='Show what would change and write nothing.'),
    ] = False,
    force: Annotated[
        bool,
        typer.Option('--force', help='Skip the warning about uncommitted changes in the project.'),
    ] = False,
    write_suggestions: Annotated[
        bool,
        typer.Option(
            '--write-suggestions',
            help='For conflicting files, write the generated version as '
            f'<name>{SUGGESTION_SUFFIX}.',
        ),
    ] = False,
) -> None:
    """Align an existing project with what `cdforge new` generates.

    Rewrites the managed sandbox files (.devcontainer/, .githooks/, .claude/), merges
    cdforge's entries into .gitignore and .claude/settings.json, creates the documents it
    ships only when they are missing, and never touches application source code. Re-run it
    after upgrading cdforge to pull newer devcontainer fixes into the project.
    """
    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        typer.secho(f'{project_dir} is not an existing directory', fg=typer.colors.RED)
        raise typer.Exit(code=1)
    if type_id is not None and type_id not in PROJECT_TYPES:
        typer.secho(
            f'Unknown project type {type_id!r}. Available: {", ".join(PROJECT_TYPES)}',
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    try:
        answers = _resolve_adopt_answers(
            project_dir,
            answers_file=answers_file,
            type_id=type_id,
            non_interactive=non_interactive,
            reconfigure=reconfigure,
        )
    except (AnswersError, ManifestError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    dirty = dirty_tracked_files(project_dir)
    if dirty and not force and not dry_run:
        typer.secho(
            'This project has uncommitted changes. Adoption only rewrites the managed '
            'files (.devcontainer/, .githooks/, .claude/); after it runs, `git diff` will '
            'mix its rewrite with your own edits. Commit or stash first for a clean review '
            '(or pass --force to silence this warning):',
            fg=typer.colors.YELLOW,
        )
        for path in dirty[:10]:
            typer.echo(f'  {path}')

    try:
        plan = plan_alignment(answers, project_dir)
    except (AdoptError, AnswersError, ValueError) as exc:
        typer.secho(str(exc), fg=typer.colors.RED)
        raise typer.Exit(code=1) from exc

    _print_plan(plan)

    if dry_run:
        typer.secho('Dry run: nothing was written.', fg=typer.colors.BLUE)
        return

    apply_alignment(plan, answers, write_suggestions=write_suggestions)
    typer.secho(
        f'Aligned {project_dir} with cdforge {__version__} ({len(plan.writes)} file(s) written).',
        fg=typer.colors.GREEN,
    )

    if plan.conflicts:
        typer.secho(
            'These files already existed and were left untouched; merge them by hand:',
            fg=typer.colors.YELLOW,
        )
        for change in plan.conflicts:
            hint = f' -> {change.relative_path}{SUGGESTION_SUFFIX}' if write_suggestions else ''
            typer.echo(f'  {change.relative_path}{hint}')
        if not write_suggestions:
            typer.echo('  (re-run with --write-suggestions to get the generated version alongside)')

    for note in plan.notes:
        typer.secho(f'Note: {note}', fg=typer.colors.YELLOW)

    typer.echo('Next steps:')
    typer.echo('  1. git diff   # review the rewritten files')
    typer.echo('  2. Command Palette -> "Dev Containers: Reopen in Container"')


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
