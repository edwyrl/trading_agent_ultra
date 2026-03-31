from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class ResearchStage(StrEnum):
    PREPARE = "prepare"
    PLAN = "plan"
    RESEARCH = "research"
    ANALYZE = "analyze"
    SUMMARIZE = "summarize"
    FINAL_REPORT = "final_report"
    COMPLETED = "completed"
    FAILED = "failed"


class StreamingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=lambda: uuid4().hex)
    run_id: str
    stage: ResearchStage
    event_type: str = "status"
    message: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
