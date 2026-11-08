$ErrorActionPreference = 'Stop'
$python = Join-Path $PSScriptRoot '.venv/Scripts/python.exe'
if (-not (Test-Path $python)) { throw 'Run audio-events/setup.ps1 first.' }
& $python (Join-Path $PSScriptRoot 'listener.py') @args
exit $LASTEXITCODE
