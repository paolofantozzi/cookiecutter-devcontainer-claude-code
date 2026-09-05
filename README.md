# cdforge

A cookiecutter-style scaffolder that generates new projects shipping a VS Code devcontainer
with Claude Code running *inside* it — sandboxed so Claude Code can only ever reach that
project's own folder, never the rest of your machine. Claude Code does not need to be
installed on your host at all.

## What you get in a generated project

- A `.devcontainer/` (Docker-based) with Claude Code pre-installed via the official
  [Claude Code Dev Container Feature](https://github.com/anthropics/devcontainer-features/tree/main/src/claude-code),
  and the VS Code extension auto-added when you open it.
- **Sandboxing by construction, not a Claude Code setting**: the container is an ordinary,
  **unprivileged** container that only mounts the project's own folder plus its own Claude
  Code config directory — no host block devices, no host Docker socket, no host filesystem.
  `.devcontainer/` is mounted **read-only**, so the container that defines the sandbox
  cannot be rewritten from inside it.
- Projects that need backing services (django + Postgres/Redis) get them as **sibling
  containers** via the Dev Containers Docker Compose workflow, reachable by hostname over a
  private network — no in-container Docker daemon and no privilege required.
- In-container Docker for Claude Code (build/run/Testcontainers) is **opt-in and off by
  default**, with two modes: **Sysbox** (`--runtime=sysbox-runc`) gives a full in-container
  Docker daemon that stays unprivileged with no host access (requires Sysbox on a Linux
  host); **privileged** `docker-in-docker` gives Docker anywhere but makes the container
  `--privileged`, which grants host kernel/device access and voids the isolation above. The
  generated docs say which one is in effect.
- Login and conversation memory persist per project in `.devcontainer/claude-home/`
  (gitignored) — sign in once, it survives container rebuilds.
- Every terminal session starts in Claude Code's `auto` permission mode; pushing is
  discouraged by a `permissions.deny` entry and a `pre-push` hook, and prevented in practice
  because no push credentials are mounted into the container.
- **Optional egress firewall**, off by default: `allowlist` mode installs an iptables script
  into the image that rejects everything except DNS, the container's own networks, and an
  allowlist (Anthropic, GitHub, PyPI, npm, Debian) — including the Docker bridge gateway,
  which is how the *host's* own listening ports are reachable from an ordinary devcontainer.
  `strict` mode additionally removes the base image's passwordless `sudo`, so the rules cannot
  be flushed from inside.
- Optional GPU passthrough for the devcontainer itself, chosen at scaffold time — which is
  also what the `data_science` type defaults its PyTorch build (CUDA vs CPU-only wheels) to.
- A `.githooks/pre-commit` hook that runs the linter and the full test suite before any
  commit is accepted.
- A `CLAUDE.md` telling the embedded Claude Code to keep itself, `README.md`,
  `CHANGELOG.md`, and `[project].version` up to date, commit per feature with Conventional
  Commits, and never push.

## Project types

| Type | What it scaffolds |
| --- | --- |
| `python_uv_tool` | A `uv`-managed Python CLI (Typer), ruff-formatted, pytest tests. |
| `django_drf` | A Django REST Framework API: pytest-django, optional Postgres/Redis/Celery as unprivileged sibling containers via the Dev Containers Docker Compose workflow, JWT or session auth, optional drf-spectacular docs. |
| `data_science` | Jupyter notebooks plus a reusable `src/` package for data analysis and model training: numpy/pandas/scikit-learn, optionally PyTorch (CPU or CUDA wheels) and the Hugging Face transformers stack, MLflow or W&B tracking, notebooks linted by ruff and stripped of outputs before every commit. |

Run `cdforge list-types` to see this list from the CLI, and `cdforge list-skills` for the
optional Claude Code skills you can add on top of the mandatory ones.

## What the sandbox does and does not guarantee

The generated devcontainer is an unprivileged container whose only writable mount is the
project workspace (`.devcontainer/` is read-only). From inside it, Claude Code cannot reach
the host filesystem, the host Docker daemon, or host devices. Three things are worth
understanding, though:

- **The sandbox is a filesystem sandbox; the network is opt-in.** With the default
  `network_firewall: none`, the container behaves like any devcontainer: it sits on a Docker
  bridge and can reach the internet, your LAN, and the host itself through the bridge gateway
  — so anything listening on the host (SSH, a database, a dev server) answers from inside the
  container. Choose the `allowlist` or `strict` firewall mode to close that. In `allowlist`
  mode the image keeps its passwordless `sudo`, so in-container root can flush the rules:
  that mode stops incidental traffic, it is not a boundary against a determined process.
  `strict` removes that `sudo` (and is therefore incompatible with in-container Docker, whose
  daemon needs root at runtime — it degrades to `allowlist` there).
- **The workspace itself is shared with the host.** Everything under the project folder is
  the same bytes on the host disk. Files there that the *host* later executes — git hooks
  under `.git/hooks`, an editor task in `.vscode/`, a `Makefile` you run on the host — run
  with your privileges, not the container's. Review changes (they are tracked in git) before
  running project tooling on the host, and prefer working inside the container.
- **In-container Docker is an explicit trade-off.** If Claude Code needs to build/run its
  own containers, prefer the **Sysbox** mode (Docker inside, still no host access) where the
  host supports it. The **privileged** `docker-in-docker` mode re-introduces host access and
  should only be used when Sysbox is not available and you accept that.

## Usage

```console
$ uv tool install cdforge   # or: uvx cdforge new
$ cdforge new
```

Answer the prompts (project name, git remote if one exists yet, project type, GPU, optional
skills, then that type's own questions), then:

1. `code <project-dir>`
2. Command Palette → **Dev Containers: Reopen in Container**
3. Open a terminal in the container and run `claude` once to sign in.

For scripted/non-interactive use:

```console
$ cdforge new --answers-file answers.json --output-dir my-project --non-interactive
```

## Adopting an existing project

`cdforge adopt` brings a project that already exists in line with what `cdforge new`
generates — same sandboxed devcontainer, same hooks, same Claude Code setup — without
touching its source code:

```console
$ cd my-existing-project
$ cdforge adopt --dry-run   # show exactly what would change
$ cdforge adopt             # apply it
```

It answers the same questions as `new`, pre-filled with what it can detect in the project
(type, package/Django layout, dependencies, author, git remote, existing devcontainer
settings); `--non-interactive` accepts the detected answers as-is. What it does with each
file:

| Files | What happens |
| --- | --- |
| `.devcontainer/`, `.githooks/`, `.claude/skills/` | **Managed** — (re)written to exactly what cdforge generates. |
| `.gitignore`, `.claude/settings.json` | **Merged** — cdforge's entries are added, yours are kept. |
| `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `LICENSE`, `docker-compose.yml`, `.env.example` | Created only if missing; otherwise reported as a conflict and left alone (`--write-suggestions` drops the generated version next to it as `<name>.cdforge-new`). |
| Everything else (`src/`, `apps/`, `pyproject.toml`, tests, ...) | Never written. |

For a compose-based project (Django with Postgres/Redis) that already has its own
`docker-compose.yml`, the devcontainer's services are written to
`.devcontainer/docker-compose.cdforge.yml` and `devcontainer.json` loads both files, so your
services stay untouched and the devcontainer's `app` service is merged on top.

The answers are recorded in `.cdforge.json`, so a later `cdforge adopt` reuses them without
asking (`--reconfigure` to change them). That also makes it the **upgrade path for generated
projects**: after upgrading cdforge, re-run `cdforge adopt` in a project to pull in newer
devcontainer fixes. Adoption refuses to run over uncommitted changes (`--force` to override),
so the rewrite is always reviewable with `git diff`.

## Developing cdforge itself

```console
$ uv sync --all-extras
$ uv run pytest
$ uv run ruff check .
$ uv run ruff format .
```

`git config core.hooksPath .githooks` is already set for this repository; the pre-commit
hook runs the same lint + test gate described above.

To test the generated devcontainers for real (build them and run checks inside the running
container), use the end-to-end harness:

```console
$ scripts/e2e.sh --list                       # available variants
$ scripts/e2e.sh                              # run every host-supported variant
$ scripts/e2e.sh --only py-default,dj-sqlite  # a subset
```

It needs Docker, `uv`, and the Dev Containers CLI; the `sysbox` and `gpu` variants are
skipped automatically when the host lacks the runtime.

See [CLAUDE.md](./CLAUDE.md) for the full architecture and the conventions this project
follows.
