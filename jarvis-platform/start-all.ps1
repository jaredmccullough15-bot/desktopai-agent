param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$corePath = Join-Path $root "apps\bill-core"
$workerPath = Join-Path $root "workers\bill-worker"
$webPath = Join-Path $root "apps\bill-web"
$webPort = 3000

$corePythonExe = Join-Path $corePath ".venv\Scripts\python.exe"
$workerPythonExe = Join-Path $workerPath ".venv\Scripts\python.exe"

function Write-Step {
    param([string]$Message)
    Write-Host "[start-all] $Message" -ForegroundColor Cyan
}

function Stop-WithError {
    param([string]$Message)
    Write-Host "[start-all] ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Assert-PathExists {
    param(
        [string]$Path,
        [string]$Label
    )

    if (-not (Test-Path -Path $Path)) {
        Stop-WithError "$Label not found: $Path"
    }
}

function Ensure-VenvPython {
    param(
        [string]$ServicePath,
        [string]$PythonExe
    )

    if (-not (Test-Path $PythonExe)) {
        Write-Step "Creating virtual environment in $ServicePath"
        Set-Location -Path "$ServicePath"

        $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
        if ($pyLauncher) {
            & $pyLauncher.Source -3 -m venv .venv
        } else {
            $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
            if (-not $pythonCmd) {
                Write-Error "Python interpreter not found. Install Python and retry."
                exit 1
            }
            & $pythonCmd.Source -m venv .venv
        }
    }

    if (-not (Test-Path $PythonExe)) {
        Stop-WithError "Venv python path does not exist: $PythonExe"
    }
}

function Install-PythonDependencies {
    param(
        [string]$ServicePath,
        [string]$PythonExe
    )

    if ($SkipInstall) {
        Write-Step "Skipping Python dependency install for $ServicePath"
        return
    }

    $requirementsFile = Join-Path $ServicePath "requirements.txt"
    if (-not (Test-Path $requirementsFile)) {
        Write-Step "No requirements.txt found in $ServicePath"
        return
    }

    Write-Step "Installing Python dependencies in $ServicePath"
    Set-Location -Path "$ServicePath"
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r $requirementsFile
}

function Resolve-NpmCmd {
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
    if ($npmCommand) {
        return $npmCommand.Source
    }

    $candidatePaths = @(
        "$Env:ProgramFiles\nodejs\npm.cmd",
        "$Env:ProgramFiles(x86)\nodejs\npm.cmd",
        "$Env:LocalAppData\Programs\nodejs\npm.cmd"
    )

    foreach ($candidate in $candidatePaths) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Resolve-NodeExe {
    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCommand) {
        return $nodeCommand.Source
    }

    $candidatePaths = @(
        "$Env:ProgramFiles\nodejs\node.exe",
        "$Env:ProgramFiles(x86)\nodejs\node.exe",
        "$Env:LocalAppData\Programs\nodejs\node.exe"
    )

    foreach ($candidate in $candidatePaths) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Stop-PortListeners {
    param([int[]]$Ports)

    foreach ($port in $Ports) {
        try {
            $connections = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
            if (-not $connections) {
                continue
            }

            $processIds = $connections | Select-Object -ExpandProperty OwningProcess -Unique
            foreach ($processId in $processIds) {
                if ($processId -and $processId -ne $PID -and $processId -ne 4) {
                    try {
                        Stop-Process -Id $processId -Force -ErrorAction Stop
                        Write-Step "Stopped process $processId listening on port $port"
                    }
                    catch {
                        Write-Step "Unable to stop process $processId on port ${port}: $($_.Exception.Message)"
                    }
                }
            }
        }
        catch {
            Write-Step "Port cleanup skipped for ${port}: $($_.Exception.Message)"
        }
    }
}

function Start-ServiceWindow {
    param(
        [string]$Title,
        [string]$ScriptText
    )

    Write-Step "Launching $Title"
    $prefixedScript = "$Host.UI.RawUI.WindowTitle = '$Title'; $ScriptText"
    $encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($prefixedScript))
    Start-Process powershell -ArgumentList @("-NoExit", "-EncodedCommand", $encoded)
}

Write-Step "Validating project paths"
Assert-PathExists -Path $root -Label "Project root"
Assert-PathExists -Path $corePath -Label "Core working directory"
Assert-PathExists -Path $workerPath -Label "Worker working directory"
Assert-PathExists -Path $webPath -Label "Web working directory"

Write-Step "Preparing bill-core"
Ensure-VenvPython -ServicePath $corePath -PythonExe $corePythonExe
Install-PythonDependencies -ServicePath $corePath -PythonExe $corePythonExe

