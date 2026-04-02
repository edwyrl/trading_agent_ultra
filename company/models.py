from __future__ import annotations

import uuid

from sqlalchemy import Date, DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.config import settings
from shared.db.base import Base
from shared.time_utils import utc_now

_SCHEMA = settings.database.schema_name


class CompanyContextSnapshotModel(Base):
    __tablename__ = "company_context_snapshots"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    version: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[Date] = mapped_column(Date, index=True)
    industry_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    macro_version_ref: Mapped[str] = mapped_column(String(64), index=True)
    industry_version_ref: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CompanyAnalysisRunModel(Base):
    __tablename__ = "company_analysis_runs"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    trade_date: Mapped[Date] = mapped_column(Date, index=True)
    context_version: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CompanyAnalystOutputModel(Base):
    __tablename__ = "company_analyst_outputs"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    ts_code: Mapped[str] = mapped_column(String(16), index=True)
    analyst_name: Mapped[str] = mapped_column(String(64), index=True)
    output_version: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
