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


def is_git_repository(project_dir: Path) -> bool:
    return (project_dir / '.git').exists()


def configure_hooks_path(project_dir: Path) -> None:
    """Point the repository at .githooks so the generated pre-commit/pre-push hooks
    actually run (git only looks at .git/hooks by default)."""
    subprocess.run(
        ['git', 'config', 'core.hooksPath', '.githooks'],
        cwd=project_dir,
        check=False,
        capture_output=True,
        text=True,
    )


def tracked_changes(project_dir: Path) -> list[str]:
    """Paths of tracked files with uncommitted modifications (untracked files are
    ignored: they are not at risk from a rewrite)."""
    result = subprocess.run(
        ['git', 'status', '--porcelain', '--untracked-files=no'],
        cwd=project_dir,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    return [line[3:] for line in result.stdout.splitlines() if line.strip()]


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
