"""
seed.py — Initialize Bill Core database tables and insert default data.

Safe to call multiple times (idempotent).
"""
import logging

from db import Base, engine, SessionLocal
from models_db import Tenant

logger = logging.getLogger(__name__)

DEFAULT_TENANT_ID = "default"
DEFAULT_TENANT_NAME = "Internal"


def init_db() -> None:
    """Create all tables (no-op if they already exist)."""
    Base.metadata.create_all(bind=engine)
    logger.info("DB tables created / verified OK (url=%s)", engine.url)


def seed_default_tenant() -> None:
    """Insert the internal default tenant if it doesn't exist yet."""
    with SessionLocal() as session:
        existing = session.get(Tenant, DEFAULT_TENANT_ID)
        if existing is None:
            session.add(
                Tenant(
                    id=DEFAULT_TENANT_ID,
                    name=DEFAULT_TENANT_NAME,
                    is_internal=True,
                )
            )
            session.commit()
            logger.info("Seeded default tenant: id=%s name=%s", DEFAULT_TENANT_ID, DEFAULT_TENANT_NAME)
        else:
            logger.debug("Default tenant already exists: id=%s", DEFAULT_TENANT_ID)


def run_seed() -> None:
    """Full seed sequence — call once at application startup."""
    init_db()
    seed_default_tenant()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_seed()
    print("Seed complete.")
