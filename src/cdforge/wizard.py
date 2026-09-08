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


def _ask_optional_skills(project_type_id: str, preselected: set[str]) -> list[str]:
    catalog = skills_for_type(project_type_id)
    if not catalog:
        return []
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
    return chosen or []


# Answers asked by the common part of the wizard; everything else in an answers dict
# belongs to a specific project type's own questions. `reselect_project_type` keeps these
# and re-asks only the chosen type's questions.
COMMON_ANSWER_KEYS = (
    'project_name',
    'git_remote_url',
    'project_type',
    'gpu_enabled',
    'docker_mode',
    'network_firewall',
    'optional_skills',
)


def reselect_project_type(
    recorded: dict[str, Any],
    detected: dict[str, Any] | None = None,
    *,
    forced_type: str | None = None,
) -> dict[str, Any]:
    """`cdforge adopt` on a project that already recorded its answers in `.cdforge.json`.

    Every common answer the manifest recorded is kept; only the project type may change.
    Returns the recorded answers unchanged when the type is left alone.

    - ``forced_type`` (the ``--type`` flag): switch without prompting. The new type's own
      answers are taken from ``detected`` where a key carries over and default otherwise;
      run ``--reconfigure`` for the full wizard.
    - otherwise: prompt for the type (default = the recorded one); changing it asks the
      new type's own questions, pre-filled from ``detected``, instead of re-running the
      whole wizard the way ``--reconfigure`` does.
    """
    detected = detected or {}
    current = recorded.get('project_type')
    if forced_type is not None:
        chosen = forced_type
    else:
        chosen = questionary.select(
            'Project type',
            choices=[
                questionary.Choice(title=pt.label, value=pt.id) for pt in PROJECT_TYPES.values()
            ],
            default=current if current in PROJECT_TYPES else None,
        ).ask()
    if chosen == current or chosen is None:
        return recorded

    answers: dict[str, Any] = {key: recorded[key] for key in COMMON_ANSWER_KEYS if key in recorded}
    answers['project_type'] = chosen
    fallback = {**detected, **recorded}
    project_type = PROJECT_TYPES[chosen]

    valid_skills = {s.id for s in skills_for_type(chosen)}
    carried_skills = [
        sid for sid in recorded.get('optional_skills', []) or [] if sid in valid_skills
    ]

    if forced_type is not None:
        answers['optional_skills'] = carried_skills
        for question in project_type.questions:
            answers[question.key] = (
                fallback[question.key] if question.key in fallback else question.resolve_default()
            )
        return answers

    answers['optional_skills'] = _ask_optional_skills(chosen, set(carried_skills))
    for question in project_type.questions:
        answers[question.key] = _ask_question(question, fallback.get(question.key))
    return answers


def run_wizard(
    defaults: dict[str, Any] | None = None,
    *,
    ask_output_dir: bool = True,
    force_project_type: str | None = None,
) -> tuple[dict[str, Any], Path | None]:
    """Ask the common questions plus the chosen type's own ones.

    `defaults` pre-fills every prompt, which is how `cdforge adopt` offers what it
    detected in an existing project; `ask_output_dir` is False when the target
    directory is already known (adoption); `force_project_type` skips the project-type
    prompt and uses that type (the `cdforge adopt --type` flag).
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

    if force_project_type is not None:
        type_choice = force_project_type
    else:
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
    docker_choices = [
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
    ]
    if docker_default not in ('none', 'sysbox', 'privileged'):
        docker_default = 'none'
    while True:
        answers['docker_mode'] = questionary.select(
            'In-container Docker for Claude Code (build/run/Testcontainers)?',
            choices=docker_choices,
            default=docker_default,
        ).ask()
        if not (answers['gpu_enabled'] and answers['docker_mode'] == 'sysbox'):
            break
        # Sysbox has no NVIDIA-runtime support: a container with both --gpus=all and
        # --runtime=sysbox-runc fails to start. Make the user resolve the conflict here.
        questionary.print(
            'Sysbox cannot be combined with GPU passthrough — the container would fail to '
            "start. Choose 'none' or 'privileged', or restart and answer no to the GPU "
            'question.',
            style='fg:yellow',
        )
        docker_default = 'none'

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

    answers['optional_skills'] = _ask_optional_skills(
        project_type.id, set(defaults.get('optional_skills', []) or [])
    )

    for question in project_type.questions:
        answers[question.key] = _ask_question(question, defaults.get(question.key))

    # Postgres/Redis are run from inside the devcontainer (docker compose up -d), which needs
    # an in-container Docker daemon. These questions come after docker_mode, so re-ask it
    # here rather than let build_context reject the combination.
    if (answers.get('database') == 'postgres' or answers.get('include_celery')) and answers.get(
        'docker_mode'
    ) == 'none':
        questionary.print(
            'Postgres/Redis run inside the devcontainer via its own Docker daemon, so this '
            "project needs docker_mode 'sysbox' or 'privileged' (not 'none').",
            style='fg:yellow',
        )
        # Sysbox has no NVIDIA-runtime support, so a GPU project can only take 'privileged'.
        service_docker_choices = [
            questionary.Choice(
                'Privileged docker-in-docker — full Docker but REMOVES host isolation',
                value='privileged',
            )
        ]
        if not answers['gpu_enabled']:
            service_docker_choices.insert(
                0,
                questionary.Choice(
                    'Sysbox — Docker inside, still unprivileged/no host access '
                    '(requires sysbox on the host)',
                    value='sysbox',
                ),
            )
        answers['docker_mode'] = questionary.select(
            'In-container Docker for the backing services?',
            choices=service_docker_choices,
            default=service_docker_choices[0].value,
        ).ask()
        if answers['network_firewall'] == 'strict':
            # In-container Docker needs root at runtime, so strict cannot apply there.
            answers['network_firewall'] = 'allowlist'

    return answers, output_dir
