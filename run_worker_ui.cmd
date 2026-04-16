@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%SCRIPT_DIR%run_worker_ui.ps1"
endlocal
