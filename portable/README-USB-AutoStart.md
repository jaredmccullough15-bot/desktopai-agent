# USB Auto-Start (Windows)

Windows disables automatic execution from USB drives for security. True auto-run (plug and it starts) is not supported on modern Windows for USB media.

This folder provides the best-possible alternatives:

- `autorun.inf`: Helps AutoPlay show a "Run setup.exe" action if a `setup.exe` exists at the drive root (works on some configurations).
- `setup-launcher.cmd`: One-click launcher to run `desktop-ai-agent\setup.ps1` from the USB root.
- `usb_setup_launcher.py`: Optional Python stub you can build into `setup.exe` for a cleaner AutoPlay experience.

## Recommended Flow

1. Copy contents:
   - Place `autorun.inf` and your built `setup.exe` at the **USB drive root** (e.g., `E:\`).
   - Copy the entire `desktop-ai-agent` folder to `E:\desktop-ai-agent`.

2. Build `setup.exe` (optional but recommended for AutoPlay):

```powershell
# From project root
python -m pip install pyinstaller
pyinstaller --onefile portable/usb_setup_launcher.py -n setup
# Copy dist\setup.exe to USB drive root
```

3. On the target PC:
   - Insert the USB drive.
   - If AutoPlay prompts: choose "Run setup.exe".
   - If no prompt: open the drive and double-click `setup.exe` (or `setup-launcher.cmd`).

## What the setup does

- Creates/activates a virtual environment on the target machine.
- Installs dependencies via `requirements.txt`.
- Attempts PyAudio install; falls back to known wheel.

## Notes

- Full hands-free auto-run is intentionally blocked on Windows for USB.
- Using `setup.exe` increases the chance AutoPlay offers a "Run" option.
- You can still manually run `setup-launcher.cmd` if AutoPlay does not show the option.
