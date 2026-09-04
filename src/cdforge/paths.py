from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATES_ROOT = PACKAGE_ROOT / 'templates'
COMMON_TEMPLATE_DIR = TEMPLATES_ROOT / 'common'
OPTIONAL_SKILLS_DIR = TEMPLATES_ROOT / 'skills' / 'optional'
PROJECT_TYPES_TEMPLATE_DIR = TEMPLATES_ROOT / 'project_types'
