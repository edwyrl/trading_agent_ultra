from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from shared.config import settings


def create_db_engine() -> Engine:
    # Supabase transaction pooler (pgBouncer) is incompatible with psycopg auto prepared statements.
    # Disable server-side prepare to avoid DuplicatePreparedStatement errors.
    return create_engine(
        settings.database.db_url,
        pool_pre_ping=True,
        connect_args={"prepare_threshold": None},
    )


engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
