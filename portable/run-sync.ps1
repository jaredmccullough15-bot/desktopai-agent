$ErrorActionPreference = 'Stop'
Write-Host "Starting Smart Sherpa Sync (Lean Runner)..." -ForegroundColor Cyan

# Use script directory
$repo = $PSScriptRoot
$root = Split-Path -Parent $repo

# Ensure venv
$envPath = Join-Path $root "venv\Scripts\Activate.ps1"
if (!(Test-Path $envPath)) {
  Write-Host "Setting up Python environment..." -ForegroundColor Yellow
  & (Join-Path $root "setup.ps1")
}
. $envPath

# Default Chrome DevTools port
if (-not $env:CHROME_DEBUG_PORT) { $env:CHROME_DEBUG_PORT = "9222" }
Write-Host "Chrome DevTools port: $env:CHROME_DEBUG_PORT" -ForegroundColor Yellow

# Quick check: is Chrome running with DevTools enabled?
try {
  $version = Invoke-WebRequest -Uri "http://127.0.0.1:$($env:CHROME_DEBUG_PORT)/json/version" -UseBasicParsing -TimeoutSec 2 -ErrorAction Stop | Select-Object -ExpandProperty Content
  if ($version) { Write-Host "Detected Chrome DevTools endpoint." -ForegroundColor Green }
} catch {
  Write-Host "Chrome debug endpoint not detected." -ForegroundColor Yellow
  $startChrome = Join-Path $root "start-chrome-debug.ps1"
  if (Test-Path $startChrome) {
    Write-Host "Tip: Start Chrome in debug mode now." -ForegroundColor DarkGray
    Write-Host "Running start-chrome-debug.ps1..." -ForegroundColor Yellow
    powershell -NoProfile -ExecutionPolicy Bypass -File $startChrome
    Write-Host "Please log into HealthSherpa in that window, then return here." -ForegroundColor Yellow
  } else {
    Write-Host "Start Chrome with: chrome.exe --remote-debugging-port=9222" -ForegroundColor Yellow
  }
}

# Optional: set CLIENTS_URL, SYNC_TEXT via environment before running
Push-Location $root
python "$repo\run_smart_sherpa_sync.py"
Pop-Location

Write-Host "Done. If you saw an attach error, make sure Chrome is in debug mode and on the clients page." -ForegroundColor DarkGray
Read-Host -Prompt "Press Enter to close"