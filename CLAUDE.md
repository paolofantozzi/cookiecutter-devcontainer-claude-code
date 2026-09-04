# CLAUDE.md

Guidance for working in this repository. Keep this file accurate: update it whenever
architecture, conventions, or the development workflow change.

## What this is

`cdforge` is a cookiecutter-style CLI that scaffolds new projects, each shipping a VS Code
devcontainer with Claude Code running *inside* it, sandboxed so it can only reach the
project's own folder on the host. See `README.md` for user-facing usage and the design
rationale documented in the templates themselves.

## Architecture

- `src/cdforge/cli.py` — Typer app (`new`, `list-types`, `list-skills`).
- `src/cdforge/wizard.py` — interactive prompts (questionary) for the common + per-type
  questions.
- `src/cdforge/answers.py` — loads/validates a JSON answers file (`--answers-file`, used by
  both scripted runs and the test suite).
- `src/cdforge/context_builder.py` — merges answers with each project type's derived
  defaults into the Jinja rendering context.
- `src/cdforge/renderer.py` — walks a template tree, rendering both filenames and file
  contents through Jinja2, stripping the `.j2` suffix, and skipping a file entirely when it
  renders to blank (used for conditionally-omitted files like `docker-compose.yml` or
  `celery.py`; every file that must always exist has non-blank content even in its "off"
  branch, e.g. a leading docstring).
- `src/cdforge/scaffold.py` — orchestrates a full scaffold: render, create the
  `.devcontainer/claude-home/` placeholder, best-effort `ruff format` the output so the
  initial commit is already canonically formatted, then `git init` + commit.
- `src/cdforge/project_types/` — one module per project type (`base.py` defines the
  `ProjectType`/`Question` dataclasses and the registry). Adding a new project type means
  adding a module here plus a `templates/project_types/<id>/` tree.
- `src/cdforge/skills_catalog.py` — the OPTIONAL skills catalog (mandatory skills live
  directly inside `templates/common/.claude/skills/` and
  `templates/project_types/<id>/template/.claude/skills/`, since they are simply part of
  every generated project's file tree).
- `src/cdforge/templates/` — the actual template trees; see the `common/` vs
  `project_types/<id>/template/` split below.

## Template tree layout

- `templates/common/` mirrors a generated project's root exactly (`.devcontainer/`,
  `.claude/`, `.githooks/`, `CLAUDE.md.j2`, `README.md.j2`, ...) and is rendered into every
  project regardless of type.
- `templates/project_types/<id>/template/` also mirrors the output root (its own
  `.devcontainer/Dockerfile.j2`, `pyproject.toml.j2`, source tree, ...) and is rendered on
  top of `common/`.
- `templates/project_types/<id>/*.fragment.*.j2` (e.g. `CLAUDE.fragment.md.j2`,
  `precommit.fragment.sh.j2`) live *outside* `template/` — they are never rendered as
  standalone output files, only pulled in via `{% include %}` from a `common/` template, so
  a single common file (`CLAUDE.md.j2`, `.githooks/pre-commit.j2`) can carry a
  type-specific section.
- `templates/skills/optional/<id>/` — the optional skills catalog.

A path segment containing `{{ ... }}` (e.g. `src/{{package_import_name}}/`) is rendered by
the same Jinja pass as file contents, so directory/file names can depend on the answers.

## Sandboxing decisions worth preserving

These were deliberate, researched choices — see git history / the plan this was built from
for the full reasoning if changing them:

- `~/.claude` is bind-mounted from `.devcontainer/claude-home/` **inside the project repo**
  (gitignored), not a Docker named volume, so login/memory live per-project on disk as
  requested, and `CLAUDE_CONFIG_DIR` is set to that same path (required — Claude Code's
  `~/.claude.json` OAuth session lives outside `~/.claude` unless redirected).
- `permissions.defaultMode: "auto"` is seeded into that mounted directory's
  `settings.json` (i.e. **user-scope** settings) by `post-create.sh`, once, only if the
  file doesn't already exist. It cannot be set from the project's own `.claude/settings.json`
  — Claude Code ignores `auto`/`bypassPermissions` there by design.
- Docker-in-Docker (`ghcr.io/devcontainers/features/docker-in-docker:2`) gives an isolated
  nested daemon instead of mounting the host's `/var/run/docker.sock`, which would break
  the "no host access" guarantee.
- GPU (`runArgs: ["--gpus=all"]`) is scoped to the devcontainer process itself; nested
  containers started via the isolated Docker-in-Docker daemon do not get GPU passthrough.

## Language and style

- English only, everywhere (code, comments, commits, docs).
- Dependencies managed with `uv`; run everything via `uv run ...`.
- `ruff` enforces style: single-quoted strings, one import per line and sorted
  (`force-single-line = true`) — never `from x import a, b`.

## Workflow

- Keep this file, `README.md`, and `CHANGELOG.md` in sync with what the tool actually does.
- Bump `[project].version` in `pyproject.toml` and add a `CHANGELOG.md` entry for every
  notable change, in the same commit as the change.
- Commit each feature/fix on its own with a Conventional Commit message. Never `git push`.
- `.githooks/pre-commit` (installed via `git config core.hooksPath .githooks`) runs
  `ruff check`, `ruff format --check`, and `pytest` before a commit is accepted.
- After touching a template, manually scaffold a project from it and run `uv sync`,
  `ruff check`, `ruff format --check`, and `pytest` *inside the generated project* —
  the test suite only checks file presence/content, not that generated Python/Django code
  actually runs; that has caught real bugs before (an `[build-system]`/`uv_build` mismatch
  for the Django app-layout project, and Django's `makemigrations` not auto-detecting a
  brand-new unmigrated app unless named explicitly, fixed by shipping a checked-in initial
  migration).
