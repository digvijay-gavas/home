@echo off
setlocal
title Bobo - Audio Events
pushd "%~dp0"
if errorlevel 1 exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo Run setup.ps1 in this folder first to install the listener.
    pause
    popd
    exit /b 1
)
".venv\Scripts\python.exe" "ui.py" %*
set "ui_exit=%errorlevel%"
if not "%ui_exit%"=="0" pause
popd
exit /b %ui_exit%
