$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($repo) -and $PSCommandPath) {
    $repo = Split-Path -Parent $PSCommandPath
}
if ([string]::IsNullOrWhiteSpace($repo) -and $MyInvocation.MyCommand.Path) {
    $repo = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($repo)) {
    throw "Could not resolve script folder. Open PowerShell in the worker folder and run: powershell -ExecutionPolicy Bypass -File .\\setup_worker.ps1"
}

$resolvedRepo = (Resolve-Path -Path $repo).Path
if ($resolvedRepo -match '^[A-Za-z]:\\Windows\\System32$') {
    throw "setup_worker.ps1 is running from System32. Run it from your extracted worker folder using: powershell -ExecutionPolicy Bypass -File .\\setup_worker.ps1"
}

$repo = $resolvedRepo
Push-Location $repo

Write-Host "Setting up this computer as a Jarvis worker..." -ForegroundColor Cyan

$setupScript = Join-Path $repo "setup.ps1"
if (!(Test-Path $setupScript)) {
    throw "setup.ps1 not found at $setupScript"
}

& powershell -ExecutionPolicy Bypass -File $setupScript
if ($LASTEXITCODE -ne 0) {
    throw "Base setup failed."
}

$activate = Join-Path $repo "venv\Scripts\Activate.ps1"
if (!(Test-Path $activate)) {
    throw "venv activation script not found."
}
. $activate

Write-Host "Installing Playwright browser binaries (chromium)..." -ForegroundColor Yellow
python -m playwright install chromium

$templatePath = Join-Path $repo "worker.env.template"
if ([string]::IsNullOrWhiteSpace($templatePath)) {
    throw "Could not resolve worker.env.template path. Current repo path: '$repo'"
}
if (!(Test-Path $templatePath)) {
    @"
JARVIS_MEMORY_API=http://127.0.0.1:8787
JARVIS_MACHINE_ID=USER@PCNAME
JARVIS_WORKER_POLL_INTERVAL=2.0
"@ | Set-Content -Path $templatePath -Encoding UTF8
    Write-Host "Created worker.env.template" -ForegroundColor Green
}

$shortcutScript = Join-Path $repo "create_worker_desktop_shortcut.ps1"
if (Test-Path $shortcutScript) {
    try {
        & powershell -NoProfile -ExecutionPolicy Bypass -File $shortcutScript
    } catch {
        Write-Warning "Could not create Worker desktop shortcut automatically: $($_.Exception.Message)"
    }
}

Write-Host "Worker setup complete." -ForegroundColor Green
Write-Host "Use desktop icon 'Jarvis Worker' (or run run_worker_ui.cmd) to put worker in ready mode." -ForegroundColor Green

Pop-Location
