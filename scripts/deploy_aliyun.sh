#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy StayScape on a Linux ECS that already has Docker Engine and Compose v2.
# OpenClaw is intentionally not exposed by this script: the Gateway should stay
# on the private host network and be called only by the StayScape API container.

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

log() { printf '\n[StayScape] %s\n' "$*"; }
fail() { printf '\n[StayScape] ERROR: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || fail "未检测到 Docker。请先安装 Docker Engine，再重新执行本脚本。"
docker compose version >/dev/null 2>&1 || fail "未检测到 Docker Compose v2。请先升级 Docker，再重新执行本脚本。"

created_env=false
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  created_env=true
  log "已从 .env.example 创建 .env"
fi

random_hex() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

set_env() {
  local key="$1"
  local value="$2"
  local escaped
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

# Production-safe defaults. Existing non-placeholder values are preserved.
previous_app_env="$(env_value APP_ENV)"
previous_http_port="$(env_value STAYSCAPE_HTTP_PORT)"
set_env APP_ENV production
if [[ "$created_env" == true || -z "$previous_http_port" || ( "$previous_app_env" != "production" && "$previous_http_port" == "8080" ) ]]; then
  set_env STAYSCAPE_HTTP_PORT 80
fi
if [[ -z "$(env_value SEED_DEMO_ON_STARTUP)" ]]; then set_env SEED_DEMO_ON_STARTUP true; fi
if [[ -z "$(env_value POSTGRES_DB)" ]]; then set_env POSTGRES_DB stayscape; fi
if [[ -z "$(env_value POSTGRES_USER)" ]]; then set_env POSTGRES_USER stayscape; fi

secret_key="$(env_value SECRET_KEY)"
if [[ -z "$secret_key" || "$secret_key" == change-me* ]]; then
  set_env SECRET_KEY "$(random_hex)"
fi
postgres_password="$(env_value POSTGRES_PASSWORD)"
if [[ -z "$postgres_password" || "$postgres_password" == change-me* ]]; then
  set_env POSTGRES_PASSWORD "$(random_hex)"
fi

log "开始构建并启动 PostgreSQL、FastAPI、Vue 和 Nginx"
docker compose --env-file .env up -d --build

port="$(env_value STAYSCAPE_HTTP_PORT)"
port="${port:-80}"
log "等待应用健康检查"
for attempt in $(seq 1 36); do
  if command -v curl >/dev/null 2>&1 && curl -fsS "http://127.0.0.1:${port}/health" >/dev/null; then
    break
  fi
  if [[ "$attempt" == 36 ]]; then
    docker compose --env-file .env ps
    docker compose --env-file .env logs --tail=80 server nginx
    fail "应用未在预期时间内启动，请查看上面的容器日志。"
  fi
  sleep 5
done

docker compose --env-file .env ps
log "部署完成：请访问 http://<ECS公网IP>:${port}"
log "首次演示可保持 SEED_DEMO_ON_STARTUP=true；确认数据后可改为 false 并执行 docker compose up -d。"
log "OpenClaw 配置请参阅 docs/DEPLOY_ALIYUN.md，不要把 18789 暴露到公网。"
