#!/usr/bin/env bash
set -Eeuo pipefail

# Backward-compatible entry point for the competition deployment guide. The
# complete deployment now lives in deploy.sh and includes the private pinned
# OpenClaw Gateway in live mode.
ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
exec "$ROOT_DIR/scripts/deploy.sh" live "$@"
