$ErrorActionPreference = 'Stop'
Write-Host "Packaging Smart Sherpa Sync (sync-only) zip..." -ForegroundColor Cyan

# Paths
$repo = $PSScriptRoot
$root = Split-Path -Parent $repo
$staging = Join-Path $repo "sync-staging"
$zipPath = Join-Path $root "SmartSherpaSync-USB.zip"

# Clean staging
if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
New-Item -ItemType Directory -Path $staging | Out-Null

# Ensure setup.exe exists; build if missing
$setupExe = Join-Path $repo "setup.exe"
if (!(Test-Path $setupExe)) {
  Write-Host "Building setup.exe via PyInstaller..." -ForegroundColor Yellow
  Push-Location $root
  $venvActivate = Join-Path $root "venv\Scripts\Activate.ps1"
  if (Test-Path $venvActivate) { . $venvActivate }
  python -m pip install --quiet pyinstaller
  python -m PyInstaller --onefile portable/usb_setup_launcher.py -n setup
  Copy-Item -Force (Join-Path $root "dist\setup.exe") $setupExe
  Pop-Location
}

# Root files for AutoPlay
Copy-Item -Force (Join-Path $repo "autorun.inf") (Join-Path $staging "autorun.inf")
Copy-Item -Force $setupExe (Join-Path $staging "setup.exe")
if (Test-Path (Join-Path $repo "portable\run-sync-root.cmd")) {
  Copy-Item -Force (Join-Path $repo "portable\run-sync-root.cmd") (Join-Path $staging "Run Smart Sherpa Sync.cmd")
}

# Minimal project subset
$destProj = Join-Path $staging "desktop-ai-agent"
New-Item -ItemType Directory -Path $destProj | Out-Null

$files = @(
  "setup.ps1",
  "requirements.txt",
  "start-chrome-debug.ps1",
  "portable\run-sync.cmd",
  "portable\run-sync.ps1",
  "portable\run_smart_sherpa_sync.py",
  "modules\actions.py",
  "modules\memory.py",
  "modules\__init__.py"
)

foreach ($f in $files) {
  $src = Join-Path $root $f
  $dest = Join-Path $destProj $f
  $destDir = Split-Path -Parent $dest
  if (!(Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir | Out-Null }
  Copy-Item -Force $src $dest
}

# Ensure data folder exists
New-Item -ItemType Directory -Path (Join-Path $destProj "data") | Out-Null

# Create zip
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zipPath

# Cleanup
Remove-Item -Recurse -Force $staging

Write-Host "Created: $zipPath" -ForegroundColor Green
