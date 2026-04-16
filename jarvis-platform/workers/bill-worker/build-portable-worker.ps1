param(
    [string]$OutputPath = "C:\JarvisWorker"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[portable-build] $Message" -ForegroundColor Cyan
}

$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) {
    $scriptPath = $MyInvocation.MyCommand.Path
}

if (-not [string]::IsNullOrWhiteSpace($scriptPath)) {
    $root = Split-Path -Parent $scriptPath
} elseif (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    $root = $PSScriptRoot
} else {
    $root = (Get-Location).Path
}

$entryPoint = Join-Path $root "main.py"
if (-not (Test-Path $entryPoint)) {
    throw "Unable to find worker entry point: $entryPoint"
}

$entryText = Get-Content -Path $entryPoint -Raw -Encoding UTF8
$versionMatch = [regex]::Match($entryText, 'WORKER_VERSION\s*=\s*"([^"]+)"')
$workerVersion = if ($versionMatch.Success) { $versionMatch.Groups[1].Value } else { "unknown" }

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $pythonExe = $venvPython
} else {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        throw "Python is required on build machine. Install Python or create .venv first."
    }
    $pythonExe = $pythonCmd.Source
}

Write-Step "Using Python: $pythonExe"

Write-Step "Ensuring PyInstaller is installed"
& $pythonExe -m pip install --upgrade pyinstaller
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install/update PyInstaller"
}

$buildDir = Join-Path $root "build"
$distDir = Join-Path $root "dist"
if (Test-Path $buildDir) { Remove-Item -Recurse -Force $buildDir }
if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }

Write-Step "Building self-contained BillWorker.exe (one-folder)"
& $pythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --console `
    --name BillWorker `
    --collect-all playwright `
    --hidden-import selenium `
    --hidden-import tkinter `
    --paths $root `
    $entryPoint

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed"
}

$builtFolder = Join-Path $distDir "BillWorker"
if (-not (Test-Path $builtFolder)) {
    throw "Build output not found: $builtFolder"
}

Write-Step "Preparing output folder: $OutputPath"
if (Test-Path $OutputPath) {
    Remove-Item -Recurse -Force $OutputPath
}
New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null

Write-Step "Copying self-contained runtime files"
Copy-Item -Path (Join-Path $builtFolder "*") -Destination $OutputPath -Recurse -Force

foreach ($dirName in @("logs", "screenshots", "downloads")) {
    New-Item -ItemType Directory -Path (Join-Path $OutputPath $dirName) -Force | Out-Null
}

$configPath = Join-Path $OutputPath "config.json"
$configJson = @'
{
    "core_url": "http://10.0.0.44:8000",
  "worker_name": "BillWorker-PC",
  "visible_mode": true,
  "poll_interval_seconds": 5,
  "log_level": "INFO"
}
'@
Set-Content -Path $configPath -Value $configJson -Encoding UTF8

$versionPath = Join-Path $OutputPath "version.json"
$builtAtUtc = (Get-Date).ToUniversalTime().ToString("o")
$versionJson = @"
{
    "worker_version": "$workerVersion",
    "built_at_utc": "$builtAtUtc"
}
"@
Set-Content -Path $versionPath -Value $versionJson -Encoding UTF8

$startBatPath = Join-Path $OutputPath "start_worker.bat"
$startBat = @'
@echo off
setlocal
cd /d "%~dp0"

set "MAX_RESTARTS=10"
set "RESTART_COUNT=0"

:run_worker
echo [JarvisWorker] Working directory: "%CD%"
echo [JarvisWorker] Launching BillWorker.exe...

BillWorker.exe
set "EXITCODE=%ERRORLEVEL%"

if "%EXITCODE%"=="0" (
    tasklist /FI "IMAGENAME eq BillWorker.exe" | find /I "BillWorker.exe" >nul
    if errorlevel 1 (
        if %RESTART_COUNT% LSS %MAX_RESTARTS% (
            set /a RESTART_COUNT+=1
            echo [JarvisWorker] Worker exited cleanly. Relaunching in 5 seconds (attempt %RESTART_COUNT%/%MAX_RESTARTS%)...
            timeout /t 5 /nobreak >nul
            goto run_worker
        )
    )
)

echo.
echo [JarvisWorker] BillWorker.exe exited with code %EXITCODE%
echo [JarvisWorker] Review logs in "%CD%\logs"
pause

endlocal & exit /b %EXITCODE%
'@
Set-Content -Path $startBatPath -Value $startBat -Encoding ASCII

$taskBatPath = Join-Path $OutputPath "install_startup_task.bat"
$taskBat = @'
@echo off
setlocal
cd /d "%~dp0"

set "TASK_NAME=Jarvis Bill Worker"
set "TASK_CMD=\"%~dp0start_worker.bat\""

echo [JarvisWorker] Installing startup scheduled task "%TASK_NAME%"...

schtasks /Delete /TN "%TASK_NAME%" /F >nul 2>&1
schtasks /Create /TN "%TASK_NAME%" /TR %TASK_CMD% /SC ONLOGON /RL LIMITED /IT /F

if errorlevel 1 (
  echo [JarvisWorker] ERROR: Failed to create startup task.
  echo [JarvisWorker] Try running this script as the user who should run desktop automation.
  pause
  endlocal & exit /b 1
)

echo [JarvisWorker] Startup task installed successfully.
echo [JarvisWorker] It will run only when this user is logged on (interactive desktop).
pause

endlocal & exit /b 0
'@
Set-Content -Path $taskBatPath -Value $taskBat -Encoding ASCII

$triggerUpdatePath = Join-Path $OutputPath "trigger_update_now.bat"
$triggerUpdateBat = @'
@echo off
setlocal
cd /d "%~dp0"

echo [JarvisWorker] Triggering manual update check...
BillWorker.exe --trigger-update-now
set "EXITCODE=%ERRORLEVEL%"

echo [JarvisWorker] Manual update trigger finished with exit code %EXITCODE%
echo [JarvisWorker] Check logs in "%CD%\logs" and updates\last_update.log for details.
pause

endlocal & exit /b %EXITCODE%
'@
Set-Content -Path $triggerUpdatePath -Value $triggerUpdateBat -Encoding ASCII

Write-Step "Portable output is ready"
Write-Host "Created: $OutputPath" -ForegroundColor Green
Write-Host "Contents:" -ForegroundColor Green
Get-ChildItem -Path $OutputPath | Select-Object Name | Format-Table -AutoSize
