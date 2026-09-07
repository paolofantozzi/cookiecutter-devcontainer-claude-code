# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.17] - 2026-09-07

### Fixed

- **The `pre-push` hook no longer blocks pushes from the host.** `core.hooksPath` is a
  repository-level setting shared by the host and the container, so the unconditional
  `pre-push` guard also refused a human's `git push` from the host — the one place a push is
  meant to happen. The hook now keys off a new `CDFORGE_DEVCONTAINER=1` env var (added to
  `devcontainer.json`'s `containerEnv`): it refuses a push from inside the devcontainer and
  is a no-op on the host. Re-run `cdforge adopt .` on a generated project to pick up the
  change.

## [0.1.16] - 2026-09-07

### Added

- New **`generic` project type**: a near-empty workspace for whatever does not fit the other
  types — drafting documents, keeping notes, scratch code — running in the same sandboxed
  devcontainer. It ships only a `docs/` folder, a `tests/` folder, and a `pyproject.toml`
  that gives a `uv`-managed environment with `ruff` and `pytest` but nothing to build
  (`[tool.uv] package = false`, no `[build-system]`). Its `.githooks/pre-commit` runs the
  test suite but treats pytest's "no tests collected" status as success, so a
  documents-only project commits without carrying any tests. `cdforge adopt` recognises an
  existing project as `generic` when its `pyproject.toml` sets `[tool.uv] package = false`.
  Only one question, `python_version`.

## [0.1.15] - 2026-09-07

### Fixed

- **Reject `gpu_enabled` together with `docker_mode: sysbox`.** Sysbox has no NVIDIA
  container-runtime support, so a devcontainer generated with both `--gpus=all` and
  `--runtime=sysbox-runc` built fine but failed to start on the NVIDIA prestart hook
  (`Running hook #0 ... failed to open OCI spec file: ... permission denied`). The wizard
  now re-prompts for the Docker mode when the combination is chosen, and
  `validate_answer_compatibility` (called from `build_context`, so it also covers
  `--answers-file` runs and `cdforge adopt`) raises a clear `AnswersError` pointing at
  `docker_mode: none` or `privileged`. Existing projects hitting this: re-run
  `cdforge adopt .` after switching `docker_mode` in `.cdforge.json`.

## [0.1.14] - 2026-09-05

### Added

- New **`data_science` project type**: Jupyter notebooks plus a reusable `src/<package>/`
  package, for data analysis, classical ML and transformer fine-tuning — all managed with
  `uv` and running in the same sandboxed devcontainer as the other types.
  - One question, `ml_stack`, selects a cumulative stack: `analysis`
    (numpy/pandas/matplotlib/seaborn/scikit-learn/JupyterLab), `deep-learning` (+ PyTorch) or
    `transformers` (+ Hugging Face transformers/datasets/accelerate/evaluate). `compute_target`
    pins PyTorch to its CPU-only index or takes the default CUDA wheels, defaulting to `cuda`
    when the project was scaffolded with GPU passthrough. `experiment_tracking` adds MLflow
    (local SQLite store, no server) or Weights & Biases.
  - The generated package ships `config.py` (project paths + `RANDOM_SEED`), `data.py`
    (loading/saving and one shared train/validation/test split), `seeding.py`, and — for the
    PyTorch stacks — `training.py` with a seeded, checkpointing training loop runnable as
    `uv run python -m <package>.training` on synthetic data, plus
    `fine_tune_text_classifier()` for Hugging Face sequence classifiers.
  - Two generated notebooks (`01-explore-data.ipynb`, `02-train-model.ipynb`) that run top to
    bottom offline, a `notebook-ml-conventions` skill, and gitignore entries that keep
    datasets, checkpoints, figures and tracking stores out of git.
- **Notebooks are treated as source code.** ruff is configured with
  `extend-include = ["*.ipynb"]`, and the generated `.githooks/pre-commit` strips outputs from
  staged notebooks with `nbstripout` and re-stages them, so notebook diffs stay reviewable and
  cell outputs (which can carry data printed inside the container) never reach a commit.
- `ProjectType` gained `forward_ports`, `vscode_extensions` and `extra_allowed_domains`, so a
  type can declare the ports its devcontainer forwards (8888 for JupyterLab), the VS Code
  extensions it needs (the Jupyter extension) and the hosts its toolchain fetches from
  (`huggingface.co`, `download.pytorch.org`) — the last of which are added to the egress
  firewall's allowlist when it is enabled.
- `cdforge adopt` detects notebook projects (a `notebooks/` directory, or a
  jupyter/torch/transformers dependency) along with their stack, compute target and tracking
  backend.
- `scripts/e2e.sh` variants `ds-analysis`, `ds-torch`, `ds-firewall` and `ds-adopt`, which
  additionally execute a generated notebook and check the notebook-stripping pre-commit hook
  inside the real container.

## [0.1.13] - 2026-09-05

### Added

- Optional **network egress firewall** for the generated devcontainer, answered at scaffold
  time as `network_firewall` (`none` | `allowlist` | `strict`, default `none`). A
  devcontainer is a *filesystem* sandbox: by default it still sits on a Docker bridge and can
  reach the internet, the LAN, and the host itself at the bridge gateway, so ports listening
  on the host answer from inside the container.
  - `allowlist` renders `.devcontainer/init-firewall.sh`, copies it into the image as
    root-owned `/usr/local/bin/cdforge-firewall`, and runs it from `postStartCommand` (after
    the Docker daemon, when there is one). It rejects the default gateway and everything
    else except DNS, the container's own subnets (compose siblings, nested Docker) and an
    allowlist of hosts (Anthropic, GitHub, PyPI, npm, Debian); IPv6 egress is closed. Extra
    domains go in `.devcontainer/firewall-allow.txt`, which is on the read-only mount and so
    can only be extended from the host. Capabilities are `NET_ADMIN`/`NET_RAW` — never
    `--privileged`.
  - `strict` additionally removes the base image's blanket passwordless sudo, leaving one
    sudoers rule for the firewall script, so the rules cannot be flushed from inside. It
    needs no in-container Docker (whose daemon needs root) and degrades to `allowlist` when
    one is enabled.
- `scripts/e2e.sh` variants `py-firewall`, `py-firewall-strict` and `dj-firewall`, which
  check inside the real container that the host gateway is unreachable, that the allowlist
  still works, that an off-allowlist host is rejected, and that strict mode has no blanket
  sudo.

### Changed

- Postgres and Redis are published on `127.0.0.1` instead of every host interface. The
  devcontainer reaches them by hostname on the compose network, so the previous binding only
  exposed a fixed-password dev database to the whole LAN.
- The generated `README.md`/`CLAUDE.md` and this repository's `README.md` now say plainly
  that, without the firewall, the sandbox covers the filesystem and not the network — the
  previous wording ("nothing else on the host is reachable from inside it") read as a
  promise it did not keep.

## [0.1.12] - 2026-09-05

### Added

- New `cdforge adopt [PROJECT_DIR]` command: aligns an **existing** project with what
  `cdforge new` generates. It asks the same questions pre-filled with what it detects in the
  project (type, package/Django layout, dependencies, author, git remote, current
  devcontainer settings — `--non-interactive` just takes the detected answers), then:
  - (re)writes the managed sandbox files `.devcontainer/`, `.githooks/`, `.claude/skills/`;
  - merges cdforge's entries into `.gitignore` and `.claude/settings.json`, keeping the
    project's own;
  - creates `README.md`/`CLAUDE.md`/`CHANGELOG.md`/`LICENSE`/`docker-compose.yml`/
    `.env.example` only when missing, reporting the rest as conflicts to merge by hand
    (`--write-suggestions` writes the generated version as `<name>.cdforge-new`);
  - never writes application code (`src/`, `apps/`, `pyproject.toml`, tests).

  Adopting a compose-based project that already has its own `docker-compose.yml` writes the
  devcontainer's services to `.devcontainer/docker-compose.cdforge.yml` instead of the root
  file, and `devcontainer.json` now accepts a list of compose files, so the project's
  services survive and the `app` service is merged on top of them.

  `--dry-run` prints the plan and writes nothing, and adoption refuses to run over
  uncommitted tracked changes (`--force` overrides) so the result is reviewable with
  `git diff`.
- Generated and adopted projects now carry a `.cdforge.json` manifest recording the answers
  they were built from. `cdforge adopt` reuses it without asking (`--reconfigure` to change
  the answers), which makes re-running it the supported **upgrade path**: after upgrading
  cdforge, adopt a generated project to pull in newer devcontainer fixes. Adoption is
  idempotent — a freshly scaffolded project reports "already aligned".
- The generated `README.md` and `CLAUDE.md` now document which files are cdforge-managed
  (and therefore re-rendered by `cdforge adopt`) versus owned by the project.
- `scripts/e2e.sh` gained `py-adopt` and `dj-adopt` variants, which strip a generated project
  of everything cdforge manages (replacing the compose file with one of the project's own) and
  then adopt it, so the adopted devcontainer is built and checked like any other variant.

## [0.1.11] - 2026-09-05

### Fixed

- Privileged `docker-in-docker` mode now actually works. Two problems, both found by
  `scripts/e2e.sh` on a real host:
  - `"overrideCommand": false` (added in 0.1.10 so the feature's entrypoint could start
    `dockerd`) also hands the container's lifetime to the base image's `CMD` (`python3`),
    which exits immediately — the devcontainer stopped seconds after starting. The setting is
    gone; `dockerd` is now started from `postStartCommand` via `.devcontainer/docker-start.sh`,
    which calls the feature's own `docker-init.sh` (so cgroup nesting and DNS are still set up
    upstream's way) and keeps the CLI's keep-alive command.
  - The docker-in-docker feature pins Debian's iptables alternative to the *legacy* backend,
    which cannot create the `nat` table on hosts whose kernel only provides nftables; `dockerd`
    died with ``can't initialize iptables table `nat'``. The start script now switches to
    `iptables-nft` when the legacy backend is unusable.

  `docker-start.sh` is therefore generated for both the `sysbox` and `privileged` modes.

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
