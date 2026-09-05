from cdforge.project_types.base import ProjectType
from cdforge.project_types.data_science import DATA_SCIENCE
from cdforge.project_types.django_drf import DJANGO_DRF
from cdforge.project_types.python_uv_tool import PYTHON_UV_TOOL

PROJECT_TYPES: dict[str, ProjectType] = {
    PYTHON_UV_TOOL.id: PYTHON_UV_TOOL,
    DJANGO_DRF.id: DJANGO_DRF,
    DATA_SCIENCE.id: DATA_SCIENCE,
}


def get_project_type(type_id: str) -> ProjectType:
    try:
        return PROJECT_TYPES[type_id]
    except KeyError as exc:
        available = ', '.join(sorted(PROJECT_TYPES))
        raise ValueError(f'Unknown project type {type_id!r}. Available: {available}') from exc
