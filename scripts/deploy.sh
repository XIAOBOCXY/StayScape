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
primary_model="$(env_value OPENCLAW_PRIMARY_MODEL)"
[[ -n "$primary_model" ]] || fail "OPENCLAW_PRIMARY_MODEL must be set in .env before a live deployment"
set_env OPENCLAW_TRANSPORT responses
set_env OPENCLAW_RESPONSES_PATH /v1/responses
set_env OPENCLAW_RUNTIME_VERSION 2026.6.9
openclaw_image="$(env_value OPENCLAW_IMAGE)"
[[ -n "$openclaw_image" ]] || set_env OPENCLAW_IMAGE ghcr.io/openclaw/openclaw:2026.6.9-slim
openclaw_install_method="$(env_value OPENCLAW_INSTALL_METHOD)"
[[ -n "$openclaw_install_method" ]] || set_env OPENCLAW_INSTALL_METHOD image
openclaw_config_group_id="$(env_value OPENCLAW_CONFIG_GROUP_ID)"
[[ -n "$openclaw_config_group_id" ]] || set_env OPENCLAW_CONFIG_GROUP_ID 1000
openclaw_config_group_id="$(env_value OPENCLAW_CONFIG_GROUP_ID)"
[[ "$openclaw_config_group_id" =~ ^[0-9]+$ ]] || fail "OPENCLAW_CONFIG_GROUP_ID must be a numeric GID"

secret_key="$(env_value SECRET_KEY)"
[[ -n "$secret_key" && "$secret_key" != change-me* ]] || set_env SECRET_KEY "$(random_hex)"
postgres_password="$(env_value POSTGRES_PASSWORD)"
[[ -n "$postgres_password" && "$postgres_password" != change-me* ]] || set_env POSTGRES_PASSWORD "$(random_hex)"

if [[ "$MODE" == "live" ]]; then
  qwen_api_key="$(env_value QWEN_API_KEY)"
  [[ -n "$qwen_api_key" ]] || fail "Live mode requires QWEN_API_KEY in .env. Create a Qwen/Model Studio API key and keep it server-side; never commit or paste it into the browser."
  set_env AGENT_PROVIDER openclaw
  set_env OPENCLAW_BASE_URL http://openclaw:18789
  gateway_token="$(env_value OPENCLAW_GATEWAY_TOKEN)"
  [[ -n "$gateway_token" ]] || set_env OPENCLAW_GATEWAY_TOKEN "$(random_hex)"
  tool_token="$(env_value STAYSCAPE_AGENT_TOOL_TOKEN)"
  [[ -n "$tool_token" ]] || set_env STAYSCAPE_AGENT_TOOL_TOKEN "$(random_hex)"
  set_env OPENCLAW_SKILLS_READY false
  set_env OPENCLAW_LIVE_READY false
else
  set_env AGENT_PROVIDER mock
  set_env OPENCLAW_SKILLS_READY false
  set_env OPENCLAW_LIVE_READY false
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
  # The entrypoint copies the rendered secret-bearing config at container start,
  # so force a single Gateway recreation whenever Live configuration is rendered.
  docker compose --env-file .env --profile live up -d --force-recreate --no-deps openclaw
else
  docker compose --env-file .env up -d --build
fi

# Nginx otherwise keeps a stale Docker service IP after a backend recreation.
docker compose --env-file .env exec -T nginx nginx -t >/dev/null
docker compose --env-file .env exec -T nginx nginx -s reload >/dev/null

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
  log "Waiting for the private OpenClaw Gateway readiness endpoint"
  for attempt in $(seq 1 48); do
    if docker compose --env-file .env --profile live exec -T openclaw node -e "fetch('http://127.0.0.1:18789/readyz').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))" >/dev/null 2>&1; then
      break
    fi
    if [[ "$attempt" == 48 ]]; then
      docker compose --env-file .env --profile live logs --tail=100 openclaw || true
      fail "OpenClaw Gateway did not become ready in time"
    fi
    sleep 5
  done
  log "Verifying the single stayscape-main Agent"
  docker compose --env-file .env --profile live exec -T openclaw openclaw agents list --json \
    | python3 scripts/verify_openclaw_agent.py
  log "Discovering both Skills through the OpenClaw CLI"
  docker compose --env-file .env --profile live exec -T openclaw openclaw skills list --agent stayscape-main --json \
    | python3 scripts/verify_openclaw_skills.py
  log "Checking that both Skills are visible to stayscape-main"
  docker compose --env-file .env --profile live exec -T openclaw openclaw skills check --agent stayscape-main --json \
    | python3 scripts/verify_openclaw_skills.py
  log "Verifying official OpenClaw provider and StayScape Tool Plugin"
  plugin_json="$(mktemp)"
  trap 'rm -f "$plugin_json"' EXIT
  docker compose --env-file .env --profile live exec -T openclaw openclaw plugins list --json >"$plugin_json"
  FEISHU_ENABLED="$(env_value FEISHU_ENABLED)" python3 scripts/verify_openclaw_plugins.py <"$plugin_json"
  log "Verifying configured Qwen model"
  model_output="$(docker compose --env-file .env --profile live exec -T openclaw openclaw models list --provider qwen --all 2>&1)" || fail "OpenClaw Qwen provider is not available. Inspect: docker compose --profile live logs openclaw"
  printf '%s\n' "$model_output" | grep -Fq "${primary_model}" || fail "OpenClaw does not report the configured model ${primary_model}"
  log "Running one real OpenResponses smoke test through stayscape-main"
  docker compose --env-file .env --profile live exec -T openclaw node --input-type=module -e '
    const response = await fetch("http://127.0.0.1:18789/v1/responses", {
      method: "POST",
      headers: {
        "Authorization": "Bearer " + process.env.OPENCLAW_GATEWAY_TOKEN,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-openclaw-agent-id": "stayscape-main"
      },
      body: JSON.stringify({ model: "openclaw/default", input: "Reply with the single word READY.", store: false })
    });
    const raw = await response.text();
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      console.error("OpenResponses smoke test returned non-JSON HTTP " + response.status);
      process.exit(1);
    }
    const output = Array.isArray(payload.output)
      ? payload.output.flatMap((item) => Array.isArray(item?.content) ? item.content : [])
          .map((part) => typeof part?.text === "string" ? part.text : "")
          .filter(Boolean)
          .join("\n")
          .trim()
      : "";
    if (!response.ok || payload.status !== "completed" || output.toUpperCase() !== "READY") {
      console.error("OpenResponses smoke test failed: http=" + response.status + ", status=" + (payload.status || "missing") + ", output=" + JSON.stringify(output.slice(0, 160)));
      process.exit(1);
    }
    console.log("OpenResponses smoke test passed with validated READY output");
  ' || fail "OpenClaw Gateway or Qwen model smoke test failed"
  set_env OPENCLAW_SKILLS_READY true
  set_env OPENCLAW_LIVE_READY true
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
log "Hotel demo username: hotel_demo (enter the password manually; it is not embedded in the web bundle)"
if [[ "$MODE" == "live" ]]; then
  log "Live runtime: one private OpenClaw Gateway, Agent stayscape-main, two Skills"
  log "If a model provider needs first-time OAuth/API authorization, complete that one provider-specific step now."
fi
