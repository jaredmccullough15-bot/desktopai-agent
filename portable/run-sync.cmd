@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "ROOT=%SCRIPT_DIR%.."

REM Activate venv or run setup
if not exist "%ROOT%\venv\Scripts\Activate.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%\setup.ps1"
)

powershell -NoProfile -ExecutionPolicy Bypass -NoExit -File "%SCRIPT_DIR%run-sync.ps1"
endlocal
