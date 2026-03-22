from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import ConfidenceLevel


class ConfidenceDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: float = Field(ge=0.0, le=1.0)
    level: ConfidenceLevel
    note: str | None = None
