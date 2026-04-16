param(
    [string]$Version = "1.0.4"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[bill-worker-installer] $Message" -ForegroundColor Cyan
}

function Fail-AndExit {
    param([string]$Message)
    Write-Host "[bill-worker-installer] ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Resolve-IsccPath {
    $isccCmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($isccCmd) {
        return $isccCmd.Source
    }

    $registryCandidates = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Inno Setup 6_is1"
    )

    foreach ($regPath in $registryCandidates) {
        if (Test-Path $regPath) {
            try {
                $reg = Get-ItemProperty -Path $regPath
                if ($reg.InstallLocation) {
                    $isccFromInstallLocation = Join-Path $reg.InstallLocation "ISCC.exe"
                    if (Test-Path $isccFromInstallLocation) {
                        return $isccFromInstallLocation
                    }
                }

                if ($reg.UninstallString -and ($reg.UninstallString -match '"([^"]+\\unins\d+\.exe)"')) {
                    $unins = $matches[1]
                    $isccFromUninsDir = Join-Path (Split-Path -Parent $unins) "ISCC.exe"
                    if (Test-Path $isccFromUninsDir) {
                        return $isccFromUninsDir
                    }
                }
            } catch {
            }
        }
    }

    $candidates = @(
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Install-InnoSetupIfMissing {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        return $false
    }

    Write-Step "Inno Setup not found. Attempting automatic install via winget"
    & $winget.Source install --id JRSoftware.InnoSetup -e --source winget --accept-package-agreements --accept-source-agreements --silent
    if ($LASTEXITCODE -ne 0) {
        return $false
    }

    Start-Sleep -Seconds 2
    return $true
}

$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) {
    $scriptPath = $MyInvocation.MyCommand.Path
}

if (-not [string]::IsNullOrWhiteSpace($scriptPath)) {
    $workerRoot = Split-Path -Parent $scriptPath
} elseif (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    $workerRoot = $PSScriptRoot
} else {
    $workerRoot = (Get-Location).Path
}

Set-Location $workerRoot

$isccPath = Resolve-IsccPath
if (-not $isccPath) {
    $installed = Install-InnoSetupIfMissing
    if ($installed) {
        $isccPath = Resolve-IsccPath
    }
}

if (-not $isccPath) {
    Fail-AndExit "Inno Setup not found and automatic install failed. Install Inno Setup 6 (https://jrsoftware.org/isdl.php), then rerun build-worker-installer.ps1"
}

Write-Step "Building latest complete ZIP backup and installer source files"
& (Join-Path $workerRoot "package-worker.ps1")
if ($LASTEXITCODE -ne 0) {
    Fail-AndExit "package-worker.ps1 failed (exit code: $LASTEXITCODE)"
}

$sourceDir = Join-Path $workerRoot "package-output\bill-worker"
if (-not (Test-Path $sourceDir)) {
    Fail-AndExit "Installer source directory not found: $sourceDir"
}

$installerScript = Join-Path $workerRoot "installer.iss"
if (-not (Test-Path $installerScript)) {
    Fail-AndExit "Installer script not found: $installerScript"
}

$installerOutputDir = Join-Path $workerRoot "package-output\installer"
New-Item -ItemType Directory -Path $installerOutputDir -Force | Out-Null

Write-Step "Compiling Windows installer"
& $isccPath "/DAppVersion=$Version" "/DSourceDir=$sourceDir" "/DOutDir=$installerOutputDir" $installerScript
if ($LASTEXITCODE -ne 0) {
    Fail-AndExit "Inno Setup compilation failed (exit code: $LASTEXITCODE)"
}

$installerExe = Join-Path $installerOutputDir "bill-worker-setup-$Version.exe"
if (Test-Path $installerExe) {
    Write-Host "Created installer:" -ForegroundColor Green
    Write-Host $installerExe -ForegroundColor Green
} else {
    Write-Host "Installer build completed. Check output folder:" -ForegroundColor Yellow
    Write-Host $installerOutputDir -ForegroundColor Yellow
}

Write-Host "ZIP backup remains available at package-output\\bill-worker-complete.zip" -ForegroundColor Green
