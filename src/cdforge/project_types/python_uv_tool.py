import re

from cdforge.git_ops import host_git_user_email
from cdforge.git_ops import host_git_user_name
from cdforge.project_types.base import ProjectType
from cdforge.project_types.base import Question
from cdforge.project_types.base import database_question


def _slugify_package_name(raw: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', raw.strip()).strip('_').lower()
    return slug or 'my_tool'


PYTHON_UV_TOOL = ProjectType(
    id='python_uv_tool',
    label='Python uv tool',
    description='A command-line Python tool managed with uv, linted and formatted with ruff.',
    base_image='mcr.microsoft.com/devcontainers/python:1-3.12-bookworm',
    remote_user='vscode',
    extra_apt_packages=['jq'],
    questions=[
        Question(
            key='package_import_name',
            prompt='Python import package name',
            kind='text',
            help_text='Used as the src/<name> package and the import name.',
        ),
        Question(
            key='cli_command_name',
            prompt='CLI command name',
            kind='text',
            help_text='The command users type in a shell to run the tool.',
        ),
        Question(
            key='python_version',
            prompt='Minimum Python version',
            kind='select',
            choices=['3.11', '3.12', '3.13'],
            default='3.12',
        ),
        Question(
            key='include_mypy',
            prompt='Include mypy for static type checking?',
            kind='confirm',
            default=True,
        ),
        database_question(),
        Question(
            key='license_id',
            prompt='License',
            kind='select',
            choices=['MIT', 'Apache-2.0', 'None'],
            default='MIT',
        ),
        Question(
            key='author_name',
            prompt='Author name',
            kind='text',
            default_factory=host_git_user_name,
        ),
        Question(
            key='author_email',
            prompt='Author email',
            kind='text',
            default_factory=host_git_user_email,
        ),
    ],
)


def derive_defaults(answers: dict) -> dict:
    project_name = answers.get('project_name', '')
    derived = {}
    if not answers.get('package_import_name'):
        derived['package_import_name'] = _slugify_package_name(project_name)
    if not answers.get('cli_command_name'):
        derived['cli_command_name'] = derived.get(
            'package_import_name', answers.get('package_import_name', '')
        ).replace('_', '-')
    return derived
