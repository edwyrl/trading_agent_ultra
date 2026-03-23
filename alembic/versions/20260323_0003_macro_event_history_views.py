"""Add macro event history and event views tables.

Revision ID: 20260323_0003
Revises: 20260322_0002
Create Date: 2026-03-23 11:00:00
"""

from __future__ import annotations

import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260323_0003"
down_revision = "20260322_0002"
branch_labels = None
depends_on = None


def _schema() -> str:
    return os.getenv("SUPABASE_SCHEMA", "thesis")


def upgrade() -> None:
    schema = _schema()

    op.create_table(
        "macro_event_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("history_id", sa.String(length=96), nullable=False),
        sa.Column("event_id", sa.String(length=96), nullable=False),
        sa.Column("event_seq", sa.Integer(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("event_status", sa.String(length=32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("fact_summary", sa.Text(), nullable=False),
        sa.Column("theme_type", sa.String(length=64), nullable=False),
        sa.Column("bias_hint", sa.String(length=64), nullable=True),
        sa.Column("source_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("history_id", name="uq_macro_event_history_history_id"),
        sa.UniqueConstraint("event_id", "event_seq", name="uq_macro_event_history_event_seq"),
        schema=schema,
    )
    op.create_index(
        "ix_macro_event_history_event_id",
        "macro_event_history",
        ["event_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_macro_event_history_as_of_date",
        "macro_event_history",
        ["as_of_date"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_macro_event_history_theme_type",
        "macro_event_history",
        ["theme_type"],
        unique=False,
        schema=schema,
    )

    op.create_table(
        "macro_event_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("view_id", sa.String(length=96), nullable=False),
        sa.Column("event_id", sa.String(length=96), nullable=False),
        sa.Column("history_id", sa.String(length=96), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("view_type", sa.String(length=32), nullable=False),
        sa.Column("stance", sa.String(length=16), nullable=False),
        sa.Column("view_text", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("score_reason", sa.Text(), nullable=True),
        sa.Column("source_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("view_id", name="uq_macro_event_views_view_id"),
        schema=schema,
    )
    op.create_index(
        "ix_macro_event_views_event_id",
        "macro_event_views",
        ["event_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_macro_event_views_history_id",
        "macro_event_views",
        ["history_id"],
        unique=False,
        schema=schema,
    )
    op.create_index(
        "ix_macro_event_views_as_of_date",
        "macro_event_views",
        ["as_of_date"],
        unique=False,
        schema=schema,
    )


def downgrade() -> None:
    schema = _schema()

    op.drop_index("ix_macro_event_views_as_of_date", table_name="macro_event_views", schema=schema)
    op.drop_index("ix_macro_event_views_history_id", table_name="macro_event_views", schema=schema)
    op.drop_index("ix_macro_event_views_event_id", table_name="macro_event_views", schema=schema)
    op.drop_table("macro_event_views", schema=schema)

    op.drop_index("ix_macro_event_history_theme_type", table_name="macro_event_history", schema=schema)
    op.drop_index("ix_macro_event_history_as_of_date", table_name="macro_event_history", schema=schema)
    op.drop_index("ix_macro_event_history_event_id", table_name="macro_event_history", schema=schema)
    op.drop_table("macro_event_history", schema=schema)
