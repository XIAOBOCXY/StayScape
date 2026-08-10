#!/usr/bin/env bash
set -Eeuo pipefail

# Official OpenClaw installer wrapper. Run this on the Alibaba Cloud Linux ECS,
# not in the StayScape API container. The official installer provisions Node
# when necessary and starts the guided onboarding flow.

command -v curl >/dev/null 2>&1 || {
  echo "请先安装 curl：sudo apt-get update && sudo apt-get install -y curl" >&2
  exit 1
}

curl -fsSL https://openclaw.ai/install.sh | bash
command -v openclaw >/dev/null 2>&1 || {
  echo "openclaw 未进入当前 PATH，请重新登录 SSH 后再执行 openclaw --version。" >&2
  exit 1
}

openclaw --version
openclaw onboard --install-daemon

echo
echo "OpenClaw 已安装。接下来请按 docs/DEPLOY_ALIYUN.md 开启 Responses API、安装两个 StayScape Skill，并把 Gateway Token 写入 StayScape 的服务端 .env。"
