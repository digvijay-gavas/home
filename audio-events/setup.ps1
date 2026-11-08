$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    if (-not (Test-Path '.venv/Scripts/python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Could not create virtual environment. Install Python 3.10+ x64.' }
    }
    & ./.venv/Scripts/python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & ./.venv/Scripts/python.exe download_model.py
    if ($LASTEXITCODE -ne 0) { throw 'Model download failed.' }
    Write-Host 'Ready. Run ./start.ps1 to listen, or ./start.ps1 --list-devices to choose a microphone.'
} finally {
    Pop-Location
}
