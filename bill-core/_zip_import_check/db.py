"""
db.py — SQLAlchemy database foundation for Bill Core.

Uses SQLite by default (bill_core.db in the same directory as this file).
Override with env var BILL_CORE_DB_URL to use Postgres or any other DB.
"""
import logging
import os
import shutil
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_db_dir = Path(__file__).resolve().parent
logger = logging.getLogger("bill-core")


def _path_is_writable_or_creatable(path: Path) -> bool:
    if path.exists():
        return os.access(path, os.W_OK)
    for ancestor in (path, *path.parents):
        if ancestor.exists():
            return os.access(ancestor, os.W_OK)
    return False


def _default_data_root() -> Path:
    configured = (os.getenv("BILL_CORE_DATA_DIR") or "").strip()
    if configured:
        configured_path = Path(configured)
        if _path_is_writable_or_creatable(configured_path):
            return configured_path
        logger.warning(
            "BILL_CORE_DATA_DIR is not writable for database path (%s); falling back to app-local data root",
            configured_path,
        )
    return _db_dir / ".data"


_data_root = _default_data_root()
_default_db_path = _data_root / "bill_core.db"
_legacy_db_path = _db_dir / "bill_core.db"

if not os.getenv("BILL_CORE_DB_URL"):
    if _default_db_path != _legacy_db_path and (not _default_db_path.exists()) and _legacy_db_path.exists():
        try:
            _default_db_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(_legacy_db_path, _default_db_path)
        except PermissionError as error:
            logger.warning(
                "Skipping legacy DB migration due to permission error: %s -> %s (%s)",
                _legacy_db_path,
                _default_db_path,
                error,
            )

# Default: SQLite file next to this module. Override for Postgres etc.
DATABASE_URL: str = os.getenv(
    "BILL_CORE_DB_URL",
    f"sqlite:///{_default_db_path}",
)

# SQLite needs check_same_thread=False when used from multiple threads (FastAPI).
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    echo=False,  # set to True for SQL query logging during development
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass
