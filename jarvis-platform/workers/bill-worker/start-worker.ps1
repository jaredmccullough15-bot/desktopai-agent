param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

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

$runtimeRoot = if (-not [string]::IsNullOrWhiteSpace($env:BILL_WORKER_RUNTIME_DIR)) {
    $env:BILL_WORKER_RUNTIME_DIR
} else {
    Join-Path $env:LOCALAPPDATA "Bill Worker"
}

if ([string]::IsNullOrWhiteSpace($runtimeRoot)) {
    Write-Host "[bill-worker] ERROR: Unable to resolve runtime directory. Set BILL_WORKER_RUNTIME_DIR or ensure LOCALAPPDATA is available." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

function Write-Step {
    param([string]$Message)
    Write-Host "[bill-worker] $Message" -ForegroundColor Cyan
}

function Fail-AndExit {
    param([string]$Message)
    Write-Host "[bill-worker] ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Invoke-CheckedCommand {
    param(
        [string]$Exe,
        [string[]]$Args,
        [string]$ErrorMessage
    )

    & $Exe @Args
    if ($LASTEXITCODE -ne 0) {
        Fail-AndExit "$ErrorMessage (exit code: $LASTEXITCODE)"
    }
}

function Resolve-PythonCommand {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return @($py.Source, @("-3")) }

    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) { return @($python.Source, @()) }

    $candidatePaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        (Join-Path $env:ProgramFiles "Python312\python.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Python312\python.exe")
    )

    foreach ($candidate in $candidatePaths) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path $candidate)) {
            return @($candidate, @())
        }
    }

    return $null
}

function Install-PythonIfMissing {
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        return $false
    }

    Write-Step "Python not found. Attempting automatic install via winget"

    $installAttempts = @(
        @("install", "--id", "Python.Python.3.12", "-e", "--source", "winget", "--accept-package-agreements", "--accept-source-agreements", "--silent"),
        @("install", "--id", "Python.Python.3.11", "-e", "--source", "winget", "--accept-package-agreements", "--accept-source-agreements", "--silent")
    )

    foreach ($args in $installAttempts) {
        & $winget.Source @args
        if ($LASTEXITCODE -eq 0) {
            Start-Sleep -Seconds 2
            $pythonCmd = Resolve-PythonCommand
            if ($pythonCmd) {
                return $true
            }
        }
    }

    return $false
}

