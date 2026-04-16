$ErrorActionPreference = 'Stop'
Write-Host "Portable setup starting..." -ForegroundColor Cyan

# Use script directory reliably
$repo = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($repo)) {
    if ($MyInvocation.MyCommand.Path) {
        $repo = Split-Path -Parent $MyInvocation.MyCommand.Path
    }
}
if ([string]::IsNullOrWhiteSpace($repo)) {
    $repo = (Get-Location).Path
}
Push-Location $repo

function Get-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) { return 'python' }
    elseif (Get-Command py -ErrorAction SilentlyContinue) { return 'py -3' }
    else { return $null }
}

# Ensure Python is available; if not, download and install per-user
function Ensure-Python {
    $py = Get-PythonCommand
    if ($py) { return $py }

    Write-Host "Python not found. Downloading installer..." -ForegroundColor Yellow
    try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
    $installerUrl = "https://www.python.org/ftp/python/3.12.2/python-3.12.2-amd64.exe"
    $installerPath = Join-Path $repo "python-installer.exe"
    try {
        Invoke-WebRequest -Uri $installerUrl -OutFile $installerPath -UseBasicParsing
    } catch {
        Write-Warning "Failed to download Python installer: $($_.Exception.Message)"
    }

    if (!(Test-Path $installerPath)) {
        Write-Error "Could not download Python. Please install Python 3.12+ from https://www.python.org/downloads/windows/ and re-run setup.ps1."
    }

    Write-Host "Running Python installer (per-user, adds pip + PATH)..." -ForegroundColor Yellow
    $args = "/quiet InstallAllUsers=0 PrependPath=1 Include_pip=1"
    try {
        Start-Process -FilePath $installerPath -ArgumentList $args -Wait
    } catch {
        Write-Warning "Python installer failed: $($_.Exception.Message)"
    }

    # Try to find python in typical per-user install location
    $candidateDir = Join-Path $env:LocalAppData "Programs\Python"
    $pythonExe = Get-ChildItem -Path $candidateDir -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($pythonExe) { return $pythonExe.FullName }

    # Fallback: try detecting via PATH or launcher again
    return Get-PythonCommand
}

$py = Ensure-Python
if (-not $py) {
    Write-Error "Python 3 is required. Please install Python (3.12+) and re-run setup.ps1."
}

if (!(Test-Path "$repo\venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    & $py -m venv "$repo\venv"
} else {
    Write-Host "venv already exists; reusing" -ForegroundColor Green
}

# Activate venv
$envPath = Join-Path $repo "venv\Scripts\Activate.ps1"
if (!(Test-Path $envPath)) {
    throw "Could not find venv activation script at: $envPath"
}
. $envPath

Write-Host "Upgrading pip/setuptools/wheel" -ForegroundColor Yellow
python -m pip install --upgrade pip setuptools wheel

if (Test-Path "$repo\requirements.txt") {
    Write-Host "Installing from requirements.txt" -ForegroundColor Yellow
    python -m pip install -r "$repo\requirements.txt"
} else {
    Write-Host "requirements.txt not found; installing common deps" -ForegroundColor Yellow
    python -m pip install customtkinter pyautogui selenium mss pytesseract pillow sounddevice pynput openai python-dotenv imageio
}

Write-Host "Ensuring critical runtime modules" -ForegroundColor Yellow
python -m pip install sounddevice soundfile

# Try PyAudio install; fall back to wheel if needed
function Install-PyAudio {
    try {
        python -m pip install pyaudio -q
        return $true
    } catch {
        return $false
    }
}

Write-Host "Ensuring PyAudio (optional)" -ForegroundColor Yellow
$ok = Install-PyAudio
if (-not $ok) {
    Write-Host "pip install failed; attempting wheel..." -ForegroundColor Yellow
    $pyTag = & python -c "import sys; print(f'cp{sys.version_info.major}{sys.version_info.minor}')"
    $wheel = "PyAudio-0.2.14-$pyTag-$pyTag-win_amd64.whl"
    $url = "https://github.com/intxcc/pyaudio_portaudio/releases/download/v0.2.14/$wheel"
    $wheelPath = Join-Path $repo $wheel
    try {
        Invoke-WebRequest -Uri $url -OutFile $wheelPath -UseBasicParsing
        python -m pip install $wheelPath
        Remove-Item $wheelPath -Force -ErrorAction SilentlyContinue
        Write-Host "PyAudio installed via wheel" -ForegroundColor Green
    } catch {
        Write-Warning "PyAudio wheel install failed; audio features may be disabled"
    }
}

Write-Host "Setup complete. Use run.ps1 to start the agent." -ForegroundColor Green
Pop-Location
