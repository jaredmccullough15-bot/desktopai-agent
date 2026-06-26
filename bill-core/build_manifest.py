"""
build_manifest.py — Generate build_manifest.json for bill-core deployments.

Run this before packaging:
    python build_manifest.py
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REQUIRED_FILES = [
    "main.py",
    "task_service.py",
    "conversational/__init__.py",
    "conversational/conversation_service.py",
    "requirements.txt",
    "Procfile",
]


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def main() -> None:
    required_files_present: dict[str, bool] = {}
    all_present = True
    for f in REQUIRED_FILES:
        exists = (ROOT / f).exists()
        required_files_present[f] = exists
        if not exists:
            all_present = False
            print(f"WARNING: required file missing: {f}")

    commit = _git_commit()

    manifest = {
        "app_name": "bill-core",
        "build_timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": commit,
        "python_version": sys.version,
        "required_files_present": required_files_present,
        "all_required_files_ok": all_present,
        "package_type": "backend",
    }

    out_path = ROOT / "build_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"build_manifest.json written: git_commit={commit} all_required_files_ok={all_present}")

    if not all_present:
        sys.exit(1)


if __name__ == "__main__":
    main()