function Set-EnvIfMissing {
    param(
        [string]$Name,
        [string]$Value
    )

    $existing = [Environment]::GetEnvironmentVariable($Name, "Process")
    if ([string]::IsNullOrWhiteSpace($existing)) {
        [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
    }
}

function Set-EnvForce {
    param(
        [string]$Name,
        [string]$Value
    )

    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Test-VenvPython {
    param(
        [string]$PythonPath
    )

    if (-not (Test-Path $PythonPath)) {
        return $false
    }

    try {
        & $PythonPath -c "import sys; print(sys.version)" | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Get-ConfigValue {
    param(
        [object]$Config,
        [string]$Key,
        [object]$DefaultValue
    )

    if ($null -eq $Config) {
        return $DefaultValue
    }

    if ($Config -is [System.Collections.IDictionary]) {
        if ($Config.Contains($Key)) {
            $value = $Config[$Key]
            if ($null -ne $value) {
                return $value
            }
        }
        return $DefaultValue
    }

    $prop = $Config.PSObject.Properties[$Key]
    if ($null -eq $prop) {
        return $DefaultValue
    }

    if ($null -eq $prop.Value) {
        return $DefaultValue
    }

    return $prop.Value
}

Write-Step "Preparing Python virtual environment"
$venvDir = Join-Path $runtimeRoot ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if ((Test-Path $venvPython) -and (-not (Test-VenvPython -PythonPath $venvPython))) {
    Write-Step "Detected non-portable or broken .venv; rebuilding virtual environment"
    try {
        Remove-Item -Recurse -Force $venvDir
    } catch {
        Fail-AndExit "Failed to remove broken .venv: $($_.Exception.Message)"
    }
}

if (-not (Test-Path $venvPython)) {
    $pythonCmd = Resolve-PythonCommand
    if (-not $pythonCmd) {
        $installed = Install-PythonIfMissing
        if ($installed) {
            $pythonCmd = Resolve-PythonCommand
        }
    }

    if (-not $pythonCmd) {
        Fail-AndExit "Python not found and automatic install failed. Install Python 3.10+ (or winget), then retry."
    }

    $exe = $pythonCmd[0]
    $args = $pythonCmd[1]
    Write-Step "Creating .venv"
    & $exe @args -m venv $venvDir
}

if (-not (Test-Path $venvPython)) {
    Fail-AndExit "Virtual environment setup failed: $venvPython not found"
}

if (-not (Test-VenvPython -PythonPath $venvPython)) {
    Fail-AndExit "Virtual environment Python is not usable. Ensure Python 3.10+ is installed and rerun start-worker.ps1"
}

$activateScript = Join-Path $venvDir "Scripts\Activate.ps1"
if (Test-Path $activateScript) {
    . $activateScript
}

$bundledPlaywrightBrowsers = Join-Path $workerRoot "playwright-browsers"
$runtimePlaywrightBrowsers = Join-Path $runtimeRoot "playwright-browsers"
if (Test-Path $bundledPlaywrightBrowsers) {
    if (-not (Test-Path $runtimePlaywrightBrowsers)) {
        Write-Step "Initializing Playwright browsers cache in runtime directory"
        Copy-Item -Path $bundledPlaywrightBrowsers -Destination $runtimePlaywrightBrowsers -Recurse -Force
    }
    Write-Step "Using runtime Playwright browsers cache"
    Set-EnvForce -Name "PLAYWRIGHT_BROWSERS_PATH" -Value $runtimePlaywrightBrowsers
} elseif (Test-Path $runtimePlaywrightBrowsers) {
    Set-EnvForce -Name "PLAYWRIGHT_BROWSERS_PATH" -Value $runtimePlaywrightBrowsers
}

if (-not $SkipInstall) {
    Write-Step "Checking worker dependencies"
    $depsOk = $false
    try {
        & $venvPython -c "import requests, playwright" | Out-Null
        $depsOk = $true
    } catch {
        $depsOk = $false
    }

    if (-not $depsOk) {
        Write-Step "Installing requirements"
        Invoke-CheckedCommand -Exe $venvPython -Args @("-m", "pip", "install", "--upgrade", "pip") -ErrorMessage "Failed to upgrade pip"

        $wheelhouseDir = Join-Path $workerRoot "wheelhouse"
        if (Test-Path $wheelhouseDir) {
            Write-Step "Installing from bundled wheelhouse"
            & $venvPython -m pip install --no-index --find-links $wheelhouseDir -r (Join-Path $workerRoot "requirements.txt")
            if ($LASTEXITCODE -ne 0) {
                Write-Step "Wheelhouse install failed; falling back to online install"
                Invoke-CheckedCommand -Exe $venvPython -Args @("-m", "pip", "install", "-r", (Join-Path $workerRoot "requirements.txt")) -ErrorMessage "Failed to install requirements online"
            }
        } else {
            Invoke-CheckedCommand -Exe $venvPython -Args @("-m", "pip", "install", "-r", (Join-Path $workerRoot "requirements.txt")) -ErrorMessage "Failed to install requirements"
        }

        try {
            & $venvPython -c "import requests, playwright" | Out-Null
        } catch {
            Fail-AndExit "Dependencies still missing after installation. Ensure internet access or provide a compatible wheelhouse for this Python version."
        }
    } else {
        Write-Step "Requirements already installed"
    }

    Write-Step "Checking Playwright Chromium"
    $chromiumInstalled = $false
    try {
        $checkCode = @"
from pathlib import Path
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    exe = p.chromium.executable_path
    print(Path(exe).exists())
"@
        $result = & $venvPython -c $checkCode
        if ($result -match "True") {
            $chromiumInstalled = $true
        }
    } catch {
        $chromiumInstalled = $false
    }

    if (-not $chromiumInstalled) {
        Write-Step "Installing Playwright Chromium"
        Invoke-CheckedCommand -Exe $venvPython -Args @("-m", "playwright", "install", "chromium") -ErrorMessage "Failed to install Playwright Chromium"
    } else {
        Write-Step "Playwright Chromium already installed"
    }
}

$configPath = Join-Path $workerRoot "worker-config.json"
$config = $null
if (Test-Path $configPath) {
    try {
        $config = Get-Content $configPath -Raw | ConvertFrom-Json
    } catch {
        Fail-AndExit "Invalid worker-config.json: $($_.Exception.Message)"
    }
}

$coreUrl = [string](Get-ConfigValue -Config $config -Key "core_url" -DefaultValue "http://127.0.0.1:8010")
$machineDisplayName = [string](Get-ConfigValue -Config $config -Key "machine_display_name" -DefaultValue "")
$defaultMode = [string](Get-ConfigValue -Config $config -Key "default_execution_mode" -DefaultValue "interactive_visible")
$heartbeat = [string](Get-ConfigValue -Config $config -Key "heartbeat_interval_seconds" -DefaultValue "10")
$polling = [string](Get-ConfigValue -Config $config -Key "polling_interval_seconds" -DefaultValue "5")
$shotsDirRaw = [string](Get-ConfigValue -Config $config -Key "screenshots_dir" -DefaultValue "screenshots")
$downloadsDirRaw = [string](Get-ConfigValue -Config $config -Key "downloads_dir" -DefaultValue "downloads")
$showUi = [bool](Get-ConfigValue -Config $config -Key "show_local_ui" -DefaultValue $true)

if ([System.IO.Path]::IsPathRooted($shotsDirRaw)) {
    $shotsDir = [System.IO.Path]::GetFullPath($shotsDirRaw)
} else {
    $shotsDir = [System.IO.Path]::GetFullPath((Join-Path $runtimeRoot $shotsDirRaw))
}

if ([System.IO.Path]::IsPathRooted($downloadsDirRaw)) {
    $downloadsDir = [System.IO.Path]::GetFullPath($downloadsDirRaw)
} else {
    $downloadsDir = [System.IO.Path]::GetFullPath((Join-Path $runtimeRoot $downloadsDirRaw))
}

New-Item -ItemType Directory -Force -Path $shotsDir | Out-Null
New-Item -ItemType Directory -Force -Path $downloadsDir | Out-Null

Set-EnvIfMissing -Name "BILL_CORE_URL" -Value $coreUrl
Set-EnvIfMissing -Name "JARVIS_CORE_URL" -Value $coreUrl
Set-EnvIfMissing -Name "BILL_WORKER_DEFAULT_MODE" -Value $defaultMode
Set-EnvIfMissing -Name "JARVIS_WORKER_DEFAULT_MODE" -Value $defaultMode
Set-EnvIfMissing -Name "BILL_WORKER_HEARTBEAT_INTERVAL" -Value $heartbeat
Set-EnvIfMissing -Name "JARVIS_WORKER_HEARTBEAT_INTERVAL" -Value $heartbeat
Set-EnvIfMissing -Name "BILL_WORKER_POLLING_INTERVAL" -Value $polling
Set-EnvIfMissing -Name "JARVIS_WORKER_POLLING_INTERVAL" -Value $polling
Set-EnvIfMissing -Name "BILL_WORKER_SCREENSHOTS_DIR" -Value $shotsDir
Set-EnvIfMissing -Name "JARVIS_WORKER_SCREENSHOTS_DIR" -Value $shotsDir
Set-EnvIfMissing -Name "BILL_WORKER_DOWNLOADS_DIR" -Value $downloadsDir
Set-EnvIfMissing -Name "JARVIS_WORKER_DOWNLOADS_DIR" -Value $downloadsDir
Set-EnvIfMissing -Name "BILL_WORKER_UI" -Value ($(if ($showUi) { "1" } else { "0" }))
Set-EnvIfMissing -Name "JARVIS_WORKER_UI" -Value ($(if ($showUi) { "1" } else { "0" }))

if (-not [string]::IsNullOrWhiteSpace($machineDisplayName)) {
    Set-EnvIfMissing -Name "BILL_WORKER_MACHINE_NAME" -Value $machineDisplayName
    Set-EnvIfMissing -Name "JARVIS_WORKER_MACHINE_NAME" -Value $machineDisplayName
}

Write-Step "Running connectivity check: $coreUrl/health"
try {
    $health = Invoke-RestMethod -Uri "$coreUrl/health" -Method Get -TimeoutSec 8
    if ($health.status -ne "ok") {
        throw "Unexpected health response"
    }
    Write-Step "Core health check passed"
} catch {
    Write-Host "Cannot reach Jarvis Core at $coreUrl" -ForegroundColor Red
    Write-Host "Likely causes:" -ForegroundColor Yellow
    Write-Host "- Core is not running" -ForegroundColor Yellow
    Write-Host "- Wrong IP address" -ForegroundColor Yellow
    Write-Host "- Firewall is blocking the configured API port" -ForegroundColor Yellow
    Write-Host "- Core is bound to localhost instead of 0.0.0.0" -ForegroundColor Yellow
    Write-Host "" 
    Write-Host "Start core with:" -ForegroundColor Yellow
    Write-Host "python -m uvicorn main:app --reload --host 0.0.0.0 --port 8010" -ForegroundColor Yellow
    exit 1
}

$machineNameFinal = if ([string]::IsNullOrWhiteSpace($env:BILL_WORKER_MACHINE_NAME)) { $env:COMPUTERNAME } else { $env:BILL_WORKER_MACHINE_NAME }
Write-Step "Machine name: $machineNameFinal"
Write-Step "Core URL: $env:BILL_CORE_URL"
Write-Step "Runtime root: $runtimeRoot"
Write-Step "Execution mode: $env:BILL_WORKER_DEFAULT_MODE"
Write-Step "Screenshots path: $env:BILL_WORKER_SCREENSHOTS_DIR"
Write-Step "Downloads path: $env:BILL_WORKER_DOWNLOADS_DIR"
Write-Step "Heartbeat interval: $env:BILL_WORKER_HEARTBEAT_INTERVAL s"
Write-Step "Polling interval: $env:BILL_WORKER_POLLING_INTERVAL s"

Write-Step "Starting worker"
& $venvPython (Join-Path $workerRoot "main.py")
if ($LASTEXITCODE -ne 0) {
    Fail-AndExit "Worker process exited unexpectedly (exit code: $LASTEXITCODE)"
}
