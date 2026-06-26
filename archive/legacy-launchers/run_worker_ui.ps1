$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($repo) -and $PSCommandPath) {
    $repo = Split-Path -Parent $PSCommandPath
}
if ([string]::IsNullOrWhiteSpace($repo) -and $MyInvocation.MyCommand.Path) {
    $repo = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($repo)) {
    throw "Could not resolve script folder."
}

$repo = (Resolve-Path -Path $repo).Path
Push-Location $repo

try {
    $activate = Join-Path $repo "venv\Scripts\Activate.ps1"
    if (!(Test-Path $activate)) {
        throw "venv not found. Run setup_worker.ps1 first."
    }

    . $activate

    $workerUi = Join-Path $repo "worker_ui.py"
    if (!(Test-Path $workerUi)) {
        throw "worker_ui.py not found at $workerUi"
    }

    python "$workerUi"
    if ($LASTEXITCODE -ne 0) {
        throw "worker_ui.py exited with code $LASTEXITCODE"
    }
}
catch {
    Write-Host "Failed to launch Jarvis Worker UI:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host ""
    Write-Host "Press Enter to keep troubleshooting in this window." -ForegroundColor Yellow
    Read-Host | Out-Null
    return
}
finally {
    Pop-Location
}
