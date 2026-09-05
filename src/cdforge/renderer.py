from __future__ import annotations

import stat
from pathlib import Path
from typing import Any

import jinja2

from cdforge.paths import COMMON_TEMPLATE_DIR
from cdforge.project_types.base import ProjectType

_EXECUTABLE_NAMES = {
    'pre-commit',
    'pre-push',
    'post-create.sh',
    'docker-start.sh',
    'init-firewall.sh',
}


def build_environment(project_type: ProjectType) -> jinja2.Environment:
    loader = jinja2.ChoiceLoader(
        [
            jinja2.FileSystemLoader(str(project_type.scaffold_dir)),
            jinja2.FileSystemLoader(str(project_type.template_dir)),
            jinja2.FileSystemLoader(str(COMMON_TEMPLATE_DIR)),
        ]
    )
    return jinja2.Environment(
        loader=loader,
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _render_name(env: jinja2.Environment, segment: str, context: dict[str, Any]) -> str:
    if '{{' in segment:
        return env.from_string(segment).render(context)
    return segment


def _iter_template_files(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob('*') if p.is_file())


def render_tree(
    env: jinja2.Environment,
    source_root: Path,
    output_dir: Path,
    context: dict[str, Any],
) -> list[Path]:
    written: list[Path] = []
    for source_file in _iter_template_files(source_root):
        rel = source_file.relative_to(source_root)
        rendered_parts = [_render_name(env, part, context) for part in rel.parts]
        is_template = rendered_parts[-1].endswith('.j2')
        if is_template:
            rendered_parts[-1] = rendered_parts[-1][: -len('.j2')]
        dest_path = output_dir.joinpath(*rendered_parts)

        if is_template:
            template = env.get_template(rel.as_posix())
            content = template.render(context)
            if content.strip() == '':
                continue
        else:
            content = source_file.read_text(encoding='utf-8')

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        dest_path.write_text(content, encoding='utf-8')
        if dest_path.name in _EXECUTABLE_NAMES:
            mode = dest_path.stat().st_mode
            dest_path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        written.append(dest_path)
    return written


def render_optional_skills(
    skill_dirs: list[Path],
    output_dir: Path,
    context: dict[str, Any],
) -> list[Path]:
    written: list[Path] = []
    for skill_dir in skill_dirs:
        dest_root = output_dir / '.claude' / 'skills' / skill_dir.name
        for source_file in _iter_template_files(skill_dir):
            rel = source_file.relative_to(skill_dir)
            is_template = source_file.name.endswith('.j2')
            dest_name = rel.name[: -len('.j2')] if is_template else rel.name
            dest_path = dest_root.joinpath(*rel.parts[:-1], dest_name)
            text = source_file.read_text(encoding='utf-8')
            content = jinja2.Template(text).render(context) if is_template else text
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_text(content, encoding='utf-8')
            written.append(dest_path)
    return written


def render_project(
    project_type: ProjectType,
    context: dict[str, Any],
    output_dir: Path,
    optional_skill_dirs: list[Path] | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    env = build_environment(project_type)
    written = render_tree(env, COMMON_TEMPLATE_DIR, output_dir, context)
    written += render_tree(env, project_type.scaffold_dir, output_dir, context)
    written += render_optional_skills(optional_skill_dirs or [], output_dir, context)
    return written
