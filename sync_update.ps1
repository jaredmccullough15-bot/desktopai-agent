param(
    [string]$SharedRoot = "$env:OneDrive\DesktopAIAgentSync",
    [switch]$IncludeMemory,
    [switch]$SkipBackup,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

function Resolve-SharedRoot {
    param([string]$PreferredRoot)

    $syncFolderNames = @('DesktopAIAgentSync', 'AIAgentShared')
    $candidates = @()
    if ($PreferredRoot) {
        $candidates += $PreferredRoot
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $PreferredRoot $name)
        }
    }

    if ($env:DESKTOP_AI_SYNC_ROOT) {
        $candidates += $env:DESKTOP_AI_SYNC_ROOT
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:DESKTOP_AI_SYNC_ROOT $name)
        }
    }

    if ($env:SHARED_DATA_PATH) {
        $candidates += $env:SHARED_DATA_PATH
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:SHARED_DATA_PATH $name)
        }
    }

    if ($env:AIAgentSharedPath) {
        $candidates += $env:AIAgentSharedPath
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:AIAgentSharedPath $name)
        }
    }

    if ($env:OneDrive) {
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:OneDrive $name)
            $candidates += (Join-Path (Join-Path $env:OneDrive 'Desktop') $name)
            $candidates += (Join-Path (Join-Path $env:OneDrive 'Documents') $name)
        }
    }
    if ($env:OneDriveCommercial) {
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:OneDriveCommercial $name)
            $candidates += (Join-Path (Join-Path $env:OneDriveCommercial 'Desktop') $name)
            $candidates += (Join-Path (Join-Path $env:OneDriveCommercial 'Documents') $name)
        }
    }
    if ($env:OneDriveConsumer) {
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:OneDriveConsumer $name)
            $candidates += (Join-Path (Join-Path $env:OneDriveConsumer 'Desktop') $name)
            $candidates += (Join-Path (Join-Path $env:OneDriveConsumer 'Documents') $name)
        }
    }

    try {
        $oneDriveDirs = Get-ChildItem -Path $env:UserProfile -Directory -Filter 'OneDrive*' -ErrorAction SilentlyContinue
        foreach ($d in $oneDriveDirs) {
            foreach ($name in $syncFolderNames) {
                $candidates += (Join-Path $d.FullName $name)
                $candidates += (Join-Path (Join-Path $d.FullName 'Desktop') $name)
                $candidates += (Join-Path (Join-Path $d.FullName 'Documents') $name)
            }
        }
    } catch {
    }

    $uniqueCandidates = @()
    foreach ($c in $candidates) {
        if ([string]::IsNullOrWhiteSpace($c)) { continue }
        $trimmed = $c.Trim()
        if ($uniqueCandidates -notcontains $trimmed) {
            $uniqueCandidates += $trimmed
        }
    }

    foreach ($root in $uniqueCandidates) {
        if (Test-Path (Join-Path $root 'sync_update.ps1')) {
            return $root
        }
        $current = Join-Path $root 'current'
        if (Test-Path $current) {
            return $root
        }
    }

    throw "Shared current folder not found. Checked: $($uniqueCandidates -join '; ')"
}

function Invoke-Robocopy {
    param(
        [string]$From,
        [string]$To,
        [string[]]$ExcludeDirs,
        [string[]]$ExcludeFiles,
        [switch]$Dry
    )

    $args = @(
        $From,
        $To,
        '/MIR',
        '/R:1',
        '/W:1',
        '/NFL',
        '/NDL',
        '/NP'
    )

    if ($Dry) {
        $args += '/L'
    }

    if ($ExcludeDirs -and $ExcludeDirs.Count -gt 0) {
        $args += '/XD'
        $args += $ExcludeDirs
    }

    if ($ExcludeFiles -and $ExcludeFiles.Count -gt 0) {
        $args += '/XF'
        $args += $ExcludeFiles
    }

    & robocopy @args | Out-Null
    $code = $LASTEXITCODE
    if ($code -gt 7) {
        throw "Robocopy failed with code $code"
    }
}

$repoRoot = $PSScriptRoot
$SharedRoot = Resolve-SharedRoot -PreferredRoot $SharedRoot
$sharedCurrent = Join-Path $SharedRoot 'current'

if (-not (Test-Path $sharedCurrent)) {
    throw "Shared current folder not found: $sharedCurrent"
}

Write-Host "Updating Desktop AI Agent from shared folder..." -ForegroundColor Cyan
Write-Host "Local: $repoRoot" -ForegroundColor DarkGray
Write-Host "Shared: $sharedCurrent" -ForegroundColor DarkGray

$excludeDirs = @(
    '.git',
    '.github',
    'venv',
    'dist',
    'build',
    '__pycache__',
    'backups'
)

$excludeFiles = @(
    '.env',
    'agent.log',
    'conversation_history.json',
    'current_screen.png',
    '*.pyc',
    '*.pyo'
)

if (-not $IncludeMemory) {
    $excludeFiles += 'desktop_memory.json'
}

if (-not $SkipBackup) {
    $backupRoot = Join-Path $repoRoot 'backups'
    $backupPath = Join-Path $backupRoot ("sync_" + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
    Invoke-Robocopy -From $repoRoot -To $backupPath -ExcludeDirs $excludeDirs -ExcludeFiles $excludeFiles -Dry:$DryRun
    if ($DryRun) {
        Write-Host "Dry run backup preview complete: $backupPath" -ForegroundColor Yellow
    } else {
        Write-Host "Backup created: $backupPath" -ForegroundColor Green
    }
}

Invoke-Robocopy -From $sharedCurrent -To $repoRoot -ExcludeDirs $excludeDirs -ExcludeFiles $excludeFiles -Dry:$DryRun

if ($DryRun) {
    Write-Host "Dry run update preview complete. No files changed." -ForegroundColor Yellow
} else {
    Write-Host "Update complete." -ForegroundColor Green
    Write-Host "Run setup.ps1 if requirements changed." -ForegroundColor DarkGray
}
