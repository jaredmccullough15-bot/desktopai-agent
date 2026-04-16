param(
    [string]$Package,
    [switch]$SkipSetup
)

$ErrorActionPreference = 'Stop'

$repo = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($repo) -and $PSCommandPath) {
    $repo = Split-Path -Parent $PSCommandPath
}
if ([string]::IsNullOrWhiteSpace($repo) -and $MyInvocation.MyCommand.Path) {
    $repo = Split-Path -Parent $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($repo)) {
    throw "Could not resolve worker folder."
}

$repo = (Resolve-Path -Path $repo).Path

if ([string]::IsNullOrWhiteSpace($Package)) {
    throw "Package is required. Example: .\update_worker.ps1 -Package .\Jarvis-Worker-Package_20260318_123000.zip OR -Package https://.../Jarvis-Worker-Package.zip"
}

$tempRoot = Join-Path $env:TEMP ("jarvis_worker_update_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
$downloadZip = Join-Path $tempRoot "package.zip"
$extractDir = Join-Path $tempRoot "payload"

New-Item -Path $tempRoot -ItemType Directory -Force | Out-Null

try {
    $resolvedPackage = $null

    if ($Package -match '^https?://') {
        Write-Host "Downloading worker package..." -ForegroundColor Cyan
        Invoke-WebRequest -Uri $Package -OutFile $downloadZip -UseBasicParsing
        $resolvedPackage = $downloadZip
    } else {
        $candidate = $Package
        if (-not [System.IO.Path]::IsPathRooted($candidate)) {
            $candidate = Join-Path $repo $candidate
        }
        if (!(Test-Path $candidate)) {
            throw "Package zip not found: $candidate"
        }
        $resolvedPackage = (Resolve-Path -Path $candidate).Path
    }

    Write-Host "Expanding package..." -ForegroundColor Cyan
    Expand-Archive -Path $resolvedPackage -DestinationPath $extractDir -Force

    $required = @(
        "setup_worker.ps1",
        "worker_ui.py",
        "worker_main.py",
        "browser_controller.py"
    )

    foreach ($file in $required) {
        if (!(Test-Path (Join-Path $extractDir $file))) {
            throw "This zip does not look like a Jarvis worker package (missing $file)."
        }
    }

    Write-Host "Updating worker files..." -ForegroundColor Cyan

    $excludeDirs = @(
        '.git',
        'venv',
        '__pycache__',
        'sessions',
        'portable',
        'node_modules',
        'data'
    )

    $excludeFiles = @(
        '.env',
        '*.zip',
        'desktop_memory.json',
        'agent_data.json'
    )

    $robocopyArgs = @(
        $extractDir,
        $repo,
        '/E',
        '/R:1',
        '/W:1',
        '/NFL',
        '/NDL',
        '/NJH',
        '/NJS',
        '/NP',
        '/XD'
    ) + $excludeDirs + @('/XF') + $excludeFiles

    & robocopy @robocopyArgs | Out-Null
    $rc = $LASTEXITCODE
    if ($rc -ge 8) {
        throw "File copy failed (robocopy exit code $rc)."
    }

    Write-Host "Worker files updated." -ForegroundColor Green

    if (-not $SkipSetup) {
        $setupScript = Join-Path $repo "setup_worker.ps1"
        if (!(Test-Path $setupScript)) {
            throw "setup_worker.ps1 missing after update."
        }

        Write-Host "Running setup_worker.ps1 to refresh dependencies and shortcut..." -ForegroundColor Yellow
        & powershell -NoProfile -ExecutionPolicy Bypass -File $setupScript
        if ($LASTEXITCODE -ne 0) {
            throw "setup_worker.ps1 reported failure (exit code $LASTEXITCODE)."
        }
    }

    Write-Host "Update complete." -ForegroundColor Green
    Write-Host "Launch Jarvis Worker icon again and click Start Ready Mode." -ForegroundColor Green
}
finally {
    if (Test-Path $tempRoot) {
        Remove-Item -Path $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
