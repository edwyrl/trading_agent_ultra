from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.config import settings
from shared.db.base import Base
from shared.time_utils import utc_now

_SCHEMA = settings.database.schema_name


class IndustryThesisSnapshotModel(Base):
    __tablename__ = "industry_thesis_snapshots"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    industry_id: Mapped[str] = mapped_column(String(32), index=True)
    industry_name: Mapped[str] = mapped_column(String(128))
    sw_level: Mapped[str] = mapped_column(String(8), index=True)
    as_of_date: Mapped[Date] = mapped_column(Date, index=True)
    current_bias: Mapped[str] = mapped_column(String(16), index=True)
    confidence_score: Mapped[float] = mapped_column()
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IndustryThesisLatestModel(Base):
    __tablename__ = "industry_thesis_latest"
    __table_args__ = {"schema": _SCHEMA}

    industry_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    sw_level: Mapped[str] = mapped_column(String(8), primary_key=True)
    latest_version: Mapped[str] = mapped_column(String(64), index=True)
    as_of_date: Mapped[Date] = mapped_column(Date)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IndustryDeltaModel(Base):
    __tablename__ = "industry_deltas"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    delta_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    industry_id: Mapped[str] = mapped_column(String(32), index=True)
    from_version: Mapped[str] = mapped_column(String(64))
    to_version: Mapped[str] = mapped_column(String(64), index=True)
    as_of_date: Mapped[Date] = mapped_column(Date, index=True)
    material_change: Mapped[bool] = mapped_column(Boolean)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IndustryWeeklyRefreshCandidateModel(Base):
    __tablename__ = "industry_weekly_refresh_candidates"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    week_key: Mapped[str] = mapped_column(String(16), index=True)
    industry_id: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[float] = mapped_column()
    score_breakdown: Mapped[dict] = mapped_column(JSONB)
    selected: Mapped[bool] = mapped_column(Boolean, default=False)
    rank_order: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class IndustryWeeklyRefreshRunModel(Base):
    __tablename__ = "industry_weekly_refresh_runs"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    week_key: Mapped[str] = mapped_column(String(16), index=True)
    candidate_count: Mapped[int] = mapped_column()
    refreshed_count: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
