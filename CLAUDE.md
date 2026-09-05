# CLAUDE.md

Guidance for working in this repository. Keep this file accurate: update it whenever
architecture, conventions, or the development workflow change.

## What this is

`cdforge` is a cookiecutter-style CLI that scaffolds new projects, each shipping a VS Code
devcontainer with Claude Code running *inside* it, sandboxed so it can only reach the
project's own folder on the host. See `README.md` for user-facing usage and the design
rationale documented in the templates themselves.

## Architecture

- `src/cdforge/cli.py` — Typer app (`new`, `adopt`, `list-types`, `list-skills`).
- `src/cdforge/wizard.py` — interactive prompts (questionary) for the common + per-type
  questions; `defaults=` pre-fills every prompt (used by `adopt`) and `ask_output_dir=False`
  skips the output-directory question when the target already exists.
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
  `.devcontainer/claude-home/` placeholder, write `.cdforge.json`, best-effort `ruff format`
  the output so the initial commit is already canonically formatted, then `git init` +
  commit.
- `src/cdforge/adopt.py` — aligns an **existing** project with the template (see below).
- `src/cdforge/detect.py` — best-effort inference of the answers for an existing project
  (project type, package/Django layout, dependencies, author, current devcontainer settings).
- `src/cdforge/manifest.py` — reads/writes `.cdforge.json`, the record of the answers a
  project was generated or aligned from.
- `src/cdforge/project_types/` — one module per project type (`base.py` defines the
  `ProjectType`/`Question` dataclasses and the registry). Adding a new project type means
  adding a module here plus a `templates/project_types/<id>/` tree. Besides the questions, a
  `ProjectType` can declare `extra_apt_packages`, `extra_features`, `forward_ports`,
  `vscode_extensions` (rendered into `devcontainer.json`) and `extra_allowed_domains` (added
  to the egress allowlist when the firewall is on); `context_builder.py` copies all of them
  into the context.
- `src/cdforge/skills_catalog.py` — the OPTIONAL skills catalog (mandatory skills live
  directly inside `templates/common/.claude/skills/` and
  `templates/project_types/<id>/template/.claude/skills/`, since they are simply part of
  every generated project's file tree).
- `src/cdforge/templates/` — the actual template trees; see the `common/` vs
  `project_types/<id>/template/` split below.

## Adoption of existing projects (`cdforge adopt`)

`adopt` renders a full project into a temporary directory (reusing `render_project`, so
there is exactly one rendering path) and then applies each rendered file to the target
according to `adopt.classify()`:

- **managed** (`.devcontainer/`, `.githooks/`, `.claude/`) — overwritten; these *are* the
  sandbox and the workflow cdforge guarantees, and are the reason re-running `adopt` after a
  cdforge upgrade is the supported upgrade path for generated projects.
- **merged** (`.gitignore`, `.claude/settings.json`) — cdforge's entries are added and the
  project's are never removed (line-append and deep JSON merge respectively; a scalar the
  project already set always wins).
- **create-only** (`CLAUDE.md`, `README.md`, `CHANGELOG.md`, `LICENSE`,
  `docker-compose.yml`, `.env.example`) — written only when missing, otherwise reported as a
  conflict and left untouched (`--write-suggestions` writes `<name>.cdforge-new` alongside).
- everything else is application code and is never written into an existing project.

When a compose-based type is adopted into a project that already has its own
`docker-compose.yml`, the generated compose file cannot go to the root (overwriting it is
destructive, leaving it alone would point `devcontainer.json` at a file with no `app`
service). `adopt` therefore re-renders it as `.devcontainer/docker-compose.cdforge.yml` and
`devcontainer.json` lists both files — Docker Compose merges them and resolves the relative
paths of *every* file against the first file's directory (the project root), which is why the
override's `.`/`./.devcontainer` paths still mean what they say. The choice is driven by
`compose_file_location` (`root` | `devcontainer`) in `context_builder.py`; it is derived per
run, never stored in `.cdforge.json`, so a generated project keeps its root compose file and
adoption stays idempotent.

