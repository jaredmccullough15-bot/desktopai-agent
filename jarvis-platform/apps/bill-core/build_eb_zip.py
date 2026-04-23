from __future__ import annotations

import os
import shutil
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CLEAN_DIR = BASE_DIR / "bill-core-deploy-clean"
ZIP_PATH = BASE_DIR / "bill-core-deploy.zip"

REQUIRED_ROOT_FILES = [
    "main.py",
    "Procfile",
    "requirements.txt",
    ".ebignore",
    "db.py",
    "models_db.py",
    "db_writes.py",
    "seed.py",
    "teach_session.py",
    "recovery.py",  # Phase 6: Human recovery system
]

REQUIRED_DIRS = [
    "app",
]

# Exclusions to keep deployment Linux/EB clean.
EXCLUDE_DIR_NAMES = {
    "__pycache__",
    ".venv",
    "logs",
}

EXCLUDE_FILE_NAMES = {
    "bill_core.db",
    ".env",
}

EXCLUDE_SUFFIXES = {
    ".pyc",
}


def should_exclude_file(path: Path) -> bool:
    if path.name in EXCLUDE_FILE_NAMES:
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    return False


def ensure_required_files_exist() -> None:
    missing: list[str] = []
    for file_name in REQUIRED_ROOT_FILES:
        src = BASE_DIR / file_name
        if not src.is_file():
            missing.append(file_name)

    for dir_name in REQUIRED_DIRS:
        src = BASE_DIR / dir_name
        if not src.is_dir():
            missing.append(f"{dir_name}/")

    if missing:
        raise FileNotFoundError(f"Missing required deployment paths: {', '.join(missing)}")


def rebuild_clean_folder() -> None:
    if CLEAN_DIR.exists():
        shutil.rmtree(CLEAN_DIR)
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)

    for file_name in REQUIRED_ROOT_FILES:
        src = BASE_DIR / file_name
        if should_exclude_file(src):
            continue
        shutil.copy2(src, CLEAN_DIR / file_name)

    for dir_name in REQUIRED_DIRS:
        src_dir = BASE_DIR / dir_name
        dst_dir = CLEAN_DIR / dir_name

        for root, dirs, files in os.walk(src_dir):
            root_path = Path(root)

            dirs[:] = [
                d for d in dirs
                if d not in EXCLUDE_DIR_NAMES
            ]

            rel_root = root_path.relative_to(src_dir)
            target_root = dst_dir / rel_root
            target_root.mkdir(parents=True, exist_ok=True)

            for file_name in files:
                src_file = root_path / file_name
                if should_exclude_file(src_file):
                    continue
                if any(part in EXCLUDE_DIR_NAMES for part in src_file.parts):
                    continue
                shutil.copy2(src_file, target_root / file_name)


def zip_folder(folder_path: Path, zip_path: Path) -> list[str]:
    entries: list[str] = []
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(folder_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIR_NAMES]
            for file in files:
                full_path = Path(root) / file
                rel_path = os.path.relpath(full_path, folder_path)
                zip_entry = rel_path.replace("\\", "/")
                z.write(full_path, zip_entry)
                entries.append(zip_entry)
    return sorted(entries)


def validate_requirements(path: Path) -> dict[str, bool]:
    content = path.read_text(encoding="utf-8")
    lowered = content.lower()
    return {
        "fastapi": "fastapi" in lowered,
        "uvicorn": "uvicorn" in lowered,
        "sqlalchemy": "sqlalchemy" in lowered,
        "python-multipart": "python-multipart" in lowered,
    }


def validate_zip(entries: list[str]) -> tuple[bool, bool, bool]:
    has_backslashes = any("\\" in entry for entry in entries)
    has_app_folder = any(entry == "app" or entry.startswith("app/") for entry in entries)

    # Root-layout check: no outer wrapper folder prefix like bill-core-deploy-clean/
    has_outer_folder = any(entry.startswith("bill-core-deploy-clean/") for entry in entries)

    return (not has_backslashes), has_app_folder, (not has_outer_folder)


def main() -> None:
    ensure_required_files_exist()

    dep_status = validate_requirements(BASE_DIR / "requirements.txt")

    rebuild_clean_folder()
    entries = zip_folder(CLEAN_DIR, ZIP_PATH)

    no_backslashes, has_app, root_layout_ok = validate_zip(entries)

    print("requirements_check:")
    for dep, present in dep_status.items():
        print(f"  - {dep}: {'OK' if present else 'MISSING'}")

    print("\nzip_path:")
    print(f"  {ZIP_PATH}")

    print("\nzip_entries:")
    for entry in entries:
        print(f"  - {entry}")

    print("\nvalidation:")
    print(f"  - root_files_no_outer_folder: {'OK' if root_layout_ok else 'FAIL'}")
    print(f"  - app_folder_present: {'OK' if has_app else 'FAIL'}")
    print(f"  - no_windows_backslashes: {'OK' if no_backslashes else 'FAIL'}")

    if not all(dep_status.values()):
        missing = [k for k, v in dep_status.items() if not v]
        raise SystemExit(f"Missing required dependencies in requirements.txt: {', '.join(missing)}")

    if not (no_backslashes and has_app and root_layout_ok):
        raise SystemExit("Zip validation failed; deployment bundle is not EB-compatible.")


if __name__ == "__main__":
    main()
