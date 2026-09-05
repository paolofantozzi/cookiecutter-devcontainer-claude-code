#!/usr/bin/env bash
#
# End-to-end test matrix for cdforge-generated devcontainers.
#
# For each selected variant this script:
#   1. scaffolds a project with `cdforge new --answers-file ...`,
#   2. builds and starts its devcontainer with the Dev Containers CLI (`devcontainer up`),
#   3. runs checks *inside the running container* (`devcontainer exec`):
#        - .devcontainer is read-only, claude-home is writable,
#        - host isolation matches the docker mode (no host block devices unless privileged),
#        - `ruff` and `pytest` pass, Django projects `migrate`,
#        - the Docker/GPU capability expected for the mode actually works,
#   4. tears the container(s) down.
#
# The repo's own `pytest` suite only checks generated file content; this exercises the real
# containers, which is where build/runtime bugs show up.
#
# Requirements on the host: docker, uv, and the Dev Containers CLI (`devcontainer`, or it is
# run via `npx @devcontainers/cli`). Variants that need capabilities the host lacks are
# skipped automatically: `sysbox` needs the `sysbox-runc` runtime, `gpu` needs working
# `--gpus all`.
#
# Usage:
#   scripts/e2e.sh                     # run every supported variant
#   scripts/e2e.sh --only py-default,dj-sqlite
#   scripts/e2e.sh --list              # list variant names and exit
#   scripts/e2e.sh --work-dir /tmp/e2e --keep   # custom dir, keep containers for debugging
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK_DIR=""
KEEP=0
ONLY=""

while [ $# -gt 0 ]; do
  case "$1" in
    --work-dir) WORK_DIR="$2"; shift 2 ;;
    --only) ONLY="$2"; shift 2 ;;
    --keep) KEEP=1; shift ;;
    --list) LIST_ONLY=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

# All known variants:
#   "name|project_type|extra answer keys as k=v (space separated)|scaffold mode"
# Scaffold mode is empty for `cdforge new`, or `adopt` to check the adoption path: the
# project is generated, its cdforge-managed files are then deleted (and, for a compose
# project, its docker-compose.yml is replaced by one of the project's own) to look like a
# project that predates cdforge, and `cdforge adopt` has to make it work again.
VARIANTS=(
  "py-default|python_uv_tool|"
  "py-privileged|python_uv_tool|docker_mode=privileged"
  "py-sysbox|python_uv_tool|docker_mode=sysbox"
  "py-gpu|python_uv_tool|gpu_enabled=true"
  "dj-sqlite|django_drf|database=sqlite include_celery=false"
  "dj-postgres-celery|django_drf|database=postgres include_celery=true"
  "dj-privileged|django_drf|database=postgres include_celery=true docker_mode=privileged"
  "py-firewall|python_uv_tool|network_firewall=allowlist"
  "py-firewall-strict|python_uv_tool|network_firewall=strict"
  "dj-firewall|django_drf|database=postgres include_celery=true network_firewall=allowlist"
  "py-adopt|python_uv_tool||adopt"
  "dj-adopt|django_drf|database=postgres include_celery=false|adopt"
)

if [ "${LIST_ONLY:-0}" = 1 ]; then
  printf '%s\n' "${VARIANTS[@]}" | cut -d'|' -f1
  exit 0
fi

# --- locate tools -----------------------------------------------------------------------
if command -v devcontainer >/dev/null 2>&1; then
  DEVCONTAINER=(devcontainer)
else
  echo "note: 'devcontainer' not on PATH, using 'npx @devcontainers/cli'" >&2
  DEVCONTAINER=(npx --yes @devcontainers/cli)
fi
command -v docker >/dev/null 2>&1 || { echo "docker is required" >&2; exit 2; }
command -v uv >/dev/null 2>&1 || { echo "uv is required" >&2; exit 2; }

# --- host capability probes -------------------------------------------------------------
HAS_SYSBOX=0
docker info --format '{{json .Runtimes}}' 2>/dev/null | grep -q 'sysbox-runc' && HAS_SYSBOX=1
HAS_GPU=0
docker run --rm --gpus all hello-world >/dev/null 2>&1 && HAS_GPU=1

WORK_DIR="${WORK_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/cdforge-e2e.XXXXXX")}"
mkdir -p "$WORK_DIR"
echo "Work dir: $WORK_DIR"
echo "Host capabilities: sysbox=$HAS_SYSBOX gpu=$HAS_GPU"
echo

declare -a RESULTS

