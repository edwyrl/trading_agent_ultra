"""Initialize v1 thesis storage schema.

Revision ID: 20260322_0001
Revises:
Create Date: 2026-03-22 12:00:00
"""

from __future__ import annotations

import os

from alembic import op

from shared.db.base import Base

# Ensure all ORM models are imported before metadata create.
import company.models  # noqa: F401
import industry.models  # noqa: F401
import integration.models  # noqa: F401
import macro.models  # noqa: F401

# revision identifiers, used by Alembic.
revision = "20260322_0001"
down_revision = None
branch_labels = None
depends_on = None


def _schema() -> str:
    return os.getenv("SUPABASE_SCHEMA", "thesis")


def upgrade() -> None:
    schema = _schema()
    op.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
    bind = op.get_bind()
    bind.exec_driver_sql(f'SET search_path TO "{schema}", public')
    Base.metadata.create_all(bind=bind, checkfirst=True)


def downgrade() -> None:
    schema = _schema()
    bind = op.get_bind()
    bind.exec_driver_sql(f'SET search_path TO "{schema}", public')
    Base.metadata.drop_all(bind=bind, checkfirst=True)
    op.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
