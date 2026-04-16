$ErrorActionPreference = 'Stop'

Write-Host "Packaging USB layout zip..." -ForegroundColor Cyan

# Paths
$repo = $PSScriptRoot
$projectRoot = Split-Path -Parent $repo
$staging = Join-Path $repo "usb-staging"
$zipPath = Join-Path $projectRoot "Desktop-AI-Agent-USB.zip"

# Clean staging
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path $staging | Out-Null

# Ensure setup.exe exists; build if missing
$setupExe = Join-Path $repo "setup.exe"
if (!(Test-Path $setupExe)) {
    Write-Host "Building setup.exe via PyInstaller..." -ForegroundColor Yellow
    Push-Location $projectRoot
    $venvActivate = Join-Path $projectRoot "venv\Scripts\Activate.ps1"
    if (Test-Path $venvActivate) { . $venvActivate }
    python -m pip install --quiet pyinstaller
    python -m PyInstaller --onefile portable/usb_setup_launcher.py -n setup
    Copy-Item -Force (Join-Path $projectRoot "dist\setup.exe") $setupExe
    Pop-Location
}

# Copy autorun assets to staging root
Copy-Item -Force (Join-Path $repo "autorun.inf") (Join-Path $staging "autorun.inf")
Copy-Item -Force $setupExe (Join-Path $staging "setup.exe")
if (Test-Path (Join-Path $repo "portable\run-sync-root.cmd")) {
    Copy-Item -Force (Join-Path $repo "portable\run-sync-root.cmd") (Join-Path $staging "Run Smart Sherpa Sync.cmd")
}

# Copy project folder into staging (exclude heavy/volatile)
$destProj = Join-Path $staging "desktop-ai-agent"
New-Item -ItemType Directory -Path $destProj | Out-Null

$excludeDirs = @("venv","dist","build",".git","__pycache__")
$excludeFiles = @("*.pyc","*.log")

robocopy "$projectRoot" "$destProj" /MIR /R:1 /W:1 /XD $excludeDirs /XF $excludeFiles | Out-Null

# Create zip
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zipPath

# Cleanup
Remove-Item -Recurse -Force $staging

Write-Host "Created: $zipPath" -ForegroundColor Green
