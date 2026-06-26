"""
db.py — SQLAlchemy database foundation for Bill Core.

Uses SQLite by default (bill_core.db in the same directory as this file).
Override with env var BILL_CORE_DB_URL to use Postgres or any other DB.
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_db_dir = Path(__file__).resolve().parent

# Default: SQLite file next to this module. Override for Postgres etc.
DATABASE_URL: str = os.getenv(
    "BILL_CORE_DB_URL",
    f"sqlite:///{_db_dir / 'bill_core.db'}",
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