Write-Step "Preparing bill-worker"
Ensure-VenvPython -ServicePath $workerPath -PythonExe $workerPythonExe
Install-PythonDependencies -ServicePath $workerPath -PythonExe $workerPythonExe

if (-not (Test-Path $corePythonExe)) {
    Stop-WithError "Core Python executable not found: $corePythonExe"
}

if (-not (Test-Path $workerPythonExe)) {
    Stop-WithError "Worker Python executable not found: $workerPythonExe"
}

$npmCmd = Resolve-NpmCmd
if (-not $npmCmd) {
    Stop-WithError "npm.cmd not found. Install Node.js and ensure npm is available."
}

$nodeExe = Resolve-NodeExe
if (-not $nodeExe) {
    Stop-WithError "node.exe not found. Install Node.js and ensure node is available."
}

Assert-PathExists -Path $npmCmd -Label "npm executable"
Assert-PathExists -Path $nodeExe -Label "node executable"
Write-Step "Resolved npm command at $npmCmd"
Write-Step "Resolved node command at $nodeExe"

if ((-not $SkipInstall) -and (-not (Test-Path (Join-Path $webPath "node_modules")))) {
    Write-Step "Installing npm dependencies in bill-web"
    Set-Location -Path "$webPath"
    & "$npmCmd" install
}

Write-Step "Freeing required ports (8000, $webPort)"
Stop-PortListeners -Ports @(8000, $webPort)

$workerPkgFile = Join-Path $root "jarvis-platform\workers\bill-worker\package-output\bill-worker-lite.zip"
$coreCommand = "Set-Location -Path `"$corePath`"; `$env:BILL_CORE_HOST=`"0.0.0.0`"; `$env:BILL_CORE_PORT=`"8000`"; `$env:BILL_WORKER_LATEST_VERSION=`"0.3.21`"; `$env:BILL_WORKER_PACKAGE_FILE=`"$workerPkgFile`"; `$env:BILL_WORKER_PACKAGE_PUBLIC_URL=`"https://api.bill-core.com/worker/update/package`"; `$env:BILL_WORKER_FORCE_UPDATE=`"false`"; & `"$corePythonExe`" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000"
$workerCommand = "Set-Location -Path `"$workerPath`"; `$env:BILL_CORE_URL=`"http://127.0.0.1:8000`"; `$env:JARVIS_CORE_URL=`"http://127.0.0.1:8000`"; & `"$workerPythonExe`" main.py"
$webCommand = "Set-Location -Path `"$webPath`"; `$env:NEXT_PUBLIC_API_BASE = `"http://127.0.0.1:8000`"; `$env:Path = `"C:\Program Files\nodejs;`" + `$env:Path; & `"$nodeExe`" .\node_modules\next\dist\bin\next dev -p $webPort"
Write-Step "Freeing required ports (8010, $webPort)"
Stop-PortListeners -Ports @(8010, $webPort)

$coreCommand = "Set-Location -Path `"$corePath`"; `$env:BILL_CORE_HOST=`"0.0.0.0`"; `$env:BILL_CORE_PORT=`"8010`"; `$env:BILL_WORKER_LATEST_VERSION=`"0.3.21`"; `$env:BILL_WORKER_PACKAGE_FILE=`"$workerPkgFile`"; `$env:BILL_WORKER_PACKAGE_PUBLIC_URL=`"https://api.bill-core.com/worker/update/package`"; `$env:BILL_WORKER_FORCE_UPDATE=`"false`"; & `"$corePythonExe`" -m uvicorn main:app --reload --host 0.0.0.0 --port 8010"
$workerCommand = "Set-Location -Path `"$workerPath`"; `$env:BILL_CORE_URL=`"http://127.0.0.1:8010`"; `$env:JARVIS_CORE_URL=`"http://127.0.0.1:8010`"; & `"$workerPythonExe`" main.py"
$webCommand = "Set-Location -Path `"$webPath`"; `$env:NEXT_PUBLIC_API_BASE = `"http://127.0.0.1:8010`"; `$env:Path = `"C:\Program Files\nodejs;`" + `$env:Path; & `"$nodeExe`" .\node_modules\next\dist\bin\next dev -p $webPort"
Write-Step "Install steps complete. Starting services..."
Start-ServiceWindow -Title "bill-core" -ScriptText $coreCommand
Start-Sleep -Seconds 1
Start-ServiceWindow -Title "bill-worker" -ScriptText $workerCommand
Start-Sleep -Seconds 1
Start-ServiceWindow -Title "bill-web" -ScriptText $webCommand

Write-Step "All launch windows opened."
Write-Step "Dashboard URL: http://localhost:$webPort"
