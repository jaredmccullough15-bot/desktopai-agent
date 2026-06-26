$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Building deployment package..."

$outputZip = Join-Path $PSScriptRoot "..\bill-core-deploy.zip"
$localZip = Join-Path $PSScriptRoot "bill-core-deploy.zip"

if (Test-Path $outputZip) {
    Remove-Item $outputZip -Force
}

# Find the correct Python executable
$pythonExe = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "Venv Python not found, falling back to py -3"
    $pythonExe = "py -3"
}
if (-not (Test-Path $pythonExe)) {
    Write-Host "py -3 not found, falling back to python"
    $pythonExe = "python"
}

Write-Host "Python path selected: $pythonExe"
& $pythonExe --version
Write-Host "Current working directory: $(Get-Location)"
Write-Host "Build script path: $PSScriptRoot"

function Invoke-PythonChecked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Script
    )

    Write-Host "Running Python script: $Script"
    & $pythonExe $Script
    if ($LASTEXITCODE -ne 0) {
        throw "Step failed ($Script) with exit code $LASTEXITCODE"
    }
}

Write-Host "Step 1: Generating build manifest..."
Invoke-PythonChecked "build_manifest.py"

Write-Host "Step 2: Verifying source structure..."
Invoke-PythonChecked "verify_structure.py"

Write-Host "Step 3: Building deployment zip..."
Invoke-PythonChecked "build_eb_zip.py"

if (!(Test-Path $localZip)) {
    throw "Expected build output not found: $localZip"
}

Copy-Item $localZip $outputZip -Force

Write-Host "Step 4: Verifying deployment package contents..."
Invoke-PythonChecked "verify_deploy_package.py"

Write-Host "Done."
