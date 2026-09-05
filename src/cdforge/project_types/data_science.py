import re

from cdforge.git_ops import host_git_user_email
from cdforge.git_ops import host_git_user_name
from cdforge.project_types.base import ProjectType
from cdforge.project_types.base import Question

# The three cumulative dependency stacks this type can install.
STACKS = ('analysis', 'deep-learning', 'transformers')
TORCH_STACKS = ('deep-learning', 'transformers')


def _slugify_package_name(raw: str) -> str:
    slug = re.sub(r'[^a-zA-Z0-9]+', '_', raw.strip()).strip('_').lower()
    return slug or 'analysis'


DATA_SCIENCE = ProjectType(
    id='data_science',
    label='Data science & ML notebooks',
    description=(
        'Jupyter notebooks plus a reusable uv-managed package for data analysis, '
        'scikit-learn / PyTorch model training and transformer fine-tuning.'
    ),
    base_image='mcr.microsoft.com/devcontainers/python:1-3.12-bookworm',
    remote_user='vscode',
    # git-lfs is how model weights and large datasets travel (Hugging Face repos are
    # git-lfs repos); jq keeps notebook JSON inspectable from a shell.
    extra_apt_packages=['git-lfs', 'jq'],
    # JupyterLab, when started by hand inside the container.
    forward_ports=[8888],
    vscode_extensions=[
        'ms-toolsai.jupyter',
        'ms-python.python',
        'charliermarsh.ruff',
    ],
    # Model/dataset hubs this kind of project fetches from, added to the egress allowlist
    # when the firewall is on. Anything else (a tracking server, Kaggle, an internal
    # mirror) goes in .devcontainer/firewall-allow.txt on the host.
    extra_allowed_domains=[
        'huggingface.co',
        'cdn-lfs.huggingface.co',
        'cdn-lfs-us-1.hf.co',
        'download.pytorch.org',
    ],
    questions=[
        Question(
            key='package_import_name',
            prompt='Python import package name',
            kind='text',
            help_text='The src/<name> package the notebooks import their shared code from.',
        ),
        Question(
            key='python_version',
            prompt='Minimum Python version',
            kind='select',
            choices=['3.11', '3.12', '3.13'],
            default='3.12',
        ),
        Question(
            key='ml_stack',
            prompt='Which stack should be installed?',
            kind='select',
            choices=list(STACKS),
            default='analysis',
            help_text=(
                'analysis: numpy/pandas/matplotlib/seaborn/scikit-learn. '
                'deep-learning: + PyTorch. transformers: + Hugging Face '
                'transformers/datasets/accelerate/evaluate.'
            ),
        ),
        Question(
            key='compute_target',
            prompt='PyTorch build to install',
            kind='select',
            choices=['cpu', 'cuda'],
            default='cpu',
            help_text=(
                'cuda installs the default (CUDA-enabled) PyPI wheels and needs GPU '
                'passthrough plus the NVIDIA container toolkit on the host; cpu pins the '
                'much smaller CPU-only wheels. Ignored by the analysis stack.'
            ),
        ),
        Question(
            key='experiment_tracking',
            prompt='Experiment tracking',
            kind='select',
            choices=['mlflow', 'wandb', 'none'],
            default='mlflow',
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
    """Fill in what the answers imply. `include_torch`/`include_transformers` are not
    questions: they are the template-facing reading of `ml_stack`, kept here so a single
    place decides what each stack means."""
    project_name = answers.get('project_name', '')
    stack = answers.get('ml_stack') or 'analysis'
    derived = {
        'include_torch': stack in TORCH_STACKS,
        'include_transformers': stack == 'transformers',
    }
    if not answers.get('package_import_name'):
        derived['package_import_name'] = _slugify_package_name(project_name)
    if not answers.get('compute_target'):
        # A project scaffolded with GPU passthrough almost certainly wants the CUDA wheels.
        derived['compute_target'] = 'cuda' if answers.get('gpu_enabled') else 'cpu'
    return derived
