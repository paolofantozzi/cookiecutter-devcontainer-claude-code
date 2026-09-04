from __future__ import annotations

import re
from datetime import UTC
from datetime import datetime
from typing import Any

from cdforge import __version__
from cdforge.project_types import django_drf
from cdforge.project_types import python_uv_tool
from cdforge.project_types.base import ProjectType

_DERIVE_DEFAULTS = {
    'python_uv_tool': python_uv_tool.derive_defaults,
    'django_drf': django_drf.derive_defaults,
}


def slugify(raw: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', raw.strip()).strip('-').lower()
    return slug or 'project'


def build_context(
    answers: dict[str, Any],
    project_type: ProjectType,
    optional_skill_ids: list[str],
) -> dict[str, Any]:
    context: dict[str, Any] = dict(answers)
    derive = _DERIVE_DEFAULTS.get(project_type.id)
    if derive is not None:
        for key, value in derive(answers).items():
            context.setdefault(key, value)

    for question in project_type.questions:
        context.setdefault(question.key, question.resolve_default())

    context.setdefault('project_slug', slugify(context['project_name']))
    context.setdefault('git_remote_url', '')
    context.setdefault('gpu_enabled', False)
    # Opt-in: adds the docker-in-docker feature, which forces the devcontainer to run
    # `--privileged`. That breaks host isolation, so it is off by default.
    context.setdefault('enable_docker', False)

    # Projects that need backing services (Postgres/Redis) get them as *sibling*
    # containers via the Dev Containers Docker Compose workflow: the devcontainer itself
    # stays an ordinary, unprivileged container that can only reach the workspace, and the
    # services live on the compose network (reachable by hostname, never on the host FS).
    context['use_compose'] = bool(
        project_type.id == 'django_drf'
        and (context.get('database') == 'postgres' or context.get('include_celery'))
    )

    context['project_type'] = project_type.id
    context['project_type_label'] = project_type.label
    context['remote_user'] = project_type.remote_user
    context['base_image'] = project_type.base_image
    context['extra_apt_packages'] = project_type.extra_apt_packages
    context['extra_features'] = project_type.extra_features
    context['optional_skills'] = optional_skill_ids
    context['cdforge_version'] = __version__
    context['generation_year'] = datetime.now(tz=UTC).year

    return context
