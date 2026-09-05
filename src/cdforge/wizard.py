from __future__ import annotations

from pathlib import Path
from typing import Any

import questionary

from cdforge.context_builder import slugify
from cdforge.project_types.base import ProjectType
from cdforge.project_types.base import Question
from cdforge.project_types.registry import PROJECT_TYPES
from cdforge.skills_catalog import skills_for_type


def _ask_question(question: Question, default: Any = None) -> Any:
    resolved = question.resolve_default() if default is None else default
    if question.kind == 'confirm':
        return questionary.confirm(question.prompt, default=bool(resolved)).ask()
    if question.kind == 'select':
        choice = resolved if resolved in question.choices else question.resolve_default()
        return questionary.select(question.prompt, choices=question.choices, default=choice).ask()
    return questionary.text(question.prompt, default=str(resolved or '')).ask()


def run_wizard(
    defaults: dict[str, Any] | None = None,
    *,
    ask_output_dir: bool = True,
) -> tuple[dict[str, Any], Path | None]:
    """Ask the common questions plus the chosen type's own ones.

    `defaults` pre-fills every prompt, which is how `cdforge adopt` offers what it
    detected in an existing project; `ask_output_dir` is False when the target
    directory is already known (adoption).
    """
    defaults = defaults or {}
    answers: dict[str, Any] = {}

    answers['project_name'] = questionary.text(
        'Project name', default=str(defaults.get('project_name', ''))
    ).ask()
    output_dir: Path | None = None
    if ask_output_dir:
        output_dir = Path(
            questionary.text('Output directory', default=slugify(answers['project_name'])).ask()
        )
    answers['git_remote_url'] = questionary.text(
        'Git remote URL (leave blank if it does not exist yet)',
        default=str(defaults.get('git_remote_url', '')),
    ).ask()

    type_choices = [
        questionary.Choice(title=pt.label, value=pt.id) for pt in PROJECT_TYPES.values()
    ]
    default_type = defaults.get('project_type')
    type_choice = questionary.select(
        'Project type',
        choices=type_choices,
        default=default_type if default_type in PROJECT_TYPES else None,
    ).ask()
    answers['project_type'] = type_choice
    project_type: ProjectType = PROJECT_TYPES[type_choice]

    answers['gpu_enabled'] = questionary.confirm(
        'Make the GPU available inside the devcontainer?',
        default=bool(defaults.get('gpu_enabled', False)),
    ).ask()

    docker_default = defaults.get('docker_mode', 'none')
    answers['docker_mode'] = questionary.select(
        'In-container Docker for Claude Code (build/run/Testcontainers)?',
        choices=[
            questionary.Choice('None — maximum sandbox (default)', value='none'),
            questionary.Choice(
                'Sysbox — Docker inside, still unprivileged/no host access '
                '(requires sysbox on the host)',
                value='sysbox',
            ),
            questionary.Choice(
                'Privileged docker-in-docker — full Docker but REMOVES host isolation',
                value='privileged',
            ),
        ],
        default=docker_default if docker_default in ('none', 'sysbox', 'privileged') else 'none',
    ).ask()

    # A devcontainer is unprivileged, but by default it can still reach the host through the
    # Docker bridge gateway, plus the LAN and the whole internet. The firewall closes that.
    firewall_choices = [
        questionary.Choice('None — unrestricted network egress (default)', value='none'),
        questionary.Choice(
            'Allowlist — reject the host gateway and anything off the allowlist '
            '(in-container sudo can still flush it)',
            value='allowlist',
        ),
    ]
    firewall_default = defaults.get('network_firewall', 'none')
    if answers['docker_mode'] == 'none':
        firewall_choices.append(
            questionary.Choice(
                'Strict — the allowlist, plus no passwordless sudo so it cannot be undone '
                'from inside',
                value='strict',
            )
        )
    elif firewall_default == 'strict':
        # In-container Docker needs root at runtime, so strict cannot apply there.
        firewall_default = 'allowlist'
    answers['network_firewall'] = questionary.select(
        "Restrict the devcontainer's network egress?",
        choices=firewall_choices,
        default=firewall_default
        if firewall_default in {choice.value for choice in firewall_choices}
        else 'none',
    ).ask()

    catalog = skills_for_type(project_type.id)
    if catalog:
        preselected = set(defaults.get('optional_skills', []) or [])
        chosen = questionary.checkbox(
            'Optional Claude Code skills to include',
            choices=[
                questionary.Choice(
                    title=f'{s.label} — {s.description}',
                    value=s.id,
                    checked=s.id in preselected,
                )
                for s in catalog
            ],
        ).ask()
        answers['optional_skills'] = chosen or []
    else:
        answers['optional_skills'] = []

    for question in project_type.questions:
        answers[question.key] = _ask_question(question, defaults.get(question.key))

    return answers, output_dir
