import re

from cdforge.git_ops import host_git_user_email
from cdforge.git_ops import host_git_user_name
from cdforge.project_types.base import ProjectType
from cdforge.project_types.base import Question


def _slugify(raw: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', raw.strip()).strip('_').lower()
    return slug or 'project'


DJANGO_DRF = ProjectType(
    id='django_drf',
    label='Django REST Framework API',
    description='A Django REST Framework API project with pytest-django and drf-spectacular.',
    base_image='mcr.microsoft.com/devcontainers/python:1-3.12-bookworm',
    remote_user='vscode',
    extra_apt_packages=['libpq-dev', 'postgresql-client'],
    questions=[
        Question(
            key='django_project_slug',
            prompt='Django config package name',
            kind='text',
            help_text='Holds settings.py, urls.py, wsgi.py, asgi.py.',
        ),
        Question(
            key='initial_app_name',
            prompt='Initial Django app name',
            kind='text',
            default='core',
        ),
        Question(
            key='database',
            prompt='Database backend',
            kind='select',
            choices=['postgres', 'sqlite'],
            default='postgres',
        ),
        Question(
            key='auth_method',
            prompt='API authentication method',
            kind='select',
            choices=['simplejwt', 'session'],
            default='simplejwt',
        ),
        Question(
            key='include_celery',
            prompt='Include Celery + Redis for background tasks?',
            kind='confirm',
            default=False,
        ),
        Question(
            key='api_docs',
            prompt='API documentation',
            kind='select',
            choices=['drf-spectacular', 'none'],
            default='drf-spectacular',
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
    if not answers.get('django_project_slug'):
        derived['django_project_slug'] = _slugify(project_name) + '_config'
    return derived
