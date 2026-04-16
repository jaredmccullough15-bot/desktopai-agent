# Distribution Package Builder
# This script builds and packages everything your coworkers need

Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "Desktop AI Agent - Distribution Builder" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Cyan

# Activate virtual environment
Write-Host "[1/5] Activating virtual environment..." -ForegroundColor Yellow
.\venv\Scripts\Activate.ps1

# Check if PyInstaller is installed
Write-Host "[2/5] Checking PyInstaller..." -ForegroundColor Yellow
$pyinstaller = python -m pip list | Select-String "pyinstaller"
if (-not $pyinstaller) {
    Write-Host "Installing PyInstaller..." -ForegroundColor Yellow
    python -m pip install pyinstaller
}

# Ask user which build type
Write-Host "`n[3/5] Select build type:" -ForegroundColor Yellow
Write-Host "  1 - Folder distribution (RECOMMENDED - more reliable)"
Write-Host "  2 - Single file distribution (easier to share)"
$choice = Read-Host "Enter choice (1 or 2)"

# Build the application
Write-Host "`n[4/5] Building application..." -ForegroundColor Yellow
Write-Host "This may take 5-15 minutes. Please wait...`n" -ForegroundColor Yellow

if ($choice -eq "2") {
    python build_app.py
    $exePath = "dist\DesktopAIAgent.exe"
} else {
    python build_app_folder.py
    $exePath = "dist\DesktopAIAgent\DesktopAIAgent.exe"
}

# Check if build succeeded
if (-not (Test-Path $exePath)) {
    Write-Host "`nBUILD FAILED!" -ForegroundColor Red
    Write-Host "Check error messages above." -ForegroundColor Red
    exit 1
}

# Create distribution package
Write-Host "`n[5/5] Creating distribution package..." -ForegroundColor Yellow

$packageFolder = "DesktopAIAgent_ForDistribution"
if (Test-Path $packageFolder) {
    Remove-Item $packageFolder -Recurse -Force
}
New-Item $packageFolder -ItemType Directory | Out-Null

if ($choice -eq "2") {
    # Single file distribution
    Copy-Item "dist\DesktopAIAgent.exe" $packageFolder
} else {
    # Folder distribution
    Copy-Item "dist\DesktopAIAgent" $packageFolder -Recurse
}

# Copy support files
Copy-Item ".env.template" "$packageFolder\.env.template"
Copy-Item "README_SETUP.txt" "$packageFolder\README_SETUP.txt"

# Create the ZIP
$zipName = "DesktopAIAgent_Package.zip"
if (Test-Path $zipName) {
    Remove-Item $zipName -Force
}

Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory(
    (Resolve-Path $packageFolder).Path,
    (Join-Path (Get-Location) $zipName)
)

# Success message
Write-Host "`n========================================" -ForegroundColor Green
Write-Host "BUILD COMPLETE!" -ForegroundColor Green
Write-Host "========================================`n" -ForegroundColor Green

Write-Host "Package ready: $zipName" -ForegroundColor Green
Write-Host "Size: $([math]::Round((Get-Item $zipName).Length/1MB, 2)) MB`n" -ForegroundColor Cyan

Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1. Share '$zipName' with your coworkers" -ForegroundColor White
Write-Host "2. Tell them to extract the ZIP" -ForegroundColor White
Write-Host "3. Rename .env.template to .env and add API keys" -ForegroundColor White
Write-Host "4. Run DesktopAIAgent.exe`n" -ForegroundColor White

Write-Host "IMPORTANT:" -ForegroundColor Red
Write-Host "- DO NOT include your own .env file" -ForegroundColor White
Write-Host "- Each user needs their own API keys" -ForegroundColor White
Write-Host "- Test the package on another computer first`n" -ForegroundColor White
