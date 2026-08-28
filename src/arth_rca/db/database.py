"""
PostgreSQL Database configuration, engine factory, and session management.
"""

import os
from typing import Generator, Optional
from sqlmodel import SQLModel, create_engine, Session
from sqlalchemy.engine import Engine

from sqlalchemy.pool import NullPool, QueuePool

DEFAULT_SQLITE_URL = "sqlite:///arth_rca.db"


def get_database_url() -> str:
    """
    Return database URL from DATABASE_URL environment variable,
    defaulting to local SQLite file 'arth_rca.db' in the project workspace.
    """
    return os.environ.get("DATABASE_URL", DEFAULT_SQLITE_URL)


def create_db_engine(db_url: Optional[str] = None, echo: bool = False) -> Engine:
    """Create SQLAlchemy engine with appropriate dialect arguments."""
    url = db_url or get_database_url()
    connect_args = {}
    if "sqlite" in url:
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 30.0
        return create_engine(url, echo=echo, connect_args=connect_args, poolclass=NullPool)
    else:
        return create_engine(
            url,
            echo=echo,
            connect_args=connect_args,
            pool_size=20,
            max_overflow=40,
            pool_timeout=60.0,
            pool_recycle=1800,
        )


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
