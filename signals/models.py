from __future__ import annotations

import uuid

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.config import settings
from shared.db.base import Base
from shared.time_utils import utc_now

_SCHEMA = settings.database.schema_name


class SignalRunModel(Base):
    __tablename__ = "signal_runs"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    signal_key: Mapped[str] = mapped_column(String(64), index=True)
    source_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    requested_start_date: Mapped[Date] = mapped_column(Date, index=True)
    requested_end_date: Mapped[Date] = mapped_column(Date, index=True)
    config: Mapped[dict] = mapped_column(JSONB)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SignalJobQueueModel(Base):
    __tablename__ = "signal_job_queue"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SignalMetricTimeseriesModel(Base):
    __tablename__ = "signal_metric_timeseries"
    __table_args__ = (
        UniqueConstraint("run_id", "metric_name", "metric_date", name="uq_signal_metric_timeseries_run_metric_date"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    metric_name: Mapped[str] = mapped_column(String(64), index=True)
    metric_date: Mapped[Date] = mapped_column(Date, index=True)
    metric_value: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SignalEventModel(Base):
    __tablename__ = "signal_events"
    __table_args__ = (
        UniqueConstraint("run_id", "event_id", name="uq_signal_events_run_event"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(96), index=True)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    event_date: Mapped[Date] = mapped_column(Date, index=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SignalStatModel(Base):
    __tablename__ = "signal_stats"
    __table_args__ = (
        UniqueConstraint("run_id", "stat_group", "stat_name", name="uq_signal_stats_run_group_name"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    stat_group: Mapped[str] = mapped_column(String(64), index=True)
    stat_name: Mapped[str] = mapped_column(String(64), index=True)
    stat_value: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SignalParamSweepModel(Base):
    __tablename__ = "signal_param_sweeps"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "sweep_name",
            "x_key",
            "x_value",
            "y_key",
            "y_value",
            "metric_name",
            name="uq_signal_param_sweeps_run_grid_metric",
        ),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    sweep_name: Mapped[str] = mapped_column(String(64), index=True)
    x_key: Mapped[str] = mapped_column(String(64))
    x_value: Mapped[float] = mapped_column(Float)
    y_key: Mapped[str] = mapped_column(String(64))
    y_value: Mapped[float] = mapped_column(Float)
    metric_name: Mapped[str] = mapped_column(String(64))
    metric_value: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)


class SignalArtifactModel(Base):
    __tablename__ = "signal_artifacts"
    __table_args__ = (
        UniqueConstraint("run_id", "artifact_key", name="uq_signal_artifacts_run_key"),
        {"schema": _SCHEMA},
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[str] = mapped_column(String(64), index=True)
    artifact_type: Mapped[str] = mapped_column(String(32), index=True)
    artifact_key: Mapped[str] = mapped_column(String(64), index=True)
    uri: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
