from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from cdforge.paths import OPTIONAL_SKILLS_DIR


@dataclass(frozen=True)
class OptionalSkill:
    id: str
    label: str
    description: str
    applicable_types: tuple[str, ...] = field(default_factory=tuple)

    @property
    def template_dir(self):
        return OPTIONAL_SKILLS_DIR / self.id

    def applies_to(self, project_type_id: str) -> bool:
        return not self.applicable_types or project_type_id in self.applicable_types


OPTIONAL_SKILLS: list[OptionalSkill] = [
    OptionalSkill(
        id='commit-craftsman',
        label='Commit craftsman',
        description='Writes higher-quality Conventional Commit messages and splits mixed changes.',
    ),
    OptionalSkill(
        id='dependency-updater',
        label='Dependency updater',
        description='Periodically checks for outdated dependencies and proposes safe upgrades.',
    ),
    OptionalSkill(
        id='security-audit-helper',
        label='Security audit helper',
        description='Runs dependency vulnerability scans and reviews new code for common risks.',
    ),
    OptionalSkill(
        id='api-docs-writer',
        label='API docs writer',
        description='Keeps the OpenAPI schema and endpoint documentation in sync with the code.',
        applicable_types=('django_drf',),
    ),
]


def skills_for_type(project_type_id: str) -> list[OptionalSkill]:
    return [skill for skill in OPTIONAL_SKILLS if skill.applies_to(project_type_id)]


def get_optional_skill(skill_id: str) -> OptionalSkill:
    for skill in OPTIONAL_SKILLS:
        if skill.id == skill_id:
            return skill
    raise ValueError(f'Unknown skill {skill_id!r}')
