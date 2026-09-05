from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

from cdforge.skills_catalog import OPTIONAL_SKILLS


def _read_pyproject(project_dir: Path) -> dict[str, Any]:
    path = project_dir / 'pyproject.toml'
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding='utf-8'))
    except (tomllib.TOMLDecodeError, OSError):
        return {}


def _dependency_names(pyproject: dict[str, Any]) -> str:
    """All dependency strings (project + dependency groups) lowercased, joined, so
    membership can be tested with a plain substring check."""
    chunks: list[str] = []
    project = pyproject.get('project', {})
    if isinstance(project, dict):
        chunks += [str(dep) for dep in project.get('dependencies', []) or []]
        optional = project.get('optional-dependencies', {}) or {}
        if isinstance(optional, dict):
            for deps in optional.values():
                chunks += [str(dep) for dep in deps or []]
    groups = pyproject.get('dependency-groups', {}) or {}
    if isinstance(groups, dict):
        for deps in groups.values():
            chunks += [str(dep) for dep in deps or []]
    return ' '.join(chunks).lower()


def _has_notebooks(project_dir: Path) -> bool:
    notebooks = project_dir / 'notebooks'
    if notebooks.is_dir() and any(notebooks.glob('*.ipynb')):
        return True
    return any(project_dir.glob('*.ipynb'))


def _detect_project_type(project_dir: Path, deps: str) -> str:
    if (project_dir / 'manage.py').exists() or 'django' in deps:
        return 'django_drf'
    # Notebooks, or a stack nobody installs for a CLI tool. Plain pandas/numpy is not
    # enough: a command-line tool may well use them.
    if _has_notebooks(project_dir) or any(
        marker in deps for marker in ('jupyter', 'notebook', 'torch', 'transformers')
    ):
        return 'data_science'
    return 'python_uv_tool'


def _detect_ml_stack(deps: str) -> str:
    if 'transformers' in deps:
        return 'transformers'
    if 'torch' in deps:
        return 'deep-learning'
    return 'analysis'


def _detect_compute_target(project_dir: Path) -> str:
    """PyTorch's CPU-only index is pinned in pyproject.toml; anything else is the default
    (CUDA-enabled) wheel."""
    pyproject = project_dir / 'pyproject.toml'
    if not pyproject.exists():
        return 'cpu'
    try:
        text = pyproject.read_text(encoding='utf-8')
    except OSError:
        return 'cpu'
    return 'cpu' if 'download.pytorch.org/whl/cpu' in text else 'cuda'


def _detect_package_import_name(project_dir: Path) -> str:
    src = project_dir / 'src'
    if src.is_dir():
        for child in sorted(src.iterdir()):
            if child.is_dir() and (child / '__init__.py').exists():
                return child.name
    return ''


def _detect_django_project_slug(project_dir: Path) -> str:
    for child in sorted(project_dir.iterdir()):
        if child.is_dir() and (child / 'settings.py').exists():
            return child.name
    return ''


def _detect_initial_app_name(project_dir: Path) -> str:
    apps_dir = project_dir / 'apps'
    if apps_dir.is_dir():
        for child in sorted(apps_dir.iterdir()):
            if child.is_dir() and (child / 'apps.py').exists():
                return child.name
    return ''


def _detect_devcontainer_answers(project_dir: Path) -> dict[str, Any]:
    path = project_dir / '.devcontainer' / 'devcontainer.json'
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding='utf-8')
    except OSError:
        return {}
    detected: dict[str, Any] = {}
    if 'docker-in-docker' in raw:
        detected['docker_mode'] = 'privileged'
    elif 'sysbox-runc' in raw:
        detected['docker_mode'] = 'sysbox'
    if '--gpus' in raw or '"gpu"' in raw:
        detected['gpu_enabled'] = True
    if 'cdforge-firewall' in raw:
        # The sudoers drop-in only exists in the strict mode, so the Dockerfile tells the
        # two firewall modes apart.
        dockerfile = project_dir / '.devcontainer' / 'Dockerfile'
        strict = dockerfile.exists() and 'sudoers.d' in dockerfile.read_text(encoding='utf-8')
        detected['network_firewall'] = 'strict' if strict else 'allowlist'
    return detected


