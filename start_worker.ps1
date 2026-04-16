param(
    [string]$MemoryApi = "",
    [string]$MachineId = "",
    [double]$PollIntervalSec = 2.0
)

$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
$repo = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($repo) -and $PSCommandPath) {
    $repo = Split-Path -Parent $PSCommandPath
}
if ([string]::IsNullOrWhiteSpace($repo) -and $MyInvocation.MyCommand.Path) {
    $repo = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($repo)) {
    throw "Could not resolve script folder. Open PowerShell in the worker folder and run: powershell -ExecutionPolicy Bypass -File .\\start_worker.ps1"
}

$resolvedRepo = (Resolve-Path -Path $repo).Path
if ($resolvedRepo -match '^[A-Za-z]:\\Windows\\System32$') {
    throw "start_worker.ps1 is running from System32. Run it from your extracted worker folder using: powershell -ExecutionPolicy Bypass -File .\\start_worker.ps1"
}

$repo = $resolvedRepo

$activate = Join-Path $repo "venv\Scripts\Activate.ps1"
if (!(Test-Path $activate)) {
    Write-Error "venv not found. Run setup.ps1 first."
}

. $activate

if (-not $MemoryApi) {
    if ($env:JARVIS_MEMORY_API) {
        $MemoryApi = $env:JARVIS_MEMORY_API
    } else {
        $MemoryApi = "http://127.0.0.1:8787"
    }
}

if (-not $MachineId) {
    if ($env:JARVIS_MACHINE_ID) {
        $MachineId = $env:JARVIS_MACHINE_ID
    } else {
        $user = if ($env:USERNAME) { $env:USERNAME } else { "unknown" }
        $hostName = $env:COMPUTERNAME
        if (-not $hostName) { $hostName = "unknown-host" }
        $MachineId = "$user@$hostName"
    }
}

$env:JARVIS_MEMORY_API = $MemoryApi
$env:JARVIS_MACHINE_ID = $MachineId
$env:JARVIS_WORKER_POLL_INTERVAL = [string]$PollIntervalSec

Write-Host "Starting worker: machine_id=$MachineId api=$MemoryApi" -ForegroundColor Cyan
python "$repo\worker_main.py"
