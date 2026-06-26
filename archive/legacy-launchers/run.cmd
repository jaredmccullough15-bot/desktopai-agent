@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
REM Launch PowerShell and keep the window open to show any errors/output
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%SCRIPT_DIR%run.ps1"
endlocal
