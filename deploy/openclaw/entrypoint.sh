#!/usr/bin/env sh
set -eu

OPENCLAW_HOME="${OPENCLAW_HOME:-/home/node/.openclaw}"
mkdir -p "$OPENCLAW_HOME/workspace/skills"

# Config is rendered by scripts/deploy.sh and copied into the persistent home
# only when the volume is first created.  This keeps channel/session state and
# the Agent workspace persistent without making the generated secret-bearing
# file part of the repository.
# The rendered file is the deployment source of truth.  It is copied into the
# persistent home so OpenClaw can update its own state without a read-only
# bind mount; a subsequent deploy refreshes the declarative config.
cp /opt/stayscape/openclaw.json "$OPENCLAW_HOME/openclaw.json"
cp -R /opt/stayscape/skills/. "$OPENCLAW_HOME/workspace/skills/"

exec node dist/index.js gateway --port 18789