# Write an answers file for a variant. $1=path $2=name $3=project_type $4=extra k=v...
write_answers() {
  local path="$1" name="$2" ptype="$3"; shift 3
  local extras="$*"
  python3 - "$path" "$name" "$ptype" "$extras" <<'PY'
import json, sys
path, name, ptype, extras = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
a = {
    "project_name": name,
    "project_type": ptype,
    "git_remote_url": "",
    "gpu_enabled": False,
    "docker_mode": "none",
    "optional_skills": [],
    "author_name": "E2E",
    "author_email": "e2e@example.com",
}
if ptype == "python_uv_tool":
    a.update(package_import_name="app_tool", cli_command_name="app-tool",
             python_version="3.12", include_mypy=True, license_id="MIT")
else:
    a.update(django_project_slug="app_config", initial_app_name="core",
             database="postgres", auth_method="simplejwt", include_celery=False,
             api_docs="drf-spectacular")
for kv in extras.split():
    k, _, v = kv.partition("=")
    if v in ("true", "false"):
        v = (v == "true")
    a[k] = v
json.dump(a, open(path, "w"), indent=2)
PY
}

# Body run inside the container. Args: PROJECT_TYPE DOCKER_MODE GPU
container_checks() {
  cat <<'EOS'
set -u
fail=0
ok(){  printf '    %-34s OK\n'   "$1"; }
bad(){ printf '    %-34s FAIL: %s\n' "$1" "$2"; fail=1; }

if (echo x > .devcontainer/devcontainer.json) 2>/dev/null; then bad ".devcontainer read-only" "was writable"; else ok ".devcontainer read-only"; fi
if (echo x > "$HOME/.claude/.probe") 2>/dev/null; then ok "claude-home writable"; rm -f "$HOME/.claude/.probe"; else bad "claude-home writable" "not writable"; fi

host_dev=$(ls /dev/sd* /dev/nvme* 2>/dev/null | wc -l)
if [ "$E2E_MODE" = "privileged" ]; then
  printf '    %-34s %s host block devices (expected)\n' "privileged host access" "$host_dev"
else
  if [ "$host_dev" -eq 0 ]; then ok "no host block devices"; else bad "no host block devices" "found $host_dev"; fi
fi

uv run ruff check . >/dev/null 2>&1 && ok "ruff check" || bad "ruff check" "lint errors"
if uv run pytest -q >/tmp/e2e_pytest.log 2>&1; then ok "pytest"; else bad "pytest" "failing"; tail -8 /tmp/e2e_pytest.log; fi

if [ "$E2E_PTYPE" = "django_drf" ]; then
  if uv run python manage.py migrate --noinput >/tmp/e2e_migrate.log 2>&1; then ok "django migrate"; else bad "django migrate" "failed"; tail -8 /tmp/e2e_migrate.log; fi
fi

case "$E2E_MODE" in
  none)
    if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then bad "docker absent (mode none)" "docker is usable"; else ok "no in-container docker"; fi ;;
  sysbox|privileged)
    if docker run --rm hello-world >/dev/null 2>&1; then ok "in-container docker works"; else bad "in-container docker" "hello-world failed"; fi ;;
esac

if [ "$E2E_FIREWALL" != "none" ]; then
  gw="$(ip route show default | awk '{print $3}' | head -1)"
  # The point of the firewall: the host, one hop away at the bridge gateway, is unreachable.
  # (Best-effort: it only proves anything on a host with something listening on :22.)
  if [ -n "$gw" ] && timeout 4 bash -c "echo > /dev/tcp/${gw}/22" 2>/dev/null; then
    bad "host gateway blocked" "connected to ${gw}:22"
  else
    ok "host gateway blocked"
  fi
  # ...while the allowlist still lets Claude Code and the toolchain out.
  if curl -s -m 15 -o /dev/null https://pypi.org/simple/ 2>/dev/null; then ok "allowlist reachable"; else bad "allowlist reachable" "pypi.org unreachable"; fi
  if curl -s -m 8 -o /dev/null https://example.com 2>/dev/null; then bad "off-allowlist blocked" "example.com reachable"; else ok "off-allowlist blocked"; fi
fi
if [ "$E2E_FIREWALL" = "strict" ]; then
  if sudo -n true 2>/dev/null; then bad "no blanket sudo" "sudo -n true succeeded"; else ok "no blanket sudo"; fi
  if sudo -n /usr/local/bin/cdforge-firewall >/dev/null 2>&1; then ok "firewall re-appliable"; else bad "firewall re-appliable" "sudo cdforge-firewall failed"; fi
fi

if [ "$E2E_GPU" = "true" ]; then
  if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi -L >/dev/null 2>&1; then ok "gpu visible"; else bad "gpu visible" "nvidia-smi failed"; fi
fi

exit $fail
EOS
}

