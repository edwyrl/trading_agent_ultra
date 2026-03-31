from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class AgentRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NOT_IMPLEMENTED = "not_implemented"


class AgentRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(default_factory=lambda: uuid4().hex)
    prompt: str
    role: str = "research"
    model_id: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    status: AgentRunStatus
    role: str
    model_id: str
    summary: str = ""
    artifacts: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None


class AgentComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    left: AgentRunRequest
    right: AgentRunRequest
