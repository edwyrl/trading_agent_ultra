from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Date, DateTime, Float, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.config import settings
from shared.db.base import Base
from shared.time_utils import utc_now

_SCHEMA = settings.supabase_schema


class MacroMasterSnapshotModel(Base):
    __tablename__ = "macro_master_snapshots"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    as_of_date: Mapped[Date] = mapped_column(Date, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
    current_macro_bias: Mapped[list[str]] = mapped_column(JSONB)
    macro_mainline: Mapped[str] = mapped_column(Text)
    reasoning: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[float] = mapped_column(Float)
    material_change: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict] = mapped_column(JSONB)


class MacroThemeSnapshotModel(Base):
    __tablename__ = "macro_theme_snapshots"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(64), index=True)
    theme_type: Mapped[str] = mapped_column(String(64), index=True)
    as_of_date: Mapped[Date] = mapped_column(Date, index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
    payload: Mapped[dict] = mapped_column(JSONB)


class MacroDeltaModel(Base):
    __tablename__ = "macro_deltas"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delta_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), index=True)
    from_version: Mapped[str] = mapped_column(String(64))
    to_version: Mapped[str] = mapped_column(String(64), index=True)
    as_of_date: Mapped[Date] = mapped_column(Date, index=True)
    material_change: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
    payload: Mapped[dict] = mapped_column(JSONB)


class MacroIndustryMappingSnapshotModel(Base):
    __tablename__ = "macro_industry_mapping_snapshots"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(64), index=True)
    as_of_date: Mapped[Date] = mapped_column(Date, index=True)
    sw_l1_id: Mapped[str] = mapped_column(String(32), index=True)
    sw_l1_name: Mapped[str] = mapped_column(String(64))
    direction: Mapped[str] = mapped_column(String(16), index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class MacroRunLogModel(Base):
    __tablename__ = "macro_run_logs"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    as_of_date: Mapped[Date] = mapped_column(Date, index=True)
    event_count: Mapped[int] = mapped_column()
    changed_theme_count: Mapped[int] = mapped_column()
    material_change: Mapped[bool] = mapped_column(Boolean)
    status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