Consequences worth preserving: adoption is idempotent (a freshly scaffolded project reports
"already aligned" — `tests/test_cli.py` asserts this round trip), it never edits
`pyproject.toml` (it only *warns* when ruff/pytest are missing, since the generated
pre-commit hook needs them), and it refuses to run over uncommitted tracked changes unless
`--force`, so `git diff` is always a complete review of what it did. When adding a new file
to `templates/common/`, decide which of the four categories it falls into — the default for
an unlisted path is "never written into an existing project".

## The `data_science` project type

Notebooks are a project type with two rules of its own worth keeping:

- **Notebooks are source code.** The generated `pyproject.toml` sets ruff's
  `extend-include = ["*.ipynb"]`, so cells are linted and formatted like any other file, and
  `.githooks/pre-commit` runs `nbstripout` over the *staged* `.ipynb` files and re-stages
  them, so committed notebooks never carry outputs. The `.ipynb.j2` templates are written in
  nbformat's own serialisation (1-space indent, sequential string cell ids) so that a
  freshly generated notebook is byte-identical to what `nbstripout` would write — otherwise
  the first commit that touches one is a whole-file reformat. They are generated by hand-run
  script, not hand-edited JSON: keep cells lint-clean (single quotes, one import per line,
  no unused imports) or the generated project fails its own `ruff check`.
- **The stack is cumulative and derived, not asked twice.** `ml_stack`
  (`analysis` | `deep-learning` | `transformers`) is the single question; `derive_defaults`
  turns it into `include_torch`/`include_transformers` for the templates. `compute_target`
  chooses between PyTorch's CPU-only index (pinned via `[[tool.uv.index]]`, a few hundred MB)
  and the default CUDA wheels (several GB), and defaults to `cuda` only when the project was
  scaffolded with GPU passthrough. `training.py`, `tracking.py` and `tests/test_training.py`
  render blank — and are therefore skipped by the renderer — when their stack or tracking
  backend is off.

MLflow's plain-directory store is deprecated and now *raises*, so the generated `tracking.py`
uses a SQLite backend store (`mlflow.db`) with an explicit absolute artifact location: the
same run lands in the same place whether it was started from `notebooks/` or the project root.

## Template tree layout

- `templates/common/` mirrors a generated project's root exactly (`.devcontainer/`,
  `.claude/`, `.githooks/`, `CLAUDE.md.j2`, `README.md.j2`, ...) and is rendered into every
  project regardless of type.
- `templates/project_types/<id>/template/` also mirrors the output root (its own
  `.devcontainer/Dockerfile.j2`, `pyproject.toml.j2`, source tree, ...) and is rendered on
  top of `common/`.
- `templates/project_types/<id>/*.fragment.*.j2` (e.g. `CLAUDE.fragment.md.j2`,
  `precommit.fragment.sh.j2`, `compose.fragment.yml.j2` — which is shared by the root
  `docker-compose.yml` and the `.devcontainer/docker-compose.cdforge.yml` override) live
  *outside* `template/` — they are never rendered as
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
- **The devcontainer is unprivileged by default.** In-container Docker is chosen by the
  `docker_mode` context value (`none` | `sysbox` | `privileged`, derived in
  `context_builder.py`; the older boolean `enable_docker` still maps to `privileged`):
  - `none` (default): no in-container Docker; ordinary unprivileged container.
  - `sysbox`: adds `--runtime=sysbox-runc` (build layout) or `runtime: sysbox-runc` on the
    compose `app` service, and starts a Docker daemon via `.devcontainer/docker-start.sh`.
    The container stays unprivileged with no host access — this is the preferred way to give
    Claude Code its own Docker. It requires Sysbox on the host (untestable in CI; validate
    with a real rebuild on a sysbox host).
  - `privileged`: the `docker-in-docker` feature, which declares `"privileged": true` and so
    forces the container to run `--privileged` — giving in-container code CAP_SYS_ADMIN and
    direct host block-device/kernel access, a full escape of the "no host access" guarantee.
    The generated README/CLAUDE must keep warning about this. Its daemon is started from
    `.devcontainer/docker-start.sh` (postStartCommand), *not* from the feature's container
    entrypoint: using that entrypoint requires `"overrideCommand": false`, which hands the
    container's lifetime to the base image's `CMD` (`python3`) and kills it seconds after
    start. The script also switches Debian's iptables alternative to `iptables-nft` when the
    legacy backend cannot create the `nat` table, which is what dockerd needs on hosts whose
    kernel only has the nftables backend.
