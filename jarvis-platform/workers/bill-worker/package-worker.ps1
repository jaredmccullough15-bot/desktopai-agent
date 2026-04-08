param(
    [switch]$Lite
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[bill-worker-package] $Message" -ForegroundColor Cyan
}

function Resolve-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, @("-3")) }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @($python.Source, @()) }

    return $null
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

$outputRoot = Join-Path $root "package-output"
$staging = Join-Path $outputRoot "bill-worker"
$zipName = if ($Lite) { "bill-worker-lite.zip" } else { "bill-worker-complete.zip" }
$zipPath = Join-Path $outputRoot $zipName
$legacyZipPath = Join-Path $outputRoot "bill-worker.zip"

if (Test-Path $staging) { Remove-Item -Recurse -Force $staging }
if (Test-Path $zipPath) { Remove-Item -Force $zipPath }
if (Test-Path $legacyZipPath) { Remove-Item -Force $legacyZipPath }

New-Item -ItemType Directory -Path $staging -Force | Out-Null

$excludeDirs = @(
    ".venv",
    "__pycache__",
    "downloads",
    "screenshots",
    "package-output",
    "build",
    "dist"
)

$excludeFiles = @(
    "secrets.local.json",
    ".worker_state.json"
)

Write-Step "Copying worker files into staging"
Get-ChildItem -Path $root -Force | ForEach-Object {
    if ($excludeDirs -contains $_.Name) { return }
    if ($excludeFiles -contains $_.Name) { return }

    $dest = Join-Path $staging $_.Name
    if ($_.PSIsContainer) {
        Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
    } else {
        Copy-Item -Path $_.FullName -Destination $dest -Force
    }
}

# Flatten dist/BillWorker/ into staging root so BillWorker.exe is at the top level.
# The auto-updater requires BillWorker.exe to exist at the root of the extracted package.
$distBillWorker = Join-Path $root "dist\BillWorker"
if (Test-Path $distBillWorker) {
    Write-Step "Flattening dist/BillWorker/ into staging root (required for auto-updater)"
    Get-ChildItem -Path $distBillWorker -Force | ForEach-Object {
        $dest = Join-Path $staging $_.Name
        if ($_.PSIsContainer) {
            Copy-Item -Path $_.FullName -Destination $dest -Recurse -Force
        } else {
            Copy-Item -Path $_.FullName -Destination $dest -Force
        }
    }
} else {
    Write-Host "[bill-worker-package] WARNING: dist/BillWorker/ not found. Auto-updater will not work." -ForegroundColor Yellow
    Write-Host "[bill-worker-package] Run build-portable-worker.ps1 first to generate BillWorker.exe." -ForegroundColor Yellow
}

if (-not $Lite) {
    $bundledBrowsersDest = Join-Path $staging "playwright-browsers"
    $playwrightSource = $null

    if (-not [string]::IsNullOrWhiteSpace($env:PLAYWRIGHT_BROWSERS_PATH) -and (Test-Path $env:PLAYWRIGHT_BROWSERS_PATH)) {
        $playwrightSource = $env:PLAYWRIGHT_BROWSERS_PATH
    } else {
        $defaultPwPath = Join-Path $env:LOCALAPPDATA "ms-playwright"
        if (Test-Path $defaultPwPath) {
            $playwrightSource = $defaultPwPath
        }
    }

    if ($playwrightSource) {
        Write-Step "Bundling Playwright browsers from: $playwrightSource"
        Copy-Item -Path $playwrightSource -Destination $bundledBrowsersDest -Recurse -Force
    } else {
        Write-Step "Playwright browser cache not found; startup may install Chromium on first run"
    }

    $wheelhouse = Join-Path $staging "wheelhouse"
    New-Item -ItemType Directory -Path $wheelhouse -Force | Out-Null

    $venvPython = Join-Path $root ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        Write-Step "Downloading offline wheels using local .venv"
        try {
            & $venvPython -m pip download -r (Join-Path $root "requirements.txt") -d $wheelhouse
        } catch {
            Write-Step "Wheelhouse download failed; startup will fallback to online pip install"
        }
    } else {
        $pythonCmd = Resolve-PythonCommand
        if ($pythonCmd) {
            Write-Step "Downloading offline wheels using system Python"
            $exe = $pythonCmd[0]
            $args = $pythonCmd[1]
            try {
                & $exe @args -m pip download -r (Join-Path $root "requirements.txt") -d $wheelhouse
            } catch {
                Write-Step "Wheelhouse download failed; startup will fallback to online pip install"
            }
        } else {
            Write-Step "Python not found while packaging wheelhouse; startup will fallback to online pip install"
        }
    }

    $wheelCount = (Get-ChildItem -Path $wheelhouse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    if ($wheelCount -eq 0) {
        Remove-Item -Recurse -Force $wheelhouse
        Write-Step "No wheels downloaded; wheelhouse removed from package"
    }
}

Write-Step "Creating single-file deployment archive: $zipName"
Compress-Archive -Path (Join-Path $staging "*") -DestinationPath $zipPath -Force

Write-Host "Created deployment package:" -ForegroundColor Green
Write-Host $zipPath -ForegroundColor Green
if ($Lite) {
    Write-Host "Package type: LITE (small size, first-run may install dependencies online)" -ForegroundColor Yellow
} else {
    Write-Host "Package type: COMPLETE (bundles runtime assets; excludes .venv because Windows venv is machine-specific)" -ForegroundColor Green
}
