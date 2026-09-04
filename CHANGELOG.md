# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-09-04

### Security

- `devcontainer.json`'s `name` is now JSON-escaped (`| tojson`) so a crafted project name
  can no longer break out of the string literal and inject arbitrary devcontainer keys
  (e.g. `runArgs`/`mounts`/`privileged`), which would have run on the host at container
  build/rebuild time.

## [0.1.0] - 2026-09-04

### Added

- `cdforge new` scaffolds a VS Code devcontainer project with a sandboxed Claude Code
  inside: isolated Docker-in-Docker, a bind-mounted `~/.claude` config directory so login
  and memory persist per-project without leaking into git, optional GPU passthrough, and
  `permissions.deny` blocking `git push`.
- Two project types: `python_uv_tool` (a `uv`-managed Python CLI) and `django_drf` (a
  Django REST Framework API with pytest-django, optional Postgres/Redis/Celery via
  `docker-compose.yml`, JWT or session auth, and optional drf-spectacular docs).
- A mandatory `project-governance` skill plus a per-type conventions skill
  (`python-uv-conventions` / `django-drf-conventions`) are always included in every
  generated project; four optional skills (`commit-craftsman`, `dependency-updater`,
  `security-audit-helper`, `api-docs-writer`) can be selected at scaffold time.
- Every generated project ships a `.githooks/pre-commit` hook that runs `ruff` and the
  test suite before a commit is accepted.
- `cdforge new --answers-file` / `--non-interactive` for scripted, non-interactive
  scaffolding; `cdforge list-types` and `cdforge list-skills` for introspection.
