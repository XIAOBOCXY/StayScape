$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv }
.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir apps/server --reload --host 0.0.0.0 --port 8000

