"""
SYSTEM DESIGN CONCEPT: Database Configuration & Connection Management
Here we set up the database engine and session factory.
By creating a generic `get_session()` method or a `Database` class, we decouple our application
from the specific database implementation (SQLite in this case).
"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

import os

from api.core import config  # noqa: F401  (loads .env)

# 1. ENCAPSULATION: We hide the connection details inside this module.
if os.getenv("DATABASE_URL"):
    # Explicit override (used by tests)
    DATABASE_URL = os.getenv("DATABASE_URL")
    engine = create_engine(DATABASE_URL, echo=False)
elif os.getenv("POSTGRES_URL"):
    # Vercel/Neon Postgres provides postgres:// but SQLAlchemy needs postgresql://
    DATABASE_URL = os.getenv("POSTGRES_URL").replace("postgres://", "postgresql://", 1)
    # Remove channel_binding param if present (not supported by psycopg2)
    if "channel_binding" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("&channel_binding=require", "").replace("?channel_binding=require&", "?").replace("?channel_binding=require", "")
    engine = create_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
elif os.getenv("VERCEL"):
    DATABASE_URL = "sqlite:////tmp/notifications.db"
    engine = create_engine(DATABASE_URL, echo=False)
else:
    DATABASE_URL = "sqlite:///notifications.db"
    engine = create_engine(DATABASE_URL, echo=False)

# SessionLocal will be used to create isolated database sessions for each transaction.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all our database models (Inheritance will be used here)
Base = declarative_base()

# Columns added after the first deploy. create_all() never alters existing tables,
# so we add missing columns ourselves (works on both SQLite and Postgres).
_ADDED_COLUMNS = {
    "notification_logs": {
        "slug": "VARCHAR(200)",
        "difficulty": "VARCHAR(20)",
        "link": "VARCHAR(500)",
        "topic": "VARCHAR(200)",
        "completed_at": "TIMESTAMP",
    },
}


def _migrate():
    insp = inspect(engine)
    with engine.begin() as conn:
        for table, cols in _ADDED_COLUMNS.items():
            if not insp.has_table(table):
                continue
            existing = {c["name"] for c in insp.get_columns(table)}
            for name, ddl in cols.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def init_db():
    """Creates the database tables based on our models."""
    import api.domain.models  # noqa: F401  (register models on Base)
    Base.metadata.create_all(bind=engine)
    _migrate()


def get_db():
    """
    Provides a transactional scope around a series of operations.
    Used for Dependency Injection into our Repositories.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