def _detect_project_name(project_dir: Path, pyproject: dict[str, Any]) -> str:
    project = pyproject.get('project', {})
    if isinstance(project, dict) and project.get('name'):
        return str(project['name'])
    return project_dir.resolve().name


def _detect_python_version(pyproject: dict[str, Any]) -> str:
    project = pyproject.get('project', {})
    requires = str(project.get('requires-python', '')) if isinstance(project, dict) else ''
    match = re.search(r'3\.(\d+)', requires)
    return f'3.{match.group(1)}' if match else ''


def _detect_authors(pyproject: dict[str, Any]) -> dict[str, Any]:
    project = pyproject.get('project', {})
    authors = project.get('authors', []) if isinstance(project, dict) else []
    if authors and isinstance(authors[0], dict):
        detected = {}
        if authors[0].get('name'):
            detected['author_name'] = str(authors[0]['name'])
        if authors[0].get('email'):
            detected['author_email'] = str(authors[0]['email'])
        return detected
    return {}


def detect_answers(project_dir: Path) -> dict[str, Any]:
    """Best-effort answers inferred from an existing project, used to pre-fill the
    wizard when adopting it. Only keys we could actually infer are returned."""
    pyproject = _read_pyproject(project_dir)
    deps = _dependency_names(pyproject)
    project_type = _detect_project_type(project_dir, deps)

    detected: dict[str, Any] = {
        'project_name': _detect_project_name(project_dir, pyproject),
        'project_type': project_type,
    }
    detected.update(_detect_authors(pyproject))
    detected.update(_detect_devcontainer_answers(project_dir))

    if project_type == 'data_science':
        package = _detect_package_import_name(project_dir)
        if package:
            detected['package_import_name'] = package
        python_version = _detect_python_version(pyproject)
        if python_version:
            detected['python_version'] = python_version
        detected['ml_stack'] = _detect_ml_stack(deps)
        detected['compute_target'] = _detect_compute_target(project_dir)
        if 'mlflow' in deps:
            detected['experiment_tracking'] = 'mlflow'
        elif 'wandb' in deps:
            detected['experiment_tracking'] = 'wandb'
        else:
            detected['experiment_tracking'] = 'none'
    elif project_type == 'python_uv_tool':
        package = _detect_package_import_name(project_dir)
        if package:
            detected['package_import_name'] = package
        scripts = pyproject.get('project', {}).get('scripts', {})
        if isinstance(scripts, dict) and scripts:
            detected['cli_command_name'] = next(iter(scripts))
        python_version = _detect_python_version(pyproject)
        if python_version:
            detected['python_version'] = python_version
        detected['include_mypy'] = 'mypy' in deps
    else:
        slug = _detect_django_project_slug(project_dir)
        if slug:
            detected['django_project_slug'] = slug
        app = _detect_initial_app_name(project_dir)
        if app:
            detected['initial_app_name'] = app
        detected['database'] = 'postgres' if ('psycopg' in deps or 'postgres' in deps) else 'sqlite'
        detected['include_celery'] = 'celery' in deps
        detected['auth_method'] = 'simplejwt' if 'simplejwt' in deps else 'session'
        detected['api_docs'] = 'drf-spectacular' if 'drf-spectacular' in deps else 'none'

    return detected


def detect_optional_skills(project_dir: Path) -> list[str]:
    """Optional skills already present in the project, so adopting it keeps them."""
    skills_dir = project_dir / '.claude' / 'skills'
    if not skills_dir.is_dir():
        return []
    return [skill.id for skill in OPTIONAL_SKILLS if (skills_dir / skill.id).is_dir()]


def detect_git_remote(project_dir: Path) -> str:
    result = subprocess.run(
        ['git', 'remote', 'get-url', 'origin'],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()