- **Backing services are sibling containers, not Docker-in-Docker.** `django_drf` projects
  that need Postgres/Redis use the Dev Containers Docker Compose workflow (`use_compose`): the
  devcontainer is the unprivileged `app` service and the databases are siblings on the compose
  network, reached by hostname (`db`, `redis`). This gives real services without an
  in-container daemon or privilege. `use_compose` is derived in `context_builder.py`; when it
  is false the devcontainer uses the plain `build.dockerfile` layout. In an adopted project
  the same services may instead live in `.devcontainer/docker-compose.cdforge.yml` (see
  `compose_file_location` below), which has the side benefit of being inside the read-only
  mount.
- **`.devcontainer/` is bind-mounted read-only into the container** (over the read-write
  workspace mount, with `claude-home` re-mounted read-write). This stops in-container code
  from rewriting `devcontainer.json`/`Dockerfile`/`post-create.sh`, which the host trusts and
  executes at build/rebuild time (`initializeCommand` runs on the host). Do not remove this
  without an equivalent protection.
- **All values interpolated into `devcontainer.json` must be JSON-escaped** (`| tojson`) so a
  crafted answer (e.g. `project_name`) cannot inject devcontainer keys.
- The "never push" rule is defended in depth (a `permissions.deny` glob plus a
  `.githooks/pre-push` hook) but its real basis is that no push credentials are mounted into
  the container. Keep the docs honest that the deny/hook are best-effort.
- **The sandbox is a filesystem sandbox by default; the network is opt-in.** A devcontainer
  sits on an ordinary Docker bridge, so without a firewall it reaches the internet, the LAN,
  and the *host itself* at the bridge gateway (the host's own listening ports answer from
  inside the container). `network_firewall` (`none` | `allowlist` | `strict`, derived in
  `context_builder.py`) controls this:
  - `none` (default): unrestricted, and the generated README/CLAUDE must say so plainly
    rather than letting "sandboxed" imply the network is covered.
  - `allowlist`: `.devcontainer/init-firewall.sh` is **copied into the image** as
    `/usr/local/bin/cdforge-firewall` (root-owned, so it cannot be rewritten from inside;
    the COPY path differs between the plain layout, whose build context is `.devcontainer/`,
    and the compose layout, whose context is the project root) and run by `postStartCommand`
    after `docker-start.sh`, so the firewall has the last word. It rejects egress to the
    default gateway, allows DNS to the container's resolvers (a deliberate hole when the
    resolver *is* the gateway), allows the container's own attached subnets (compose
    siblings, nested Docker), allows an explicit domain allowlist, and rejects the rest;
    IPv6 is closed outright. Capabilities come from `runArgs: --cap-add=NET_ADMIN` (plain)
    or `cap_add` on the `app` service (compose) — never `--privileged`.
  - `strict`: `allowlist` plus a Dockerfile step that removes the base image's blanket
    NOPASSWD sudo, leaving one sudoers rule for the firewall script, so the rules cannot be
    flushed from inside. It is incompatible with in-container Docker (whose daemon needs
    root at runtime) and `context_builder.py` degrades it to `allowlist` there — keep that
    degradation if either option changes.
  Keep the docs honest about which of these is in effect: in `allowlist` mode
  `sudo iptables -F` still works, so it stops incidental traffic, not a determined process.
