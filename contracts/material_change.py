from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts.enums import MaterialChangeLevel


class MaterialChangeDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_change: bool
    level: MaterialChangeLevel
    reasons: list[str] = Field(default_factory=list)
