@echo off
setlocal
cd /d "%~dp0"

if not defined LOCALAPPDATA set "LOCALAPPDATA=%TEMP%"
set "RUNTIME_DIR=%LOCALAPPDATA%\Bill Worker"
if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%" >nul 2>&1
if not exist "%RUNTIME_DIR%" (
	set "RUNTIME_DIR=%TEMP%\Bill Worker"
	if not exist "%RUNTIME_DIR%" mkdir "%RUNTIME_DIR%" >nul 2>&1
)

set "BILL_WORKER_RUNTIME_DIR=%RUNTIME_DIR%"
set "LAUNCH_LOG=%RUNTIME_DIR%\worker-launch.log"

echo [bill-worker] Starting worker...
echo [bill-worker] Runtime dir: "%RUNTIME_DIR%"
echo [bill-worker] Launch log: "%LAUNCH_LOG%"

echo.>> "%LAUNCH_LOG%"
echo ===== %DATE% %TIME% =====>> "%LAUNCH_LOG%"
echo [bill-worker] Starting worker...>> "%LAUNCH_LOG%"
echo [bill-worker] Runtime dir: "%RUNTIME_DIR%">> "%LAUNCH_LOG%"

powershell -NoProfile -ExecutionPolicy Bypass -File ".\start-worker.ps1" >> "%LAUNCH_LOG%" 2>&1
set "EXITCODE=%ERRORLEVEL%"

if not "%EXITCODE%"=="0" (
	echo.
	echo [bill-worker] Worker exited with code %EXITCODE%.
	echo [bill-worker] See "%LAUNCH_LOG%" for details.
	echo [bill-worker] Showing last 40 log lines:
	powershell -NoProfile -Command "if (Test-Path $env:LAUNCH_LOG) { Get-Content $env:LAUNCH_LOG -Tail 40 }"
	pause
)

endlocal & exit /b %EXITCODE%
