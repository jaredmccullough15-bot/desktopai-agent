param(
    [string]$SharedRoot = "$env:OneDrive\DesktopAIAgentSync",
    [switch]$IncludeMemory
)

$ErrorActionPreference = 'Stop'

function Resolve-PublishRoot {
    param([string]$PreferredRoot)

    $syncFolderNames = @('DesktopAIAgentSync', 'AIAgentShared')
    $candidates = @()

    if ($PreferredRoot -and $PreferredRoot.Trim()) {
        $candidates += $PreferredRoot.Trim()
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $PreferredRoot.Trim() $name)
        }
    }

    if ($env:DESKTOP_AI_SYNC_ROOT -and $env:DESKTOP_AI_SYNC_ROOT.Trim()) {
        $candidates += $env:DESKTOP_AI_SYNC_ROOT.Trim()
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:DESKTOP_AI_SYNC_ROOT.Trim() $name)
        }
    }

    if ($env:SHARED_DATA_PATH -and $env:SHARED_DATA_PATH.Trim()) {
        $candidates += $env:SHARED_DATA_PATH.Trim()
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:SHARED_DATA_PATH.Trim() $name)
        }
    }

    if ($env:AIAgentSharedPath -and $env:AIAgentSharedPath.Trim()) {
        $candidates += $env:AIAgentSharedPath.Trim()
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:AIAgentSharedPath.Trim() $name)
        }
    }

    if ($env:OneDrive -and $env:OneDrive.Trim()) {
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:OneDrive $name)
            $candidates += (Join-Path (Join-Path $env:OneDrive 'Desktop') $name)
            $candidates += (Join-Path (Join-Path $env:OneDrive 'Documents') $name)
        }
    }

    if ($env:OneDriveCommercial -and $env:OneDriveCommercial.Trim()) {
        foreach ($name in $syncFolderNames) {
            $candidates += (Join-Path $env:OneDriveCommercial $name)
            $candidates += (Join-Path (Join-Path $env:OneDriveCommercial 'Desktop') $name)
            $candidates += (Join-Path (Join-Path $env:OneDriveCommercial 'Documents') $name)
        }
    }

    if ($env:OneDriveConsumer -and $env:OneDriveConsumer.Trim()) {
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
        if (-not (Test-Path $root)) { continue }
        if (Test-Path (Join-Path $root 'current')) { return $root }
        if (Test-Path (Join-Path $root 'last_publish.json')) { return $root }
        if (Test-Path (Join-Path $root 'sync_update.ps1')) { return $root }
        if ($syncFolderNames -contains (Split-Path $root -Leaf)) { return $root }
    }

    foreach ($root in $uniqueCandidates) {
        $parent = Split-Path $root -Parent
        if ($parent -and (Test-Path $parent)) {
            return $root
        }
    }

    throw "Could not determine shared root. Set DESKTOP_AI_SYNC_ROOT (or SHARED_DATA_PATH) or pass -SharedRoot. Checked: $($uniqueCandidates -join '; ')"
}

function Invoke-Robocopy {
    param(
        [string]$From,
        [string]$To,
        [string[]]$ExcludeDirs,
        [string[]]$ExcludeFiles
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
$SharedRoot = Resolve-PublishRoot -PreferredRoot $SharedRoot
$currentTarget = Join-Path $SharedRoot 'current'
$releaseRoot = Join-Path $SharedRoot 'releases'
$releaseName = Get-Date -Format 'yyyyMMdd_HHmmss'
$releaseTarget = Join-Path $releaseRoot $releaseName

Write-Host "Publishing Desktop AI Agent to shared folder..." -ForegroundColor Cyan
Write-Host "Source: $repoRoot" -ForegroundColor DarkGray
Write-Host "Shared: $SharedRoot" -ForegroundColor DarkGray

New-Item -ItemType Directory -Path $currentTarget -Force | Out-Null
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

$excludeDirs = @(
    '.git',
    '.github',
    'venv',
    'dist',
    'build',
    '__pycache__',
    'tools'
)

$excludeFiles = @(
    '.env',
    'speech_temp.mp3',
    'test_*.py',
    '*_test.py',
    '*.pyc',
    '*.pyo'
)

if (-not $IncludeMemory) {
    $excludeFiles += @(
        'agent.log',
        'conversation_history.json',
        'current_screen.png',
        'desktop_memory.json'
    )
}

Invoke-Robocopy -From $repoRoot -To $currentTarget -ExcludeDirs $excludeDirs -ExcludeFiles $excludeFiles
Invoke-Robocopy -From $currentTarget -To $releaseTarget -ExcludeDirs @() -ExcludeFiles @()

$meta = @{
    published_at = (Get-Date).ToString('s')
    source_machine = $env:COMPUTERNAME
    include_memory = [bool]$IncludeMemory
    current_path = $currentTarget
    release_path = $releaseTarget
} | ConvertTo-Json -Depth 3

Set-Content -Path (Join-Path $SharedRoot 'last_publish.json') -Value $meta -Encoding UTF8

$statusText = @(
    "Last Publish: $((Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))",
    "Source Machine: $env:COMPUTERNAME",
    "Current Path: $currentTarget",
    "Release Path: $releaseTarget"
) -join [Environment]::NewLine
Set-Content -Path (Join-Path $SharedRoot 'PUBLISH_STATUS.txt') -Value $statusText -Encoding UTF8

Write-Host "Publish complete." -ForegroundColor Green
Write-Host "Current: $currentTarget" -ForegroundColor Green
Write-Host "Release: $releaseTarget" -ForegroundColor Green