- Dev services in `compose.fragment.yml.j2` publish on `127.0.0.1` only. The devcontainer
  reaches `db`/`redis` by hostname on the compose network; publishing on all interfaces
  would put a fixed-password dev database on the LAN.
- GPU passthrough is `runArgs: ["--gpus=all"]` in the plain build layout, and a device
  reservation on the `app` service in the compose layout.

## Language and style

- English only, everywhere (code, comments, commits, docs).
- Dependencies managed with `uv`; run everything via `uv run ...`.
- `ruff` enforces style: single-quoted strings, one import per line and sorted
  (`force-single-line = true`) — never `from x import a, b`.

## This repository is adopted into its own template

`cdforge adopt` has been run on this repository itself, so cdforge is developed inside the
same sandboxed devcontainer it generates (answers recorded in `.cdforge.json`:
`python_uv_tool`, `docker_mode: sysbox`, `network_firewall: none`). Two consequences:

- **`.devcontainer/`, `.claude/` and `.githooks/` here are generated output, not hand-written
  files.** They are the *managed* category of `adopt.classify()` and the next
  `cdforge adopt .` overwrites them. To change them, change the template under
  `src/cdforge/templates/` and re-run `uv run cdforge adopt .` — never edit them in place, or
  the edit silently disappears and the templates never learn about it. (`CLAUDE.md`,
  `README.md` and `CHANGELOG.md` are the *create-only* category: they already exist, so
  adoption reports them as conflicts and leaves this project's own versions alone.)
- **`sysbox` was chosen because `scripts/e2e.sh` needs a Docker daemon**, and sysbox is the
  only mode that provides one without making the container privileged. It requires Sysbox on
  the host; without it the container does not start. `docker_mode: none` still works for
  everything except the e2e harness, which then has to run on the host.

Re-running `cdforge adopt .` after changing a template is also the cheapest smoke test that
adoption still works, and keeps this repository's devcontainer current with the templates.

## Workflow

- Keep this file, `README.md`, and `CHANGELOG.md` in sync with what the tool actually does.
- Bump `[project].version` in `pyproject.toml` and add a `CHANGELOG.md` entry for every
  notable change, in the same commit as the change.
- Commit each feature/fix on its own with a Conventional Commit message. Never `git push`.
- `.githooks/pre-commit` (installed via `git config core.hooksPath .githooks`) runs
  `ruff check`, `ruff format --check`, and `pytest` before a commit is accepted.
- A template file added under a path that `adopt.classify()` does not recognise is silently
  skipped when adopting; add it to the right category in `adopt.py` in the same commit.
- After touching a template, manually scaffold a project from it and run `uv sync`,
  `ruff check`, `ruff format --check`, and `pytest` *inside the generated project* —
  the test suite only checks file presence/content, not that generated Python/Django code
  actually runs; that has caught real bugs before (an `[build-system]`/`uv_build` mismatch
  for the Django app-layout project, and Django's `makemigrations` not auto-detecting a
  brand-new unmigrated app unless named explicitly, fixed by shipping a checked-in initial
  migration).
- `scripts/e2e.sh` automates the full container-level matrix: it scaffolds each variant,
  runs `devcontainer up`, and checks isolation / read-only `.devcontainer` / `ruff` / `pytest`
  / the docker/gpu capability *inside the real container*, then tears it down. It needs
  docker, `uv`, and the Dev Containers CLI; `sysbox` and `gpu` variants are auto-skipped when
  the host lacks the runtime. The `py-adopt`/`dj-adopt` variants cover `cdforge adopt`: they
  scaffold a project, delete everything cdforge manages (and give the compose project a
  `docker-compose.yml` of its own), then adopt it and build the result — which is the only
  way to verify the compose-override layout for real. Run `scripts/e2e.sh --list` to see
  variants,
  `scripts/e2e.sh --only py-default,dj-sqlite` for a subset. The `ds-*` variants also
  execute the first generated notebook and exercise the notebook-stripping pre-commit hook
  inside the container. This has found real build bugs
  (the broken yarn apt source; the `uv_build` module-name mismatch).
