#!/usr/bin/env bash
set -Eeuo pipefail

cat >&2 <<'EOF'
This project no longer installs a separate native OpenClaw daemon.
The supported deployment is the pinned official OpenClaw Docker image in
scripts/deploy.sh live, which keeps Gateway port 18789 on the private Docker
network and persists config, workspace, plugin and channel state.
EOF

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT_DIR/scripts/deploy.sh" live "$@"
