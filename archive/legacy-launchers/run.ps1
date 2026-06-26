$ErrorActionPreference = 'Stop'
Write-Host "Launching Desktop AI Agent" -ForegroundColor Cyan

# Use script directory reliably
$repo = $PSScriptRoot
$envPath = Join-Path $repo "venv\Scripts\Activate.ps1"
if (!(Test-Path $envPath)) {
    Write-Error "venv not found. Run setup.ps1 first."
}

. $envPath

Write-Host "Checking required Python modules..." -ForegroundColor Yellow
$moduleRepairScript = @'
import importlib
import subprocess
import sys

required = {
    "pynput": "pynput",
    "selenium": "selenium",
    "openai": "openai",
    "google.generativeai": "google-generativeai",
    "PIL": "pillow",
    "pyautogui": "pyautogui",
    "customtkinter": "customtkinter",
    "speech_recognition": "SpeechRecognition",
    "dotenv": "python-dotenv",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "openpyxl": "openpyxl",
    "mss": "mss",
    "pytesseract": "pytesseract",
    "cv2": "opencv-python",
    "numpy": "numpy",
    "sounddevice": "sounddevice",
    "soundfile": "soundfile",
}

def has_module(module_name: str) -> bool:
    try:
        importlib.import_module(module_name)
        return True
    except Exception:
        return False

missing_pairs = sorted({(mod, pkg) for mod, pkg in required.items() if not has_module(mod)}, key=lambda x: x[1])
missing = [pkg for _, pkg in missing_pairs]
if missing:
    print("Installing missing modules:", ", ".join(missing))
    rc = subprocess.call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", *missing])
    if rc != 0:
        print("Warning: pip install returned non-zero exit code", rc)
        for _, pkg in missing_pairs:
            subprocess.call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--upgrade", pkg])

still_missing = sorted({pkg for mod, pkg in required.items() if not has_module(mod)})
if still_missing:
    print("ERROR_MISSING_MODULES:", ", ".join(still_missing))
    sys.exit(2)

print("MODULES_OK")
'@

python -c $moduleRepairScript
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Missing modules remain after auto-repair. Running full setup automatically..."
    $setupScript = Join-Path $repo "setup.ps1"
    if (Test-Path $setupScript) {
        try {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $setupScript
        } catch {
            Write-Warning "Setup encountered an error: $($_.Exception.Message)"
        }
    } else {
        Write-Warning "setup.ps1 not found; continuing launch with available modules."
    }
}

# Ensure Chrome remote debugging port is set
if (-not $env:CHROME_DEBUG_PORT) { $env:CHROME_DEBUG_PORT = "9222" }
Write-Host "Chrome DevTools port: $env:CHROME_DEBUG_PORT" -ForegroundColor Yellow

# Tip: start Chrome in debug mode if not already
$startChrome = Join-Path $repo "start-chrome-debug.ps1"
if (Test-Path $startChrome) {
    Write-Host "Tip: Run start-chrome-debug.ps1 to attach Selenium to Chrome." -ForegroundColor DarkGray
}

python "$repo\main.py"