run_variant() {
  local spec="$1"
  local name ptype extras smode
  name="$(echo "$spec" | cut -d'|' -f1)"
  ptype="$(echo "$spec" | cut -d'|' -f2)"
  extras="$(echo "$spec" | cut -d'|' -f3)"
  smode="$(echo "$spec" | cut -d'|' -f4)"

  # capability gating
  case "$extras" in
    *docker_mode=sysbox*) if [ "$HAS_SYSBOX" != 1 ]; then echo "SKIP $name (no sysbox-runc runtime on host)"; RESULTS+=("SKIP  $name"); return; fi ;;
  esac
  case "$extras" in
    *gpu_enabled=true*) if [ "$HAS_GPU" != 1 ]; then echo "SKIP $name (no working --gpus all on host)"; RESULTS+=("SKIP  $name"); return; fi ;;
  esac

  local mode="none"; case "$extras" in *docker_mode=sysbox*) mode=sysbox ;; *docker_mode=privileged*) mode=privileged ;; esac
  local gpu="false"; case "$extras" in *gpu_enabled=true*) gpu=true ;; esac
  local firewall="none"; case "$extras" in *network_firewall=strict*) firewall=strict ;; *network_firewall=allowlist*) firewall=allowlist ;; esac

  local proj="$WORK_DIR/$name"
  local ans="$WORK_DIR/$name.json"
  echo "==================== $name ($ptype, docker=$mode, gpu=$gpu, firewall=$firewall, scaffold=${smode:-new}) ===================="
  rm -rf "$proj"
  write_answers "$ans" "$name" "$ptype" "$extras"

  ( cd "$REPO_ROOT" && uv run cdforge new --answers-file "$ans" --output-dir "$proj" --non-interactive ) >/dev/null 2>&1 \
    || { echo "  scaffold FAILED"; RESULTS+=("FAIL  $name (scaffold)"); return; }
  if [ "$smode" = "adopt" ]; then
    # Make the generated project look like one that predates cdforge: drop everything the
    # tool manages, and give a compose project a docker-compose.yml of its own so adoption
    # has to add the devcontainer services as an override instead of overwriting it.
    rm -rf "$proj/.devcontainer" "$proj/.claude" "$proj/.githooks" "$proj/.cdforge.json"
    if [ -f "$proj/docker-compose.yml" ]; then
      printf 'services:\n  legacy:\n    image: alpine:3.20\n    command: sleep infinity\n' \
        > "$proj/docker-compose.yml"
    fi
    ( cd "$REPO_ROOT" && uv run cdforge adopt "$proj" --answers-file "$ans" --force ) \
      || { echo "  adopt FAILED"; RESULTS+=("FAIL  $name (adopt)"); return; }
    if [ -f "$proj/.devcontainer/docker-compose.cdforge.yml" ]; then
      echo "  (adopted with a compose override)"
    fi
  fi
  mkdir -p "$proj/.devcontainer/claude-home"

  local uplog="$WORK_DIR/$name.up.log"
  if ! "${DEVCONTAINER[@]}" up --workspace-folder "$proj" >"$uplog" 2>&1; then
    echo "  devcontainer up FAILED (see $uplog)"; tail -6 "$uplog" | sed 's/^/    /'
    RESULTS+=("FAIL  $name (up)"); teardown "$proj" "$uplog"; return
  fi

  local body; body="$(container_checks)"
  local pre="export E2E_PTYPE='$ptype' E2E_MODE='$mode' E2E_GPU='$gpu' E2E_FIREWALL='$firewall';"
  if "${DEVCONTAINER[@]}" exec --workspace-folder "$proj" bash -lc "$pre $body"; then
    echo "  -> PASS"; RESULTS+=("PASS  $name")
  else
    echo "  -> FAIL"; RESULTS+=("FAIL  $name (checks)")
  fi
  teardown "$proj" "$uplog"
}

teardown() {
  local proj="$1" uplog="$2"
  [ "$KEEP" = 1 ] && { echo "  (kept: $proj)"; return; }
  # compose-based projects: bring the whole project down
  if [ -f "$proj/docker-compose.yml" ]; then
    ( cd "$proj" && docker compose down -v >/dev/null 2>&1 ) || true
  fi
  # build-based projects: remove the single container by id from the up log
  local cid
  cid="$(grep -o '"containerId":"[0-9a-f]*"' "$uplog" 2>/dev/null | head -1 | cut -d'"' -f4)"
  [ -n "${cid:-}" ] && docker rm -f "$cid" >/dev/null 2>&1 || true
}

# --- run --------------------------------------------------------------------------------
for spec in "${VARIANTS[@]}"; do
  name="$(echo "$spec" | cut -d'|' -f1)"
  if [ -n "$ONLY" ]; then case ",$ONLY," in *",$name,"*) ;; *) continue ;; esac; fi
  run_variant "$spec"
  echo
done

echo "================================ SUMMARY ================================"
printf '%s\n' "${RESULTS[@]}"
# non-zero exit if anything failed
printf '%s\n' "${RESULTS[@]}" | grep -q '^FAIL' && exit 1 || exit 0
