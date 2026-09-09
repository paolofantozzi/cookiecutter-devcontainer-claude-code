from cdforge.git_ops import host_git_user_email
from cdforge.git_ops import host_git_user_name
from cdforge.project_types.base import ProjectType
from cdforge.project_types.base import Question

STATIC_SITE = ProjectType(
    id='static_site',
    label='Static website',
    description=(
        'A plain static website: hand-written HTML, CSS and JavaScript with no build '
        'step, framework or package manager. The repository root is the deploy root and '
        'holds nothing but the site itself. Previewed inside the sandboxed devcontainer '
        "with Python's built-in HTTP server."
    ),
    base_image='mcr.microsoft.com/devcontainers/python:1-3.12-bookworm',
    remote_user='vscode',
    # Neither the uv/ruff nor the npm/eslint toolchain: the common templates skip both
    # `post-create` install and the ruff/npm pre-commit steps for this stack.
    stack='static',
    # `python3 -m http.server` for a local preview.
    forward_ports=[8000],
    questions=[
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
