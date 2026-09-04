# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.10] - 2026-09-05

### Fixed

- Privileged `docker-in-docker` mode now sets `"overrideCommand": false` in the generated
  `devcontainer.json`. Without it the Dev Containers CLI replaces the container command and
  the docker-in-docker feature's entrypoint — which starts `dockerd` — never runs, so
  `docker` inside the container did not work. Found by the end-to-end harness.

## [0.1.9] - 2026-09-05

### Fixed

- The generated `python_uv_tool` `pyproject.toml` now declares
  `[tool.uv.build-backend] module-name`, so choosing a package import name different from the
  project name no longer breaks the build (`uv sync` previously failed with "Expected a Python
  module at src/<project_name>/__init__.py"). Found by the new end-to-end harness.

## [0.1.8] - 2026-09-05

### Fixed

- The generated `.devcontainer/Dockerfile` now removes the upstream base image's third-party
  `yarn` apt source before `apt-get update`. That source's signing key periodically expires
  (`NO_PUBKEY`), which made `apt-get update` fail with exit code 100 and broke the devcontainer
  image build for every generated project. These projects don't use yarn, so the source is
  simply dropped. Verified by building the generated image end-to-end.

## [0.1.7] - 2026-09-05

### Added

- New **Sysbox** in-container Docker mode. The `docker_mode` answer now offers
  `none` (default), `sysbox`, and `privileged`. In `sysbox` mode the devcontainer runs with
  `--runtime=sysbox-runc` (or `runtime: sysbox-runc` on the compose `app` service) and starts
  its own Docker daemon via `.devcontainer/docker-start.sh`, so Claude Code can build/run
  containers and use Testcontainers while the container stays **unprivileged with no host
  access**. Requires Sysbox installed on a Linux host. The wizard now asks for the mode and
  the generated README/CLAUDE document the host prerequisite. The older boolean
  `enable_docker` still maps to `privileged`.

  Note: the Sysbox path is validated by rendering/config checks only; running it needs a
  sysbox-enabled host, so verify with a real container rebuild there.

## [0.1.6] - 2026-09-05

### Fixed

- The generated `python_uv_tool` CLI now defines an `@app.callback()`, so `tool version`
  works. Without it, a single-command Typer app collapses and invoking the command exits
  with code 2 — the generated project's own `test_version_command_prints_installed_version`
  test failed. (Found by actually running the generated project, per the workflow note.)

## [0.1.5] - 2026-09-05

### Documentation

- Rewrote the sandboxing claims in this project's `README.md`/`CLAUDE.md` and in the
  generated project's `README.md`/`CLAUDE.md` to describe the real, post-hardening model
  (unprivileged container, read-only `.devcontainer`, sibling services, opt-in privileged
  docker) instead of the old "isolated Docker-in-Docker" framing.
- Added an honest "residual risks" note: the workspace is shared with the host, so files the
  *host* later executes (git hooks, editor tasks, scripts) run with the user's privileges;
  and `enable_docker` is an explicit trade-off that re-introduces host access.

## [0.1.4] - 2026-09-05

### Security

- Hardened the "no push from the container" guardrail, which previously relied on a single
  easily-bypassed `permissions.deny` glob. Added a `.githooks/pre-push` hook that refuses
  pushes, broadened the deny list, and documented in the generated `CLAUDE.md` that these are
  best-effort layers — the actual guarantee is that no push credentials are mounted into the
  container, so a human always pushes from the host.

## [0.1.3] - 2026-09-05

### Security

- The `.devcontainer/` directory is now bind-mounted **read-only** inside the container, so
  Claude Code (or anything else running in it) cannot rewrite `devcontainer.json`, the
  `Dockerfile`, or `post-create.sh`. Those files are executed/trusted by the host's Dev
  Containers tooling at build/rebuild time; making them un-writable from inside removes the
  path where in-container code could arrange to run on the host after a rebuild. The
  `claude-home` config directory stays writable via its own mount.

## [0.1.2] - 2026-09-05

### Security

- **Devcontainers are no longer privileged by default.** The `docker-in-docker` feature —
  which forces the container to run `--privileged`, granting Claude Code inside it access to
  the host kernel and block devices — is no longer included by default. It is now an explicit
  opt-in (`enable_docker`, off by default) whose generated README/CLAUDE.md warn that it
  voids the host-isolation guarantee.
- `django_drf` projects that need Postgres/Redis now use the Dev Containers **Docker Compose**
  workflow: the devcontainer is an ordinary, unprivileged `app` service and the databases run
  as **sibling** containers reachable by hostname (`db`, `redis`) over a private compose
  network — never on the host filesystem, and without any in-container Docker daemon. Service
  URLs in `settings.py`/`.env.example` now use those hostnames instead of `localhost`.

### Changed

- GPU passthrough for compose-based projects is expressed as a device reservation on the
  `app` service instead of a host `runArgs` entry.

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
