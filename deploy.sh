#!/usr/bin/env bash
# ============================================================
# deploy.sh — rebuild the fast-trade images and (re)start the stack.
#
# Brings up the default-profile services defined in docker-compose.yml:
#   timescaledb · redis · api-gateway · data-ingestor · backtest-worker
#   go-proxy · strategy-lab · replay-api
# (the `cli` service is profile-gated and is NOT started here.)
#
# replay-api is the trading-facing 5s-replay engine (:8001) the OpenAlgo
# dashboard calls. It bakes the engine-agnostic shared_strategies package from
# an EXTERNAL build context — the sibling algotrading-strategies checkout. Set
# STRATEGIES_PATH if it lives somewhere other than the compose default
# (/mnt/projects/algotrading/algotrading-strategies); this script fails fast
# when that path is missing and replay-api is in scope.
#
# Usage:
#   ./deploy.sh [-y] [--no-build] [--pull] [--recreate] [SERVICE ...]
#
#   -y, --yes        skip the confirmation prompt
#   --no-build       start without rebuilding images
#   --pull           pull newer base images before building
#   --recreate       force-recreate containers even if config is unchanged
#   -h, --help       show this help
#   SERVICE ...      limit the action to the named service(s)
#
# Examples:
#   ./deploy.sh -y                 # rebuild changed images + start everything
#   ./deploy.sh --no-build -y      # just (re)start containers
#   ./deploy.sh --pull api-gateway # rebuild only the API, pulling base images
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

usage() {
  cat <<'EOF'
deploy.sh — rebuild the fast-trade images and (re)start the stack.

Starts the default-profile services from docker-compose.yml:
  timescaledb · redis · api-gateway · data-ingestor · backtest-worker
  go-proxy · strategy-lab · replay-api  (cli is profile-gated, not started)

replay-api (5s-replay engine, :8001) bakes shared_strategies from an external
build context — set STRATEGIES_PATH if it is not at the compose default.

Usage:
  ./deploy.sh [-y] [--no-build] [--pull] [--recreate] [SERVICE ...]

  -y, --yes      skip the confirmation prompt
  --no-build     start without rebuilding images
  --pull         pull newer base images before building
  --recreate     force-recreate containers even if config is unchanged
  -h, --help     show this help
  SERVICE ...    limit the action to the named service(s)

Examples:
  ./deploy.sh -y                 # rebuild changed images + start everything
  ./deploy.sh --no-build -y      # just (re)start containers
  ./deploy.sh --pull api-gateway # rebuild only the API, pulling base images
EOF
}

# ── flags ───────────────────────────────────────────────────
ASSUME_YES=0
DO_BUILD=1
DO_PULL=0
FORCE_RECREATE=0
SERVICES=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -y|--yes)      ASSUME_YES=1 ;;
    --no-build)    DO_BUILD=0 ;;
    --pull)        DO_PULL=1 ;;
    --recreate)    FORCE_RECREATE=1 ;;
    -h|--help)     usage; exit 0 ;;
    -*)            echo "Unknown option: $1" >&2; exit 2 ;;
    *)             SERVICES+=("$1") ;;
  esac
  shift
done

