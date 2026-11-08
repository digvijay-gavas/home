@echo off
setlocal
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist ".venv\Scripts\pythonw.exe" (
    echo Run setup.ps1 in this folder first to install Bobo.
    pause
    popd
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "controller.py" %*
popd
