from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from pathlib import Path
from typing import Any

from cdforge import __version__

MANIFEST_NAME = '.cdforge.json'


class ManifestError(ValueError):
    pass


def manifest_path(project_dir: Path) -> Path:
    return project_dir / MANIFEST_NAME


def read_manifest(project_dir: Path) -> dict[str, Any] | None:
    """Return the recorded scaffold manifest, or None when the project has none."""
    path = manifest_path(project_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        raise ManifestError(f'{path} is not valid JSON: {exc}') from exc
    if not isinstance(data, dict):
        raise ManifestError(f'{path} must contain a JSON object')
    return data


def read_manifest_answers(project_dir: Path) -> dict[str, Any] | None:
    manifest = read_manifest(project_dir)
    if manifest is None:
        return None
    answers = manifest.get('answers')
    if not isinstance(answers, dict):
        raise ManifestError(f'{manifest_path(project_dir)} has no "answers" object')
    return answers


def write_manifest(project_dir: Path, answers: dict[str, Any]) -> Path:
    """Record the answers a project was generated/aligned from, so a later
    `cdforge adopt` can re-render the managed files without asking again."""
    path = manifest_path(project_dir)
    payload = {
        'cdforge_version': __version__,
        'updated_at': datetime.now(tz=UTC).isoformat(timespec='seconds'),
        'answers': answers,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return path
