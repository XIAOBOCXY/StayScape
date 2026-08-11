#!/usr/bin/env bash
set -Eeuo pipefail

# One-command local/ECS deployment.  The default is demo mode (Mock Agent).
# Set MODE=live or pass "live" to build and run the private OpenClaw Gateway.

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

MODE="${MODE:-${1:-demo}}"
case "$MODE" in
  demo|live) ;;
  *) echo "MODE must be demo or live" >&2; exit 2 ;;
esac

log() { printf '\n[StayScape] %s\n' "$*"; }
fail() { printf '\n[StayScape] ERROR: %s\n' "$*" >&2; exit 1; }

if ! command -v docker >/dev/null 2>&1; then
  if [[ "${INSTALL_DOCKER:-false}" == "true" ]]; then
    log "Installing Docker with the official get.docker.com bootstrap"
    curl -fsSL https://get.docker.com | sh
    sudo systemctl enable --now docker
  else
    fail "Docker is required. Install Docker Engine/Compose v2 or rerun with INSTALL_DOCKER=true on a supported Linux ECS."
  fi
fi
docker compose version >/dev/null 2>&1 || fail "Docker Compose v2 is required."

created_env=false
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  created_env=true
  log "Created .env from .env.example"
fi

random_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

set_env() {
  local key="$1" value="$2" escaped
  escaped="$(printf '%s' "$value" | sed 's/[&|]/\\&/g')"
  if grep -qE "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" .env
  else
    printf '%s=%s\n' "$key" "$value" >> .env
  fi
}

env_value() {
  local key="$1"
  sed -n "s/^${key}=//p" .env | tail -n 1
}

set_env APP_ENV production
set_env MODE "$MODE"
set_env STAYSCAPE_HTTP_PORT "${STAYSCAPE_HTTP_PORT:-80}"
set_env POSTGRES_DB "$(env_value POSTGRES_DB)"
set_env POSTGRES_USER "$(env_value POSTGRES_USER)"
[[ -n "$(env_value POSTGRES_DB)" ]] || set_env POSTGRES_DB stayscape
[[ -n "$(env_value POSTGRES_USER)" ]] || set_env POSTGRES_USER stayscape
set_env SEED_DEMO_ON_STARTUP "${SEED_DEMO_ON_STARTUP:-true}"
set_env STAYSCAPE_API_INTERNAL_URL http://server:8000
set_env STAYSCAPE_HOTEL_ID "${STAYSCAPE_HOTEL_ID:-1}"
set_env OPENCLAW_AGENT_ID stayscape-main
set_env OPENCLAW_TRANSPORT responses
set_env OPENCLAW_RESPONSES_PATH /v1/responses
set_env OPENCLAW_RUNTIME_VERSION 2026.6.6
set_env OPENCLAW_IMAGE ghcr.io/openclaw/openclaw:2026.6.6

secret_key="$(env_value SECRET_KEY)"
[[ -n "$secret_key" && "$secret_key" != change-me* ]] || set_env SECRET_KEY "$(random_hex)"
postgres_password="$(env_value POSTGRES_PASSWORD)"
[[ -n "$postgres_password" && "$postgres_password" != change-me* ]] || set_env POSTGRES_PASSWORD "$(random_hex)"

if [[ "$MODE" == "live" ]]; then
  set_env AGENT_PROVIDER openclaw
  set_env OPENCLAW_BASE_URL http://openclaw:18789
  gateway_token="$(env_value OPENCLAW_GATEWAY_TOKEN)"
  [[ -n "$gateway_token" ]] || set_env OPENCLAW_GATEWAY_TOKEN "$(random_hex)"
  tool_token="$(env_value STAYSCAPE_AGENT_TOOL_TOKEN)"
  [[ -n "$tool_token" ]] || set_env STAYSCAPE_AGENT_TOOL_TOKEN "$(random_hex)"
  set_env OPENCLAW_SKILLS_READY false
else
  set_env AGENT_PROVIDER mock
  set_env OPENCLAW_SKILLS_READY false
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

if [[ "$MODE" == "live" ]]; then
  python3 scripts/render_openclaw_config.py
fi

log "Validating Compose configuration"
if [[ "$MODE" == "live" ]]; then
  docker compose --env-file .env --profile live config >/dev/null
else
  docker compose --env-file .env config >/dev/null
fi
log "Building and starting StayScape in $MODE mode"
if [[ "$MODE" == "live" ]]; then
  docker compose --env-file .env --profile live up -d --build
else
  docker compose --env-file .env up -d --build
fi

port="$(env_value STAYSCAPE_HTTP_PORT)"
port="${port:-80}"
log "Waiting for the public application health endpoint"
for attempt in $(seq 1 48); do
  if command -v curl >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:${port}/health" >/dev/null; then
    break
  fi
  if [[ "$attempt" == 48 ]]; then
    if [[ "$MODE" == "live" ]]; then
      docker compose --env-file .env --profile live ps
      docker compose --env-file .env --profile live logs --tail=100 server nginx openclaw || true
    else
      docker compose --env-file .env ps
      docker compose --env-file .env logs --tail=100 server nginx || true
    fi
    fail "StayScape did not become healthy in time"
  fi
  sleep 5
done

if [[ "$MODE" == "live" ]]; then
  log "Discovering both Skills through the OpenClaw CLI"
  docker compose --env-file .env --profile live exec -T openclaw openclaw skills list --agent stayscape-main --json \
    | python3 scripts/verify_openclaw_skills.py
  set_env OPENCLAW_SKILLS_READY true
  set -a
  . ./.env
  set +a
  docker compose --env-file .env --profile live up -d server
  log "OpenClaw discovery passed; FastAPI now reports LIVE readiness"
else
  log "Demo mode is ready: Agent provider=MOCK, no external model credentials required"
fi

if [[ "$MODE" == "live" ]]; then
  docker compose --env-file .env --profile live ps
else
  docker compose --env-file .env ps
fi
log "Deployment complete: http://127.0.0.1:${port}"
if [[ "$MODE" == "live" ]]; then
  log "Live runtime: one private OpenClaw Gateway, Agent stayscape-main, two Skills"
  log "If a model provider needs first-time OAuth/API authorization, complete that one provider-specific step now."
fi
