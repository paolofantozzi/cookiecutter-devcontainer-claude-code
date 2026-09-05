import json
from pathlib import Path

from cdforge.answers import load_answers_file
from cdforge.scaffold import scaffold_project

FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_data_science.json'


def _scaffold(tmp_path: Path, **overrides: object) -> Path:
    answers = load_answers_file(FIXTURE)
    answers.update(overrides)
    suffix = '-'.join(str(value) for value in overrides.values())
    name = f'churn-lab-{suffix}' if overrides else 'churn-lab'
    return scaffold_project(answers, tmp_path / name)


def test_expected_files_are_created(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    for relative in [
        '.devcontainer/devcontainer.json',
        '.devcontainer/Dockerfile',
        '.claude/skills/notebook-ml-conventions/SKILL.md',
        '.githooks/pre-commit',
        'CLAUDE.md',
        'README.md',
        'LICENSE',
        'pyproject.toml',
        'notebooks/01-explore-data.ipynb',
        'notebooks/02-train-model.ipynb',
        'src/churn_lab/config.py',
        'src/churn_lab/data.py',
        'src/churn_lab/seeding.py',
        'src/churn_lab/tracking.py',
        'tests/test_config.py',
        'tests/test_data.py',
        'tests/test_seeding.py',
        'data/.gitkeep',
        'models/.gitkeep',
    ]:
        assert (project_dir / relative).exists(), f'missing {relative}'


def test_notebooks_are_valid_and_output_free(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    for name in ('01-explore-data.ipynb', '02-train-model.ipynb'):
        notebook = json.loads((project_dir / 'notebooks' / name).read_text())
        assert notebook['nbformat'] == 4
        assert notebook['cells'], f'{name} has no cells'
        for cell in notebook['cells']:
            # Committed notebooks carry no outputs; the templates must not ship any either.
            assert cell.get('outputs', []) == []
            assert cell.get('execution_count') is None


def test_notebook_titles_are_json_escaped(tmp_path: Path) -> None:
    # The project name reaches the notebook JSON as a string literal, so a quote in it must
    # not be able to break the document (or inject cells).
    project_dir = _scaffold(tmp_path, project_name='Quote " Lab')

    notebook = json.loads((project_dir / 'notebooks' / '01-explore-data.ipynb').read_text())

    assert 'Quote " Lab' in ''.join(notebook['cells'][0]['source'])


def test_analysis_stack_installs_neither_torch_nor_transformers(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    pyproject = (project_dir / 'pyproject.toml').read_text()

    assert 'scikit-learn' in pyproject
    assert 'torch' not in pyproject
    assert 'transformers' not in pyproject
    # training.py renders blank for this stack and is therefore not written at all.
    assert not (project_dir / 'src' / 'churn_lab' / 'training.py').exists()
    assert not (project_dir / 'tests' / 'test_training.py').exists()


def test_deep_learning_stack_adds_torch_and_the_training_module(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path, ml_stack='deep-learning')

    pyproject = (project_dir / 'pyproject.toml').read_text()
    training = (project_dir / 'src' / 'churn_lab' / 'training.py').read_text()

    assert '"torch>=' in pyproject
    assert 'transformers' not in pyproject
    assert 'def train(' in training
    assert 'fine_tune_text_classifier' not in training
    assert (project_dir / 'tests' / 'test_training.py').exists()


def test_transformers_stack_adds_the_hugging_face_stack(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path, ml_stack='transformers')

    pyproject = (project_dir / 'pyproject.toml').read_text()
    training = (project_dir / 'src' / 'churn_lab' / 'training.py').read_text()

    assert '"transformers>=' in pyproject
    assert '"datasets>=' in pyproject
    assert 'fine_tune_text_classifier' in training


def test_cpu_target_pins_the_cpu_only_pytorch_index(tmp_path: Path) -> None:
    # The default PyPI torch wheels bundle CUDA and are several GB; a CPU project must not
    # pay for that.
    project_dir = _scaffold(tmp_path, ml_stack='deep-learning')

    pyproject = (project_dir / 'pyproject.toml').read_text()

    assert 'https://download.pytorch.org/whl/cpu' in pyproject
    assert 'torch = [{ index = "pytorch-cpu" }]' in pyproject


def test_cuda_target_uses_the_default_wheels(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path, ml_stack='deep-learning', compute_target='cuda')

    pyproject = (project_dir / 'pyproject.toml').read_text()

    assert 'download.pytorch.org' not in pyproject


def test_tracking_module_follows_the_chosen_backend(tmp_path: Path) -> None:
    mlflow_project = _scaffold(tmp_path)
    wandb_project = _scaffold(tmp_path, experiment_tracking='wandb')
    untracked_project = _scaffold(tmp_path, experiment_tracking='none')

    assert 'import mlflow' in (mlflow_project / 'src' / 'churn_lab' / 'tracking.py').read_text()
    assert '"mlflow>=' in (mlflow_project / 'pyproject.toml').read_text()
    assert 'import wandb' in (wandb_project / 'src' / 'churn_lab' / 'tracking.py').read_text()
    # No backend: the module renders blank and is skipped entirely rather than shipping a stub.
    assert not (untracked_project / 'src' / 'churn_lab' / 'tracking.py').exists()


def test_devcontainer_forwards_jupyter_and_adds_the_notebook_extension(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    config = json.loads((project_dir / '.devcontainer' / 'devcontainer.json').read_text())

    assert config['forwardPorts'] == [8888]
    assert 'ms-toolsai.jupyter' in config['customizations']['vscode']['extensions']
    # Still an ordinary unprivileged container: the notebook type changes nothing there.
    assert 'runArgs' not in config
    assert 'ghcr.io/devcontainers/features/docker-in-docker:2' not in config['features']


def test_ruff_and_the_hook_cover_notebooks(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    pyproject = (project_dir / 'pyproject.toml').read_text()
    hook = (project_dir / '.githooks' / 'pre-commit').read_text()

    assert 'extend-include = ["*.ipynb"]' in pyproject
    assert 'nbstripout' in pyproject
    # Outputs are stripped from staged notebooks and the stripped files are re-staged.
    assert 'nbstripout' in hook
    assert 'git add' in hook


def test_gitignore_keeps_data_and_weights_out_of_git(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path)

    gitignore = (project_dir / '.gitignore').read_text()

    for entry in ('/data/*', '!/data/.gitkeep', '/models/*', 'mlruns/', '.ipynb_checkpoints/'):
        assert entry in gitignore, f'missing {entry}'


def test_firewall_allowlists_the_model_hubs(tmp_path: Path) -> None:
    project_dir = _scaffold(tmp_path, network_firewall='allowlist')

    firewall = (project_dir / '.devcontainer' / 'init-firewall.sh').read_text()

    assert "'huggingface.co'" in firewall
    assert "'download.pytorch.org'" in firewall
    # The base allowlist is still there.
    assert "'api.anthropic.com'" in firewall


def test_package_name_and_seed_defaults_are_derived_from_the_project_name(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    del answers['package_import_name']
    del answers['compute_target']
    answers['gpu_enabled'] = True
    answers['ml_stack'] = 'deep-learning'

    project_dir = scaffold_project(answers, tmp_path / 'derived')

    assert (project_dir / 'src' / 'churn_lab' / 'config.py').exists()
    # GPU passthrough implies the CUDA wheels when the answer was not given explicitly.
    assert 'download.pytorch.org' not in (project_dir / 'pyproject.toml').read_text()
