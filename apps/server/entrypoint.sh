#!/usr/bin/env sh
set -eu

alembic upgrade head
if [ "${SEED_DEMO_ON_STARTUP:-true}" = "true" ]; then
  python /app/scripts/seed_demo.py
fi
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
