import re

from cdforge.git_ops import host_git_user_email
from cdforge.git_ops import host_git_user_name
from cdforge.project_types.base import ProjectType
from cdforge.project_types.base import Question


def _slugify_app_name(raw: str) -> str:
    """An npm/Angular workspace name: lowercase, dash-separated, no leading digit."""
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', raw.strip()).strip('-').lower()
    slug = re.sub(r'^[0-9]+', '', slug).strip('-')
    return slug or 'app'


ANGULAR = ProjectType(
    id='angular',
    label='Angular frontend',
    description=(
        'An Angular single-page app: standalone components, the Angular CLI, ESLint + '
        'Prettier, and Karma/Jasmine unit tests, all running inside the sandboxed '
        'devcontainer with npm.'
    ),
    base_image='mcr.microsoft.com/devcontainers/typescript-node:1-22-bookworm',
    remote_user='node',
    stack='node',
    # jq keeps package.json/angular.json inspectable from a shell; chromium is what
    # `ng test` (Karma) drives in headless mode.
    extra_apt_packages=['jq', 'chromium'],
    # `ng serve` / `npm start`.
    forward_ports=[4200],
    vscode_extensions=[
        'angular.ng-template',
        'dbaeumer.vscode-eslint',
        'esbenp.prettier-vscode',
    ],
    questions=[
        Question(
            key='app_name',
            prompt='Angular workspace / app name',
            kind='text',
            help_text='The project name in angular.json and package.json (npm-style: my-app).',
        ),
        Question(
            key='node_version',
            prompt='Minimum Node.js version',
            kind='select',
            choices=['20', '22'],
            default='22',
            help_text='Written to package.json engines. The devcontainer ships Node 22.',
        ),
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
    if not answers.get('app_name'):
        derived['app_name'] = _slugify_app_name(project_name)
    return derived
