"""Add status tracking columns to industry_recheck_queue.

Revision ID: 20260322_0002
Revises: 20260322_0001
Create Date: 2026-03-22 18:35:00
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260322_0002"
down_revision = "20260322_0001"
branch_labels = None
depends_on = None


def _schema() -> str:
    return os.getenv("SUPABASE_SCHEMA", "thesis")


def upgrade() -> None:
    schema = _schema()
    op.add_column(
        "industry_recheck_queue",
        sa.Column("note", sa.Text(), nullable=True),
        schema=schema,
    )
    op.add_column(
        "industry_recheck_queue",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        schema=schema,
    )
    op.execute(sa.text(f'UPDATE "{schema}".industry_recheck_queue SET updated_at = now() WHERE updated_at IS NULL'))
    op.alter_column("industry_recheck_queue", "updated_at", nullable=False, schema=schema)


def downgrade() -> None:
    schema = _schema()
    op.drop_column("industry_recheck_queue", "updated_at", schema=schema)
    op.drop_column("industry_recheck_queue", "note", schema=schema)
