"""
verify_deploy_package.py — Verify the contents of bill-core-deploy.zip before deployment.

Run from the bill-core directory:
    python verify_deploy_package.py

Looks for ../bill-core-deploy.zip relative to this script.
Exits 1 if any required file is missing.
"""
import sys
import zipfile
from pathlib import Path

REQUIRED_FILES = [
    "main.py",
    "teaching_copilot_service.py",
    "schemas.py",
    "structured_logging.py",
    "task_service.py",
    "conversational/__init__.py",
    "conversational/conversation_service.py",
    "requirements.txt",
    "Procfile",
]

ROOT = Path(__file__).resolve().parent
ZIP_PATH = ROOT.parent / "bill-core-deploy.zip"

# Also accept a zip in the same directory (build-deploy.ps1 copies it there).
if not ZIP_PATH.exists():
    ZIP_PATH = ROOT / "bill-core-deploy.zip"


def main() -> None:
    if not ZIP_PATH.exists():
        print(f"ERROR: deploy zip not found at {ZIP_PATH}")
        sys.exit(1)

    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        names = set(zf.namelist())

    missing: list[str] = []
    for f in REQUIRED_FILES:
        if f not in names:
            print(f"Missing: {f}")
            missing.append(f)
        else:
            print(f"OK: {f}")

    if missing:
        print(f"\nDEPLOY_PACKAGE_FAIL — {len(missing)} required file(s) missing from {ZIP_PATH.name}")
        sys.exit(1)

    print(f"\nDEPLOY_PACKAGE_OK — all required files present in {ZIP_PATH.name}")


if __name__ == "__main__":
    main()
