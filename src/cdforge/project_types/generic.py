from cdforge.project_types.base import ProjectType
from cdforge.project_types.base import Question
from cdforge.project_types.base import database_question

GENERIC = ProjectType(
    id='generic',
    label='Generic workspace',
    description=(
        'A near-empty uv/ruff workspace with Python available — for documents, notes or '
        'scratch code, when none of the other types fit.'
    ),
    base_image='mcr.microsoft.com/devcontainers/python:1-3.12-bookworm',
    remote_user='vscode',
    extra_apt_packages=['jq'],
    questions=[
        Question(
            key='python_version',
            prompt='Python version available in the devcontainer',
            kind='select',
            choices=['3.11', '3.12', '3.13'],
            default='3.12',
        ),
        database_question(),
    ],
)
