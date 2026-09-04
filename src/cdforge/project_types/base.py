from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any

from cdforge.paths import PROJECT_TYPES_TEMPLATE_DIR


@dataclass(frozen=True)
class Question:
    key: str
    prompt: str
    kind: str = 'text'
    default: Any = None
    choices: list[str] = field(default_factory=list)
    help_text: str = ''
    default_factory: Callable[[], Any] | None = None

    def resolve_default(self) -> Any:
        if self.default_factory is not None:
            return self.default_factory()
        return self.default


@dataclass(frozen=True)
class ProjectType:
    id: str
    label: str
    description: str
    base_image: str
    remote_user: str
    extra_apt_packages: list[str] = field(default_factory=list)
    extra_features: dict[str, dict[str, Any]] = field(default_factory=dict)
    questions: list[Question] = field(default_factory=list)

    @property
    def template_dir(self) -> Path:
        return PROJECT_TYPES_TEMPLATE_DIR / self.id

    @property
    def scaffold_dir(self) -> Path:
        return self.template_dir / 'template'