log()  { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# ── preflight ───────────────────────────────────────────────
command -v docker >/dev/null 2>&1 || die "docker is not installed / not on PATH"
docker compose version >/dev/null 2>&1 || die "docker compose v2 plugin is required"
docker info >/dev/null 2>&1 || die "the docker daemon is not reachable (is it running?)"

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    warn ".env missing — copying from .env.example (edit secrets before a real deploy)"
    cp .env.example .env
  else
    warn ".env missing — compose will fall back to the built-in defaults"
  fi
fi

# Services that publish a healthcheck (used by the readiness wait below).
HEALTHCHECKED=(ft-timescaledb ft-redis ft-api ft-go-proxy ft-replay-api)

# replay-api's image is built with an ADDITIONAL build context (the external
# shared_strategies checkout). Compose reads it from STRATEGIES_PATH; default it
# here too so the missing-path preflight below matches what the build will use.
STRATEGIES_PATH="${STRATEGIES_PATH:-/mnt/projects/algotrading/algotrading-strategies}"

# ── resolve target services + drop ones with a missing Dockerfile ───────────
# `docker compose config --services` lists the active-profile services (the cli
# profile is excluded). A service whose build context lacks its Dockerfile (e.g.
# a half-removed service still referenced in compose) would abort the whole build,
# so we filter those out with a warning rather than failing the deploy.
mapfile -t ALL_SERVICES < <(docker compose config --services 2>/dev/null || true)
if [[ ${#SERVICES[@]} -gt 0 ]]; then
  TARGETS=("${SERVICES[@]}")
else
  TARGETS=("${ALL_SERVICES[@]}")
fi

missing_dockerfiles() {
  # Emits the name of each requested service whose build Dockerfile is absent.
  command -v python3 >/dev/null 2>&1 || return 0   # no python → skip the check
  local cfg_json
  cfg_json="$(docker compose config --format json 2>/dev/null)" || return 0
  [[ -z "$cfg_json" ]] && return 0
  # Pass the JSON via an env var (NOT stdin) — the heredoc below is python's stdin.
  COMPOSE_CFG_JSON="$cfg_json" python3 - "$SCRIPT_DIR" <<'PY'
import json, os, sys
base = sys.argv[1]
try:
    cfg = json.loads(os.environ["COMPOSE_CFG_JSON"])
except Exception:
    sys.exit(0)
for name, svc in (cfg.get("services") or {}).items():
    b = svc.get("build")
    if not b:
        continue
    if isinstance(b, str):
        ctx, df = b, "Dockerfile"
    else:
        ctx, df = b.get("context", "."), b.get("dockerfile", "Dockerfile")
    ctx = ctx if os.path.isabs(ctx) else os.path.join(base, ctx)
    df = df if os.path.isabs(df) else os.path.join(ctx, df)
    if not os.path.isfile(df):
        print(name)
PY
}

mapfile -t BROKEN < <(missing_dockerfiles)
FILTERED=()
SKIPPED=()
for s in "${TARGETS[@]}"; do
  skip=0
  for b in "${BROKEN[@]}"; do [[ "$s" == "$b" ]] && skip=1; done
  if [[ $skip == 1 ]]; then SKIPPED+=("$s"); else FILTERED+=("$s"); fi
done
[[ ${#FILTERED[@]} -eq 0 ]] && die "no deployable services (all targets have a missing Dockerfile)"
[[ ${#SKIPPED[@]} -gt 0 ]] && warn "Skipping (missing Dockerfile): ${SKIPPED[*]}"

# replay-api can only build with its external shared_strategies context present.
# Check it up front (when replay-api is in scope and we intend to build) so the
# build fails here with a clear message instead of a cryptic compose error.
if [[ $DO_BUILD == 1 ]] && printf '%s\n' "${FILTERED[@]}" | grep -qx replay-api; then
  [[ -d "$STRATEGIES_PATH" ]] \
    || die "replay-api build context not found: STRATEGIES_PATH=$STRATEGIES_PATH (point it at the algotrading-strategies checkout)"
  ok "replay-api strategies context: $STRATEGIES_PATH"
fi

# The compose file pins container_name (ft-*). If a container with one of those
# names exists but belongs to ANOTHER compose project, `up` aborts on the name
# clash. Abort on a RUNNING foreign container (don't disrupt it); remove a STOPPED
# stale one (volumes persist, so this is safe) after consent.
resolve_name_conflicts() {
  command -v python3 >/dev/null 2>&1 || return 0
  local cfg_json our_project names
  cfg_json="$(docker compose config --format json 2>/dev/null)" || return 0
  [[ -z "$cfg_json" ]] && return 0
  our_project="$(COMPOSE_CFG_JSON="$cfg_json" python3 -c \
    'import json,os;print(json.loads(os.environ["COMPOSE_CFG_JSON"]).get("name",""))')"
  names="$(COMPOSE_CFG_JSON="$cfg_json" python3 - "${FILTERED[@]}" <<'PY'
import json, os, sys
cfg = json.loads(os.environ["COMPOSE_CFG_JSON"]); want = set(sys.argv[1:])
for n, s in (cfg.get("services") or {}).items():
    if n in want and s.get("container_name"):
        print(s["container_name"])
PY
)"
  local blockers=() removable=() cn proj running
  for cn in $names; do
    docker inspect "$cn" >/dev/null 2>&1 || continue
    proj="$(docker inspect -f '{{ index .Config.Labels "com.docker.compose.project" }}' "$cn" 2>/dev/null || true)"
    [[ "$proj" == "$our_project" ]] && continue          # ours — compose manages it
    running="$(docker inspect -f '{{.State.Running}}' "$cn" 2>/dev/null || echo false)"
    if [[ "$running" == "true" ]]; then
      blockers+=("$cn[project=${proj:-?}]")
    else
      removable+=("$cn")
    fi
  done
  if [[ ${#blockers[@]} -gt 0 ]]; then
    die "name clash with RUNNING containers from another project: ${blockers[*]} — stop or rename them first"
  fi
  if [[ ${#removable[@]} -gt 0 ]]; then
    warn "Stopped containers from another project hold our names: ${removable[*]}"
    if [[ $ASSUME_YES -ne 1 ]]; then
      read -r -p "Remove these stopped containers? [y/N] " r
      [[ "$r" =~ ^[Yy]$ ]] || die "aborted (unresolved name clash)"
    fi
    docker rm "${removable[@]}" >/dev/null && ok "Removed stale containers: ${removable[*]}"
  fi
}

# ── plan + confirm ──────────────────────────────────────────
TARGET_DESC="${FILTERED[*]}"
log "Target:        $TARGET_DESC"
log "Rebuild:       $([[ $DO_BUILD == 1 ]] && echo yes || echo 'no (--no-build)')"
log "Pull base img: $([[ $DO_PULL == 1 ]] && echo yes || echo no)"
log "Force-recreate:$([[ $FORCE_RECREATE == 1 ]] && echo yes || echo no)"

if [[ $ASSUME_YES -ne 1 ]]; then
  read -r -p "Proceed? [y/N] " reply
  [[ "$reply" =~ ^[Yy]$ ]] || die "aborted"
fi

# ── build ───────────────────────────────────────────────────
if [[ $DO_BUILD == 1 ]]; then
  build_args=(build)
  [[ $DO_PULL == 1 ]] && build_args+=(--pull)
  log "Building images…"
  docker compose "${build_args[@]}" "${FILTERED[@]}"
  ok "Images built"
else
  warn "Skipping build (--no-build)"
fi

# ── up ──────────────────────────────────────────────────────
resolve_name_conflicts
up_args=(up -d)
[[ ${#SERVICES[@]} -eq 0 ]] && up_args+=(--remove-orphans)   # safe only on a full deploy
[[ $FORCE_RECREATE == 1 ]] && up_args+=(--force-recreate)
log "Starting containers…"
docker compose "${up_args[@]}" "${FILTERED[@]}"
ok "Containers started"

# ── readiness wait ──────────────────────────────────────────
# Only wait on services that actually declare a healthcheck and are running.
wait_healthy() {
  local name="$1" timeout="${2:-90}" waited=0 status
  docker inspect "$name" >/dev/null 2>&1 || return 0          # not part of this run
  # No healthcheck → nothing to wait for.
  if ! docker inspect -f '{{if .State.Health}}yes{{end}}' "$name" 2>/dev/null | grep -q yes; then
    return 0
  fi
  printf '  waiting for %s ' "$name"
  while true; do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$name" 2>/dev/null || echo missing)"
    case "$status" in
      healthy)   printf ' \033[1;32mhealthy\033[0m\n'; return 0 ;;
      unhealthy) printf ' \033[1;31munhealthy\033[0m\n'; return 1 ;;
      missing)   printf ' \033[1;33mgone\033[0m\n'; return 0 ;;
    esac
    (( waited >= timeout )) && { printf ' \033[1;33mtimeout (%ss)\033[0m\n' "$timeout"; return 1; }
    printf '.'; sleep 3; waited=$((waited + 3))
  done
}

log "Waiting for services to report healthy…"
health_ok=1
for c in "${HEALTHCHECKED[@]}"; do
  wait_healthy "$c" 120 || health_ok=0
done

# ── status ──────────────────────────────────────────────────
echo
log "Stack status:"
docker compose ps

echo
if [[ $health_ok == 1 ]]; then
  ok "Deploy complete."
else
  warn "Deploy finished, but some services are not healthy — check logs:"
  echo "    docker compose logs -f <service>"
fi

deployed() { printf '%s\n' "${FILTERED[@]}" | grep -qx "$1"; }
echo
echo "Endpoints (host):"
deployed replay-api    && echo "  • 5s Replay API (backtest) http://localhost:8001/health"
deployed api-gateway   && echo "  • Strategy API (FastAPI)  http://localhost:8000/health"
deployed go-proxy      && echo "  • Go proxy                http://localhost:9000/health"
deployed strategy-lab  && echo "  • Strategy Lab (React)    http://localhost:5174"
deployed timescaledb   && echo "  • TimescaleDB             localhost:5433  (db=fasttrade user=fasttrade)"
deployed redis         && echo "  • Redis                   localhost:6379"

cat <<'EOF'

Common follow-ups:
  docker compose ps                 # status
  docker compose logs -f api-gateway
  docker compose down               # stop the stack
  docker compose run --rm cli       # interactive shell (cli profile)
EOF

[[ $health_ok == 1 ]] || exit 1
