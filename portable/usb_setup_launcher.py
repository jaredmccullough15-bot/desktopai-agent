import subprocess
import sys
import os


def main():
    # Resolve base directory (EXE location or script directory)
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))

    # Preferred layout: <USB_ROOT>/desktop-ai-agent/setup.ps1
    candidates = [
        os.path.join(base, 'desktop-ai-agent', 'setup.ps1'),
        os.path.join(base, 'setup.ps1'),  # if exe is inside desktop-ai-agent
    ]

    ps1 = None
    for c in candidates:
        if os.path.exists(c):
            ps1 = c
            break

    # Fallback: search for setup.ps1 nearby
    if ps1 is None:
        try:
            for root, dirs, files in os.walk(base):
                if 'setup.ps1' in files:
                    ps1 = os.path.join(root, 'setup.ps1')
                    break
        except Exception:
            ps1 = None

    if ps1 is None:
        print("Setup script not found.")
        print("Expected USB layout:")
        print("  - Root: setup.exe, autorun.inf")
        print("  - Folder: desktop-ai-agent\\setup.ps1 (and project files)")
        print("Tip: Place 'setup-launcher.cmd' at USB root and run that, or open desktop-ai-agent\\setup.ps1 in PowerShell.")
        sys.exit(1)

    cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', ps1]
    try:
        subprocess.run(cmd, cwd=os.path.dirname(ps1), check=True)
    except subprocess.CalledProcessError as e:
        print("Setup failed:", e)
        sys.exit(e.returncode)


if __name__ == '__main__':
    main()
