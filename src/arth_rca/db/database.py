"""
PostgreSQL Database configuration, engine factory, and session management.
"""

import os
from typing import Generator, Optional
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.engine import Engine

DEFAULT_POSTGRES_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/arth_rca"


def get_database_url() -> str:
    """Return database URL from environment or default."""
    return os.environ.get("DATABASE_URL", DEFAULT_POSTGRES_URL)


def create_db_engine(db_url: Optional[str] = None, echo: bool = False) -> Engine:
    """Create SQLAlchemy engine."""
    url = db_url or get_database_url()
    connect_args = {}
    if "sqlite" in url:
        connect_args["check_same_thread"] = False
    return create_engine(url, echo=echo, connect_args=connect_args)


default_engine = create_db_engine()
SessionLocal = lambda: Session(default_engine)


def init_db(engine: Optional[Engine] = None) -> None:
    """Create all tables in the database if they do not exist."""
    eng = engine or default_engine
    SQLModel.metadata.create_all(eng)


def get_session(engine: Optional[Engine] = None) -> Generator[Session, None, None]:
    """Yield database session."""
    eng = engine or default_engine
    with Session(eng) as session:
        yield session


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for database session."""
    with Session(default_engine) as session:
        yield session
