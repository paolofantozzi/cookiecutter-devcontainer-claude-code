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
  `ProjectType` can declare `stack` (`'python'` default / `'node'` / `'static'` — the common
  templates branch on it), `extra_apt_packages`, `extra_features`, `forward_ports`,
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

The devcontainer is **never** a Docker Compose project. `devcontainer.json` always uses the
plain `build.dockerfile` layout — a single, plain container that is only the dev/Claude Code
environment. A project that needs a **database server** (`database` in `postgres` /
`mariadb`, a shared question on every Python type) or Redis (`django_drf` +
`include_celery`) ships a plain root `docker-compose.yml` (db/redis only, **no `app`
service**, ports on `127.0.0.1`) that the developer brings up from *inside* the container
with the in-container Docker daemon (`docker compose up -d`); that is what
`docker_mode: sysbox` / `privileged` is for, and `answers.validate_answer_compatibility`
rejects `database` in (`postgres`, `mariadb`) / `include_celery` with `docker_mode='none'`
for any type. `adopt` writes no compose file at all: a project's own `docker-compose.yml` is
*create-only* (written if missing, reported as a conflict otherwise — cdforge's is db/redis
with `localhost` ports and may not match the project's), and `adopt` *warns* when a server
database is chosen but `pyproject.toml` declares no driver.
`context_builder.needs_service_stack` is the single derived flag (`db_is_server` or
`include_celery`); the templates branch on it. The db/`.env` wiring is derived in
`context_builder.py`: `db_is_server`, `db_image`, `db_port`, `database_url`, and — for
`mariadb` — `default-libmysqlclient-dev` + `pkg-config` appended to `extra_apt_packages`.

Consequences worth preserving: adoption is idempotent (a freshly scaffolded project reports
"already aligned" — `tests/test_cli.py` asserts this round trip), it never edits
`pyproject.toml` (it only *warns* when ruff/pytest are missing, since the generated
pre-commit hook needs them), and it *warns* (but proceeds) when the worktree has uncommitted
tracked changes — `--force` silences that warning — so committing first still gives a
`git diff` that is a complete review of what it did. When adding a new file
to `templates/common/`, decide which of the four categories it falls into — the default for
an unlisted path is "never written into an existing project".

The project type is resolved in `cli._resolve_adopt_answers`: `--answers-file`, else
`.cdforge.json` (unless `--reconfigure`), else `detect.py`. `--type/-t` overrides the type in
all of those. An interactive run with a recorded manifest calls
`wizard.reselect_project_type`, which keeps every `COMMON_ANSWER_KEYS` answer and prompts
only for the (possibly new) type's own questions — a lighter path than `--reconfigure`.
`_stdin_is_interactive()` gates that prompt so non-interactive runs and the test suite keep
reusing the recorded answers untouched (the "already aligned" round trip depends on this).
`--type` never prompts: a forced switch fills the new type's answers from `detect.py` +
question defaults. Since `adopt` only writes the managed files, switching the type
regenerates the sandbox/hooks/skills but never scaffolds the new type's source code.

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

Like every Python type it also carries the shared `database` question; `postgres`/`mariadb`
emit the root `docker-compose.yml` + `.env.example` and add the driver, but no data-access
code is generated — a notebook reads `DATABASE_URL` from the environment itself.

## The `generic` project type

The minimal type: Python + `uv` + `ruff` + `pytest` in the sandbox and nothing else. Its
`pyproject.toml` sets `[tool.uv] package = false` and declares no `[build-system]`, so there
is nothing to build; the template tree is just `docs/.gitkeep` and `tests/.gitkeep`. It has
two questions (`python_version` and the shared `database` question) and no `derive_defaults`.
Picking `database` = `postgres`/`mariadb` still emits the root `docker-compose.yml` +
`.env.example` and adds the driver to `pyproject.toml` (whose `dependencies` list goes from
`[]` to holding just that driver). Two rules of its own:

- Its `precommit.fragment.sh.j2` runs `uv run pytest || [ "$?" -eq 5 ]` — pytest's
  "no tests collected" exit status is treated as success, because a documents-only project
  legitimately has no tests. A real failure (exit 1) still blocks the commit.
- `detect.py` classifies an existing project as `generic` only on the explicit
  `[tool.uv] package = false` signal, so a normal package missing a `[build-system]` is
  still detected as `python_uv_tool`.

## The `angular` project type

The first **non-Python** type: Node + npm + the Angular CLI + ESLint/Prettier + Karma. It is
what introduced the `stack` field on `ProjectType` (`'python'` by default, `'node'` here).
`context_builder.py` copies `project_type.stack` into the context, and the shared
`templates/common/` files branch on it rather than hard-coding `uv`/`ruff`:
`post-create.sh` (`npm install` vs `uv sync`), `.githooks/pre-commit` (skips the `ruff`
lines), `.gitignore` (`node_modules/`/`dist/`/`.angular/` instead of the Python block),
`CLAUDE.md` (the "Language and style" section and the version-bump line), and the
`project-governance` skill (`package.json` instead of `pyproject.toml`). Any new common
template that mentions the toolchain must branch on `stack` too.

Rules of its own worth keeping:

- **Karma runs headless Chromium inside an unprivileged container.** `chromium` is an
  `extra_apt_package`, the Dockerfile sets `ENV CHROME_BIN=/usr/bin/chromium`, and
  `karma.conf.js` defines a `ChromeHeadlessNoSandbox` launcher (`--no-sandbox
  --disable-gpu --disable-dev-shm-usage`) because the container has no user namespaces.
  `angular.json`'s test target must point at that file with `"karmaConfig":
  "karma.conf.js"` — the `@angular-devkit/build-angular:karma` builder ignores a stray
  `karma.conf.js` otherwise and launches non-headless Chrome, which fails with "Missing X
  server".
- **`post-create.sh` runs `npm install`, not `npm ci`.** No lockfile is generated by the
  scaffolder, so `npm ci` would fail on first create; `npm install` writes
  `package-lock.json` on the first run (the same way `uv sync` creates `uv.lock`).
- **The builders are `@angular-devkit/build-angular:*`**, not the newer `@angular/build:*`.
  The devkit package is still maintained in Angular 20 and its Karma path
  (`@angular-devkit/build-angular/plugins/karma`, framework `@angular-devkit/build-angular`)
  is the battle-tested one for a generated project that must `npm install && ng build && ng
  test` cleanly.
- `detect.py` classifies an existing project as `angular` when `package.json` depends on
  `@angular/core` (or `@angular/cli`), checked before any pyproject-based signal since an
  Angular repo has no `pyproject.toml`. `app_name`/`node_version`/author/license are read
  from `package.json` + `angular.json`. `adopt._tooling_notes` warns about a missing
  `package.json`/ESLint instead of a missing `pyproject.toml`/ruff.

## The `static_site` project type

The minimal **no-toolchain** type: `stack='static'`, a plain devcontainer
(`devcontainers/python:3.12`, only for its `python3`), and a repository that is nothing but
a hand-written static site — HTML, CSS, JS at the root, with `assets/` for media. There is
no `package.json`, no `pyproject.toml`, no build step and no dependency; **the repository
root is the deploy root** (a static host serves it unchanged), which is the constraint the
whole type is shaped around.

`stack='static'` is the third value the common templates branch on (alongside `'python'`
and `'node'`), so every common file that names a toolchain has a `static` arm:
`post-create.sh` (no install step at all), `.githooks/pre-commit` (no `ruff`/`npm` — just
`{% include %}` of the fragment), `.gitignore` (no language block), `CLAUDE.md` (the
"belongs to the project" line, the "Language and style" section, the version-bump line, and
the pre-commit line), and the `project-governance` skill (version lives in `CHANGELOG.md`
alone; a "Checks" section instead of "Tests"). A new common template that mentions the
toolchain must add a `static` arm too.

Rules of its own worth keeping:

- **No lint, no tests, on purpose.** `precommit.fragment.sh.j2` only asserts that
  `index.html` exists and is non-empty — a zero-dependency check, since nothing is
  installed. The generated `CLAUDE.md`/skill tell Claude to open changed pages in a browser
  (`python3 -m http.server 8000`, port 8000 forwarded) rather than run a suite.
- **The version lives only in `CHANGELOG.md`** — there is no manifest to bump.
- `forward_ports=[8000]` is `http.server`'s default; the Dockerfile installs no language
  runtime (`astral-sh/uv` COPY dropped) and relies on the base image's `python3`.
- `detect.py` classifies an existing project as `static_site` when it has **no**
  `pyproject.toml` and **no** `package.json` but does have `index.html` (or a root `*.html`),
  checked right after the Angular signal. Only `license_id` is detected (from the `LICENSE`
  file text); author falls back to the git identity via the question defaults. The shared
  `database` question is skipped for it, like `angular`. `adopt._tooling_notes` returns
  nothing (there is no toolchain to warn about), and the site files are *project-owned* — a
  re-`adopt` rewrites only `.devcontainer/`, `.githooks/`, `.claude/`.

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
- **The devcontainer is unprivileged by default.** In-container Docker is chosen by the
  `docker_mode` context value (`none` | `sysbox` | `privileged`, derived in
  `context_builder.py`; the older boolean `enable_docker` still maps to `privileged`):
  - `none` (default): no in-container Docker; ordinary unprivileged container.
  - `sysbox`: adds `--runtime=sysbox-runc` to `runArgs` and starts a Docker daemon via
    `.devcontainer/docker-start.sh`.
    The container stays unprivileged with no host access — this is the preferred way to give
    Claude Code its own Docker. It requires Sysbox on the host (untestable in CI; validate
    with a real rebuild on a sysbox host). **`sysbox` is incompatible with `gpu_enabled`** —
    Sysbox has no NVIDIA-runtime support, so a container with both `--gpus=all` and
    `--runtime=sysbox-runc` dies on the NVIDIA prestart hook (`Running hook #0 ... permission
    denied`). `validate_answer_compatibility` in `answers.py` rejects the combination (the
    wizard re-prompts; `build_context` raises `AnswersError`), so it can never be generated.
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
- **Backing services run inside the devcontainer, not as sibling containers.** Any Python
  project that picks a database server (`database` in `postgres` / `mariadb`) — or a
  `django_drf` project with `include_celery` for Redis — ships a plain root
  `docker-compose.yml` (db/redis only, no `app` service, ports published on `127.0.0.1`)
  that the developer runs from *inside* the devcontainer with its in-container Docker daemon
  (`docker compose up -d`); the app reaches the services at `localhost` via `DATABASE_URL`
  in `.env` (Django's `settings.py` reads it through `dj-database-url`). This deliberately
  requires `docker_mode: sysbox` / `privileged` — `answers.validate_answer_compatibility`
  rejects `database` in (`postgres`, `mariadb`) / `include_celery` with `docker_mode='none'`
  (the wizard re-prompts after the per-type questions; `build_context` raises
  `AnswersError`). The devcontainer itself is always the plain single-container
  `build.dockerfile` layout; `needs_service_stack` in `context_builder.py` only gates
  whether the `docker-compose.yml` file is emitted.
- **`.devcontainer/` is bind-mounted read-only into the container** (over the read-write
  workspace mount, with `claude-home` re-mounted read-write). This stops in-container code
  from rewriting `devcontainer.json`/`Dockerfile`/`post-create.sh`, which the host trusts and
  executes at build/rebuild time (`initializeCommand` runs on the host). Do not remove this
  without an equivalent protection.
- **All values interpolated into `devcontainer.json` must be JSON-escaped** (`| tojson`) so a
  crafted answer (e.g. `project_name`) cannot inject devcontainer keys.
- The "never push" rule is defended in depth (a `permissions.deny` glob plus a
  `.githooks/pre-push` hook) but its real basis is that no push credentials are mounted into
  the container. Keep the docs honest that the deny/hook are best-effort. `core.hooksPath`
  is a repo-level setting shared by host and container, so the `pre-push` hook keys off the
  `CDFORGE_DEVCONTAINER` env var (set in `devcontainer.json`'s `containerEnv`): it blocks a
  push from inside the sandbox and is a no-op on the host, where a human is meant to push.
- **The sandbox is a filesystem sandbox by default; the network is opt-in.** A devcontainer
  sits on an ordinary Docker bridge, so without a firewall it reaches the internet, the LAN,
  and the *host itself* at the bridge gateway (the host's own listening ports answer from
  inside the container). `network_firewall` (`none` | `allowlist` | `strict`, derived in
  `context_builder.py`) controls this:
  - `none` (default): unrestricted, and the generated README/CLAUDE must say so plainly
    rather than letting "sandboxed" imply the network is covered.
  - `allowlist`: `.devcontainer/init-firewall.sh` is **copied into the image** as
    `/usr/local/bin/cdforge-firewall` (root-owned, so it cannot be rewritten from inside; the
    build context is always `.devcontainer/`, so the COPY path is unprefixed) and run by
    `postStartCommand` after `docker-start.sh`, so the firewall has the last word. It rejects
    egress to the default gateway, allows DNS to the container's resolvers (a deliberate hole
    when the resolver *is* the gateway), allows the container's own attached subnets (any
    nested/in-container Docker, where a `docker compose up` db/redis lands), allows an
    explicit domain allowlist, and rejects the rest; IPv6 is closed outright. Capabilities
    come from `runArgs: --cap-add=NET_ADMIN` / `--cap-add=NET_RAW` — never `--privileged`.
  - `strict`: `allowlist` plus a Dockerfile step that removes the base image's blanket
    NOPASSWD sudo, leaving one sudoers rule for the firewall script, so the rules cannot be
    flushed from inside. It is incompatible with in-container Docker (whose daemon needs
    root at runtime) and `context_builder.py` degrades it to `allowlist` there — keep that
    degradation if either option changes.
  Keep the docs honest about which of these is in effect: in `allowlist` mode
  `sudo iptables -F` still works, so it stops incidental traffic, not a determined process.
- Dev services in `django_drf`'s `docker-compose.yml` publish on `127.0.0.1` only. Django
  reaches `db`/`redis` at `localhost` via the published port (the devcontainer is not on the
  services' network); publishing on all interfaces would put a fixed-password dev database on
  the LAN.
- GPU passthrough is `runArgs: ["--gpus=all"]`. It cannot be combined with
  `docker_mode: sysbox` (see the sysbox note above); pair a GPU with `none` or `privileged`.
  For a `django_drf` project with Postgres, that means `privileged` (Postgres already rules
  out `none`).

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
  scaffold a project, delete everything cdforge manages (and give the django project a
  `docker-compose.yml` of its own so adoption meets a create-only conflict), then adopt it
  and build the result. The scaffolded `dj-*` postgres variants `docker compose up -d` the
  db/redis stack *inside* the container before `migrate`, which is the real workflow. Run
  `scripts/e2e.sh --list` to see variants,
  `scripts/e2e.sh --only py-default,dj-sqlite` for a subset. The `ds-*` variants also
  execute the first generated notebook and exercise the notebook-stripping pre-commit hook
  inside the container; the `ss-*` (static site) variants run the pre-commit hook and check
  that `python3 -m http.server` serves `index.html` with no toolchain installed. This has
  found real build bugs (the broken yarn apt source; the `uv_build` module-name mismatch).
