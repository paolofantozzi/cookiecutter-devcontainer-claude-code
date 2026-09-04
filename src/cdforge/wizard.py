from __future__ import annotations

from pathlib import Path
from typing import Any

import questionary

from cdforge.context_builder import slugify
from cdforge.project_types.base import ProjectType
from cdforge.project_types.base import Question
from cdforge.project_types.registry import PROJECT_TYPES
from cdforge.skills_catalog import skills_for_type


def _ask_question(question: Question) -> Any:
    default = question.resolve_default()
    if question.kind == 'confirm':
        return questionary.confirm(question.prompt, default=bool(default)).ask()
    if question.kind == 'select':
        return questionary.select(question.prompt, choices=question.choices, default=default).ask()
    return questionary.text(question.prompt, default=str(default or '')).ask()


def run_wizard() -> tuple[dict[str, Any], Path]:
    answers: dict[str, Any] = {}

    answers['project_name'] = questionary.text('Project name').ask()
    default_dir = slugify(answers['project_name'])
    output_dir = questionary.text('Output directory', default=default_dir).ask()
    answers['git_remote_url'] = questionary.text(
        'Git remote URL (leave blank if it does not exist yet)', default=''
    ).ask()

    type_choice = questionary.select(
        'Project type',
        choices=[questionary.Choice(title=pt.label, value=pt.id) for pt in PROJECT_TYPES.values()],
    ).ask()
    answers['project_type'] = type_choice
    project_type: ProjectType = PROJECT_TYPES[type_choice]

    answers['gpu_enabled'] = questionary.confirm(
        'Make the GPU available inside the devcontainer?', default=False
    ).ask()

    answers['enable_docker'] = questionary.confirm(
        'Allow Claude Code to run its own containers inside the devcontainer? '
        'WARNING: this enables docker-in-docker, which makes the container run '
        '--privileged and REMOVES host isolation.',
        default=False,
    ).ask()

    catalog = skills_for_type(project_type.id)
    if catalog:
        chosen = questionary.checkbox(
            'Optional Claude Code skills to include',
            choices=[
                questionary.Choice(title=f'{s.label} — {s.description}', value=s.id)
                for s in catalog
            ],
        ).ask()
        answers['optional_skills'] = chosen or []
    else:
        answers['optional_skills'] = []

    for question in project_type.questions:
        answers[question.key] = _ask_question(question)

    return answers, Path(output_dir)
