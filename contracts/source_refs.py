from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import SourceType


class SourceRefDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: SourceType
    title: str = Field(min_length=1)
    retrieved_at: datetime

    source_id: str | None = None
    url: str | None = None
    published_at: datetime | None = None
    provider: str | None = None
    lang: str | None = "zh-CN"
    note: str | None = None
