param(
    [string]$ReleaseRoot = "dist"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host "[release-build] $Message" -ForegroundColor Cyan
}

$scriptPath = $PSCommandPath
if ([string]::IsNullOrWhiteSpace($scriptPath)) {
    $scriptPath = $MyInvocation.MyCommand.Path
}
if ([string]::IsNullOrWhiteSpace($scriptPath)) {
    throw "Unable to determine script path"
}

$workerRoot = Split-Path -Parent (Split-Path -Parent $scriptPath)
$portableBuildScript = Join-Path $workerRoot "build-portable-worker.ps1"
if (-not (Test-Path $portableBuildScript)) {
    throw "Missing build script: $portableBuildScript"
}

$releaseRootPath = if ([IO.Path]::IsPathRooted($ReleaseRoot)) {
    $ReleaseRoot
} else {
    Join-Path $workerRoot $ReleaseRoot
}

$distFolder = Join-Path $releaseRootPath "BillWorker"
$zipPath = Join-Path $releaseRootPath "BillWorker.zip"
$stagingFolder = Join-Path $workerRoot ".release-staging\BillWorker"

Write-Step "Cleaning old release output"
if (Test-Path $releaseRootPath) {
    Remove-Item -Path $releaseRootPath -Recurse -Force
}
if (Test-Path (Split-Path -Parent $stagingFolder)) {
    Remove-Item -Path (Split-Path -Parent $stagingFolder) -Recurse -Force
}

New-Item -ItemType Directory -Path $releaseRootPath -Force | Out-Null
New-Item -ItemType Directory -Path (Split-Path -Parent $stagingFolder) -Force | Out-Null

Write-Step "Building portable worker staging folder"
& $portableBuildScript -OutputPath $stagingFolder
if ($LASTEXITCODE -ne 0) {
    throw "Portable build failed"
}

Write-Step "Preparing dist folder"
if (Test-Path $releaseRootPath) {
    Remove-Item -Path $releaseRootPath -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseRootPath -Force | Out-Null
Move-Item -Path $stagingFolder -Destination $distFolder -Force

Write-Step "Creating Windows-compatible zip"
if (Test-Path $zipPath) {
    Remove-Item -Path $zipPath -Force
}
Compress-Archive -Path (Join-Path $distFolder "*") -DestinationPath $zipPath -CompressionLevel Optimal -Force

if (Test-Path (Split-Path -Parent $stagingFolder)) {
    Remove-Item -Path (Split-Path -Parent $stagingFolder) -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Step "Release build complete"
$distItem = Get-Item $distFolder
$zipItem = Get-Item $zipPath
Write-Host "Folder: $($distItem.FullName)" -ForegroundColor Green
Write-Host "ZIP:    $($zipItem.FullName)" -ForegroundColor Green
Write-Host "ZIP size bytes: $($zipItem.Length)" -ForegroundColor Green
