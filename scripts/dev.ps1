$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv }
.venv\Scripts\python.exe -m pip install -r apps\server\requirements.txt
.venv\Scripts\python.exe -m alembic -c apps\server\alembic.ini upgrade head
.venv\Scripts\python.exe scripts\seed_demo.py
npm.cmd --prefix apps\web install --cache apps\web\.npm-cache
Start-Process -WindowStyle Hidden -FilePath ".venv\Scripts\python.exe" -ArgumentList "-m uvicorn app.main:app --app-dir apps/server --host 0.0.0.0 --port 8000"
npm.cmd --prefix apps\web run dev -- --host 0.0.0.0
