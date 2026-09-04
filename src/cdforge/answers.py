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
