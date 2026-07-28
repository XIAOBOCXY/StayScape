$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
.venv\Scripts\python.exe -m pytest apps\server\tests -q
npm.cmd --prefix apps\web run build
.venv\Scripts\python.exe scripts\package_skills.py

