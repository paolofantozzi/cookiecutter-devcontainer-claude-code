from __future__ import annotations

import subprocess
from pathlib import Path


def _git_config(key: str) -> str:
    result = subprocess.run(
        ['git', 'config', '--get', key],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip()


def host_git_user_name() -> str:
    return _git_config('user.name') or 'Your Name'


def host_git_user_email() -> str:
    return _git_config('user.email') or 'you@example.com'


def init_repository(
    project_dir: Path,
    remote_url: str,
    author_name: str = 'Project Scaffold',
    author_email: str = 'scaffold@localhost',
) -> None:
    def run(*args: str) -> None:
        subprocess.run(['git', *args], cwd=project_dir, check=True, capture_output=True, text=True)

    run('init', '-q')
    run('config', 'core.hooksPath', '.githooks')
    run('config', 'user.name', author_name)
    run('config', 'user.email', author_email)
    hook = project_dir / '.githooks' / 'pre-commit'
    if hook.exists():
        hook.chmod(0o755)
    if remote_url:
        run('remote', 'add', 'origin', remote_url)
    run('add', '-A')
    run(
        'commit',
        '-q',
        '--no-verify',
        '-m',
        'chore: scaffold project from claude-devcontainer-forge',
    )
