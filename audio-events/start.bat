@echo off
setlocal
title Hey Bobo - Audio Events
pushd "%~dp0"
if errorlevel 1 exit /b 1

if not exist ".venv\Scripts\python.exe" (
    echo Run setup.ps1 in this folder first to install the listener.
    pause
    popd
    exit /b 1
)

".venv\Scripts\python.exe" "runtime.py" %*
set "listener_exit=%errorlevel%"
if not "%listener_exit%"=="0" (
    echo.
    echo Listener exited with code %listener_exit%.
    pause
)
popd
exit /b %listener_exit%
