from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from shared.config import settings


def ensure_schema(session: Session) -> None:
    schema = settings.supabase_schema
    session.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
    session.execute(text(f'SET search_path TO "{schema}", public'))
