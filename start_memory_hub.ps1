$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
$activate = Join-Path $repo "venv\Scripts\Activate.ps1"
if (!(Test-Path $activate)) {
    Write-Error "venv not found. Run setup.ps1 first."
}

. $activate

$hostName = if ($env:JARVIS_HUB_HOST) { $env:JARVIS_HUB_HOST } else { "0.0.0.0" }
$port = if ($env:JARVIS_HUB_PORT) { $env:JARVIS_HUB_PORT } else { "8787" }

Write-Host "Starting Jarvis Shared Memory Hub on $hostName`:$port" -ForegroundColor Cyan
python -m uvicorn memory_api:app --host $hostName --port $port
