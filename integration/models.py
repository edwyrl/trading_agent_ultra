from __future__ import annotations

import uuid

from sqlalchemy import DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.config import settings
from shared.db.base import Base
from shared.time_utils import utc_now

_SCHEMA = settings.supabase_schema


class IndustryRecheckQueueModel(Base):
    __tablename__ = "industry_recheck_queue"
    __table_args__ = {"schema": _SCHEMA}

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    queue_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    sw_l1_id: Mapped[str] = mapped_column(String(32), index=True)
    industry_id: Mapped[str] = mapped_column(String(32), index=True)
    recommended_mode: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    reason_codes: Mapped[list[str]] = mapped_column(JSONB)
    triggered_by_macro_version: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), default=utc_now)
