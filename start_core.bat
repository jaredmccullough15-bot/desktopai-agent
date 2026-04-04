@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "CORE_DIR=%ROOT_DIR%jarvis-platform\apps\bill-core"
set "VENV_PYTHON=%ROOT_DIR%venv\Scripts\python.exe"

if not exist "%CORE_DIR%\main.py" (
  echo [JarvisCore] ERROR: Could not find core app at "%CORE_DIR%".
  pause
  endlocal & exit /b 1
)

cd /d "%CORE_DIR%"

echo [JarvisCore] Starting from "%CD%"

if exist "%VENV_PYTHON%" (
  echo [JarvisCore] Using venv python: "%VENV_PYTHON%"
  "%VENV_PYTHON%" -m uvicorn main:app --host 0.0.0.0 --port 8000
) else (
  echo [JarvisCore] venv python not found, falling back to system python
  python -m uvicorn main:app --host 0.0.0.0 --port 8000
)

set "EXITCODE=%ERRORLEVEL%"
echo.
echo [JarvisCore] Uvicorn exited with code %EXITCODE%
pause

endlocal & exit /b %EXITCODE%
