#!/usr/bin/env sh
set -eu

alembic upgrade head
python /app/scripts/seed_demo.py
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

