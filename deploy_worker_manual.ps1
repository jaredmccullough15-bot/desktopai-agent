param(
    [string]$PackagePath = "",
    [string]$WorkerRoot = "C:\Ai Agent\desktop-ai-agent\jarvis-platform\workers\bill-worker",
    [string]$BackupRoot = "C:\JarvisWorkerBackup"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step {
    param([string]$Message)
    Write-Host "[manual-deploy] $Message" -ForegroundColor Cyan
}

function Fail-Deploy {
    param([string]$Message)
    Write-Host "[manual-deploy] ERROR: $Message" -ForegroundColor Red
    exit 1
}

function Resolve-ExistingPath {
    param([string[]]$Candidates)
    foreach ($candidate in $Candidates) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }
    return $null
}

function Stop-WorkerSafely {
    param([string]$ResolvedWorkerRoot)

    $stopScript = Resolve-ExistingPath -Candidates @(
        (Join-Path $ResolvedWorkerRoot "stop_worker.ps1"),
        (Join-Path $ResolvedWorkerRoot "stop-worker.ps1")
    )

    if ($stopScript) {
        Write-Step "Stopping worker via script: $stopScript"
        & powershell -NoProfile -ExecutionPolicy Bypass -File $stopScript
        return
    }

    Write-Step "No stop script found. Stopping worker processes by path-safe filter."
    $escapedRoot = [Regex]::Escape($ResolvedWorkerRoot)

    $candidatePids = @()
    $processes = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    foreach ($process in $processes) {
        $cmd = [string]$process.CommandLine
        $exe = [string]$process.ExecutablePath
        $name = [string]$process.Name
        $matchesRoot = ($cmd -match $escapedRoot) -or ($exe -match $escapedRoot)
        $looksLikeWorker = ($name -ieq "BillWorker.exe") -or ($cmd -match "worker_main.py") -or ($cmd -match "bill-worker")
        if ($matchesRoot -and $looksLikeWorker) {
            $candidatePids += [int]$process.ProcessId
        }
    }

    $candidatePids = $candidatePids | Sort-Object -Unique
    foreach ($pid in $candidatePids) {
        try {
            Stop-Process -Id $pid -Force -ErrorAction Stop
            Write-Step "Stopped process PID=$pid"
        } catch {
            Write-Host "[manual-deploy] WARN: Could not stop PID=$pid ($($_.Exception.Message))" -ForegroundColor Yellow
        }
    }
}

function Test-ConfigHasSecrets {
    param([string]$Path)

    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }

    try {
        $content = Get-Content -LiteralPath $Path -Raw -Encoding UTF8
        $json = $content | ConvertFrom-Json
    } catch {
        return $false
    }

    $secretKeys = @(
        "worker_shared_secret",
        "bill_core_worker_shared_secret",
        "api_key",
        "core_api_key"
    )

    foreach ($key in $secretKeys) {
        $prop = $json.PSObject.Properties[$key]
        if ($null -ne $prop) {
            $value = [string]$prop.Value
            if (-not [string]::IsNullOrWhiteSpace($value)) {
                return $true
            }
        }
    }

    return $false
}

if (-not (Test-Path -LiteralPath $WorkerRoot)) {
    Fail-Deploy "Worker root does not exist: $WorkerRoot"
}

$resolvedWorkerRoot = (Resolve-Path -LiteralPath $WorkerRoot).Path

if ([string]::IsNullOrWhiteSpace($PackagePath)) {
    $autoPackage = Resolve-ExistingPath -Candidates @(
        "C:\Ai Agent\desktop-ai-agent\package-output\bill-worker\bill-worker-complete.zip",
        (Join-Path $resolvedWorkerRoot "package-output\bill-worker\bill-worker-complete.zip"),
        "C:\Ai Agent\desktop-ai-agent\bill-worker\package-output\bill-worker\bill-worker-complete.zip"
    )
    if (-not $autoPackage) {
        Fail-Deploy "PackagePath not provided and default bill-worker-complete.zip not found."
    }
    $PackagePath = $autoPackage
}

if (-not (Test-Path -LiteralPath $PackagePath)) {
    Fail-Deploy "Package zip not found: $PackagePath"
}

