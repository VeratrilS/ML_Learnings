"""
SYSTEM DESIGN CONCEPT: Database Configuration & Connection Management
Here we set up the database engine and session factory. 
By creating a generic `get_session()` method or a `Database` class, we decouple our application 
from the specific database implementation (SQLite in this case). 
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

import os

# 1. ENCAPSULATION: We hide the connection details inside this module.
if os.getenv("POSTGRES_URL"):
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

def init_db():
    """Creates the database tables based on our models."""
    Base.metadata.create_all(bind=engine)

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
