import os
import subprocess
from pathlib import Path

import pytest

from cdforge.answers import load_answers_file
from cdforge.scaffold import scaffold_project

FIXTURE = Path(__file__).parent / 'fixtures' / 'answers_python_uv_tool.json'


def _uv_sync_available(project_dir: Path) -> bool:
    try:
        subprocess.run(
            ['uv', 'sync', '--all-extras'],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=180,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


def test_pre_commit_hook_rejects_a_commit_with_a_failing_test(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    project_dir = scaffold_project(answers, tmp_path / 'widget-tool')

    if not _uv_sync_available(project_dir):
        pytest.skip('uv sync is not available in this sandbox (no network or no uv)')

    test_file = project_dir / 'tests' / 'test_cli.py'
    test_file.write_text(
        test_file.read_text(encoding='utf-8') + '\n\ndef test_deliberately_broken() -> None:\n'
        '    assert False\n',
        encoding='utf-8',
    )

    subprocess.run(['git', 'add', '-A'], cwd=project_dir, check=True)
    result = subprocess.run(
        ['git', 'commit', '-m', 'test: break things on purpose'],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    log = subprocess.run(
        ['git', 'log', '--oneline'], cwd=project_dir, capture_output=True, text=True, check=True
    )
    assert len(log.stdout.strip().splitlines()) == 1


def test_pre_push_hook_blocks_pushes(tmp_path: Path) -> None:
    answers = load_answers_file(FIXTURE)
    project_dir = scaffold_project(answers, tmp_path / 'widget-tool-push')

    hook = project_dir / '.githooks' / 'pre-push'
    assert hook.exists()
    assert os.access(hook, os.X_OK)

    # Point git at the hooks dir (post-create.sh does this in the real container) and add a
    # dummy remote, then confirm a push is refused by the hook.
    subprocess.run(['git', 'config', 'core.hooksPath', '.githooks'], cwd=project_dir, check=True)
    subprocess.run(
        ['git', 'remote', 'add', 'origin', str(tmp_path / 'bare.git')],
        cwd=project_dir,
        check=True,
    )
    subprocess.run(
        ['git', 'init', '--bare', str(tmp_path / 'bare.git')], check=True, capture_output=True
    )

    result = subprocess.run(
        ['git', 'push', 'origin', 'HEAD'],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert 'pushing is disabled' in (result.stderr + result.stdout)
