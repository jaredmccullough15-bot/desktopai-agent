param(
    [Parameter(Mandatory=$false)]
    [string]$DriveLetter,
    [switch]$Minimal
)

$ErrorActionPreference = 'Stop'

Write-Host "Preparing USB deployment..." -ForegroundColor Cyan

# Resolve repo root
$repo = $PSScriptRoot
$projectRoot = Split-Path -Parent $repo

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

# Determine target drive
function Get-UsbRoot {
    param([string]$dl)
    if ($dl) {
        $dl = $dl.TrimEnd(':')
        $path = ('{0}:\' -f $dl)
        if (!(Test-Path $path)) { throw ('Drive {0}:\ not found' -f $dl) }
        return $path
    }
    $rem = Get-Volume | Where-Object { $_.DriveType -eq 'Removable' -and $_.DriveLetter }
    if ($rem.Count -eq 1) {
        return ("{0}:\" -f $rem.DriveLetter)
    } elseif ($rem.Count -gt 1) {
        $letters = ($rem | Select-Object -ExpandProperty DriveLetter) -join ', '
        throw "Multiple removable drives detected: $letters. Specify -DriveLetter."
    } else {
        throw "No removable USB drive detected. Specify -DriveLetter."
    }
}

$usbRoot = Get-UsbRoot -dl $DriveLetter
Write-Host "Deploying to $usbRoot" -ForegroundColor Green

# Copy autorun assets to USB root
Copy-Item -Force (Join-Path $repo "autorun.inf") (Join-Path $usbRoot "autorun.inf")
Copy-Item -Force $setupExe (Join-Path $usbRoot "setup.exe")
if (Test-Path (Join-Path $repo "portable\run-sync-root.cmd")) {
    Copy-Item -Force (Join-Path $repo "portable\run-sync-root.cmd") (Join-Path $usbRoot "Run Smart Sherpa Sync.cmd")
}

$destProj = Join-Path $usbRoot "desktop-ai-agent"

if ($Minimal) {
    Write-Host "Minimal update mode: copying only patched files..." -ForegroundColor Yellow
    if (!(Test-Path $destProj)) { New-Item -ItemType Directory -Path $destProj | Out-Null }
    # Ensure portable dir exists
    $destPortable = Join-Path $destProj "portable"
    if (!(Test-Path $destPortable)) { New-Item -ItemType Directory -Path $destPortable | Out-Null }

    # Copy patched files
    Copy-Item -Force (Join-Path $projectRoot "setup.ps1") (Join-Path $destProj "setup.ps1")
    Copy-Item -Force (Join-Path $projectRoot "requirements.txt") (Join-Path $destProj "requirements.txt")
    Copy-Item -Force (Join-Path $projectRoot "start-chrome-debug.ps1") (Join-Path $destProj "start-chrome-debug.ps1")
    Copy-Item -Force (Join-Path $projectRoot "portable\run-sync.ps1") (Join-Path $destPortable "run-sync.ps1")
    if (Test-Path (Join-Path $projectRoot "portable\run-sync.cmd")) {
        Copy-Item -Force (Join-Path $projectRoot "portable\run-sync.cmd") (Join-Path $destPortable "run-sync.cmd")
    }
    # Lean runner and required modules
    Copy-Item -Force (Join-Path $projectRoot "portable\run_smart_sherpa_sync.py") (Join-Path $destPortable "run_smart_sherpa_sync.py")
    if (!(Test-Path (Join-Path $destProj "modules"))) { New-Item -ItemType Directory -Path (Join-Path $destProj "modules") | Out-Null }
    Copy-Item -Force (Join-Path $projectRoot "modules\__init__.py") (Join-Path $destProj "modules\__init__.py")
    Copy-Item -Force (Join-Path $projectRoot "modules\actions.py") (Join-Path $destProj "modules\actions.py")
    if (Test-Path (Join-Path $projectRoot "modules\memory.py")) {
        Copy-Item -Force (Join-Path $projectRoot "modules\memory.py") (Join-Path $destProj "modules\memory.py")
    }
    # Ensure data folder for logs
    if (!(Test-Path (Join-Path $destProj "data"))) { New-Item -ItemType Directory -Path (Join-Path $destProj "data") | Out-Null }

    Write-Host "Minimal update complete." -ForegroundColor Green
} else {
    # Sync project folder (exclude heavy/volatile dirs)
    $excludeDirs = @("venv","dist","build",".git","__pycache__")
    $excludeFiles = @("*.pyc","*.log")

    # Execute robocopy directly with arguments (PowerShell safely passes tokens)
    Write-Host "Running robocopy to mirror project..." -ForegroundColor DarkGray
    & robocopy $projectRoot $destProj /MIR /R:1 /W:1 /MT:16 /NP /XD $excludeDirs /XF $excludeFiles | Out-Null
    Write-Host "USB deployment complete." -ForegroundColor Cyan
}