$resolvedPackage = (Resolve-Path -LiteralPath $PackagePath).Path
if ([IO.Path]::GetExtension($resolvedPackage).ToLowerInvariant() -ne ".zip") {
    Fail-Deploy "Package must be a .zip file: $resolvedPackage"
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupPath = Join-Path $BackupRoot $timestamp
$tempRoot = Join-Path $env:TEMP ("bill_worker_manual_deploy_" + $timestamp)
$extractDir = Join-Path $tempRoot "extract"

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
New-Item -ItemType Directory -Force -Path $tempRoot | Out-Null

$existingConfigPath = Join-Path $resolvedWorkerRoot "config.json"
$existingConfigTempPath = Join-Path $tempRoot "existing_config.json"
$hadExistingConfig = Test-Path -LiteralPath $existingConfigPath
if ($hadExistingConfig) {
    Copy-Item -LiteralPath $existingConfigPath -Destination $existingConfigTempPath -Force
}

try {
    Write-Step "Stopping existing worker"
    Stop-WorkerSafely -ResolvedWorkerRoot $resolvedWorkerRoot

    Write-Step "Backing up current worker folder to $backupPath"
    New-Item -ItemType Directory -Force -Path $backupPath | Out-Null
    $backupRc = 0
    & robocopy $resolvedWorkerRoot $backupPath /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    $backupRc = $LASTEXITCODE
    if ($backupRc -ge 8) {
        Fail-Deploy "Backup failed (robocopy exit code $backupRc)."
    }

    Write-Step "Extracting package: $resolvedPackage"
    Expand-Archive -Path $resolvedPackage -DestinationPath $extractDir -Force

    Write-Step "Replacing worker files"
    & robocopy $extractDir $resolvedWorkerRoot /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    $copyRc = $LASTEXITCODE
    if ($copyRc -ge 8) {
        Fail-Deploy "Package copy failed (robocopy exit code $copyRc)."
    }

    $zipConfigPath = Join-Path $extractDir "config.json"
    if ($hadExistingConfig) {
        if (-not (Test-Path -LiteralPath $zipConfigPath)) {
            Write-Step "Zip did not include config.json; preserving previous config.json"
            Copy-Item -LiteralPath $existingConfigTempPath -Destination $existingConfigPath -Force
        } else {
            $existingHasSecrets = Test-ConfigHasSecrets -Path $existingConfigTempPath
            $zipHasSecrets = Test-ConfigHasSecrets -Path $zipConfigPath
            if ($existingHasSecrets -and -not $zipHasSecrets) {
                Write-Step "Zip config.json appears to omit secrets; restoring previous config.json"
                Copy-Item -LiteralPath $existingConfigTempPath -Destination $existingConfigPath -Force
            }
        }
    }

    $startScript = Resolve-ExistingPath -Candidates @(
        (Join-Path $resolvedWorkerRoot "start_worker.ps1"),
        (Join-Path $resolvedWorkerRoot "start-worker.ps1")
    )
    if (-not $startScript) {
        Fail-Deploy "Could not find start_worker.ps1 or start-worker.ps1 in $resolvedWorkerRoot"
    }

    Write-Step "Starting worker via: $startScript"
    Start-Process -FilePath "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $startScript) -WorkingDirectory $resolvedWorkerRoot | Out-Null

    $logsDir = Join-Path $resolvedWorkerRoot "logs"
    if (-not (Test-Path -LiteralPath $logsDir)) {
        New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
    }

    Write-Step "Tailing worker logs for 30 seconds"
    $startTime = Get-Date
    $deadline = $startTime.AddSeconds(30)
    $lastSizeByFile = @{}
    $capturedText = ""

    while ((Get-Date) -lt $deadline) {
        $logFiles = Get-ChildItem -LiteralPath $logsDir -Filter "*.log" -File -ErrorAction SilentlyContinue | Sort-Object LastWriteTime
        foreach ($log in $logFiles) {
            $fullName = $log.FullName
            $previousSize = 0
            if ($lastSizeByFile.ContainsKey($fullName)) {
                $previousSize = [int64]$lastSizeByFile[$fullName]
            }
            $currentSize = [int64]$log.Length
            if ($currentSize -gt $previousSize) {
                $bytesToRead = $currentSize - $previousSize
                $fs = [System.IO.File]::Open($fullName, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
                try {
                    $null = $fs.Seek($previousSize, [System.IO.SeekOrigin]::Begin)
                    $buffer = New-Object byte[] $bytesToRead
                    $null = $fs.Read($buffer, 0, $bytesToRead)
                    $chunk = [System.Text.Encoding]::UTF8.GetString($buffer)
                    if (-not [string]::IsNullOrWhiteSpace($chunk)) {
                        $capturedText += $chunk
                        $chunkLines = $chunk -split "`r?`n"
                        foreach ($line in $chunkLines) {
                            if (-not [string]::IsNullOrWhiteSpace($line)) {
                                Write-Host "[worker-log] $line"
                            }
                        }
                    }
                } finally {
                    $fs.Close()
                }
            }
            $lastSizeByFile[$fullName] = $currentSize
        }
        Start-Sleep -Seconds 2
    }

    $checks = @(
        @{ Name = "TEACH_TARGET_SELECTION_VERSION=2.0"; Pattern = "TEACH_TARGET_SELECTION_VERSION\s*=\s*2\.0|TEACH_TARGET_SELECTION_VERSION=2\.0" },
        @{ Name = "SHOW_LEGACY_OBSERVATION_PANEL=False"; Pattern = "SHOW_LEGACY_OBSERVATION_PANEL\s*=\s*False|SHOW_LEGACY_OBSERVATION_PANEL=False" },
        @{ Name = "TEACH_LEGACY_OBSERVATION_PANEL_DISABLED"; Pattern = "TEACH_LEGACY_OBSERVATION_PANEL_DISABLED" },
        @{ Name = "worker registration 200"; Pattern = "Registration succeeded\..*status=200|HTTP register response:.*status=200" },
        @{ Name = "heartbeat 200"; Pattern = "Heartbeat sent\..*status=200" }
    )

    $failedChecks = @()
    foreach ($check in $checks) {
        if ($capturedText -notmatch $check.Pattern) {
            $failedChecks += $check.Name
        }
    }

    if ($failedChecks.Count -gt 0) {
        Write-Host "[manual-deploy] Deployment completed, but verification failed." -ForegroundColor Yellow
        foreach ($failed in $failedChecks) {
            Write-Host "[manual-deploy] Missing check: $failed" -ForegroundColor Yellow
        }
        Write-Host "[manual-deploy] Backup available at: $backupPath" -ForegroundColor Yellow
        Write-Host "[manual-deploy] Restore command:" -ForegroundColor Yellow
        Write-Host "robocopy \"$backupPath\" \"$resolvedWorkerRoot\" /MIR /R:1 /W:1" -ForegroundColor Yellow
        exit 2
    }

    Write-Host "[manual-deploy] Deployment and verification succeeded." -ForegroundColor Green
    Write-Host "[manual-deploy] Backup path: $backupPath" -ForegroundColor Green
}
finally {
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}