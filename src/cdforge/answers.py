from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REQUIRED_COMMON_KEYS = ('project_name', 'project_type')


class AnswersError(ValueError):
    pass


def load_answers_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise AnswersError(f'{path} is not valid JSON: {exc}') from exc
    if not isinstance(data, dict):
        raise AnswersError(f'{path} must contain a JSON object')
    return data


def validate_common_answers(data: dict[str, Any]) -> None:
    missing = [key for key in REQUIRED_COMMON_KEYS if not data.get(key)]
    if missing:
        raise AnswersError(f'Missing required answer(s): {", ".join(missing)}')


def validate_answer_compatibility(data: dict[str, Any]) -> None:
    """Reject answer combinations that render a devcontainer that cannot start.

    Called from `build_context`, so it guards every scaffold and adopt path.
    """
    if data.get('gpu_enabled') and data.get('docker_mode') == 'sysbox':
        raise AnswersError(
            "gpu_enabled and docker_mode='sysbox' are incompatible: Sysbox does not "
            'support the NVIDIA container runtime, so a container built with both '
            '--gpus=all and --runtime=sysbox-runc fails to start on the NVIDIA prestart '
            "hook. Use docker_mode='none' (keep the GPU) or 'privileged' (GPU plus "
            'in-container Docker, but no host isolation), or drop the GPU to keep Sysbox.'
        )

    docker_mode = data.get('docker_mode')
    if docker_mode not in ('none', 'sysbox', 'privileged'):
        # Backward compatibility with the older boolean answer.
        docker_mode = 'privileged' if data.get('enable_docker') else 'none'
    if (data.get('database') == 'postgres' or data.get('include_celery')) and docker_mode == 'none':
        raise AnswersError(
            "database='postgres'/include_celery needs a backing-service stack, which is now "
            'run from *inside* the devcontainer (docker compose up -d) rather than as sibling '
            "containers. That requires an in-container Docker daemon, so docker_mode='none' "
            "is rejected: choose 'sysbox' (unprivileged, needs Sysbox on the host) or "
            "'privileged' (full Docker, but removes host isolation), or use database='sqlite' "
            'with no Celery to keep docker_mode=none.'
        )
