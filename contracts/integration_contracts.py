from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from contracts.enums import MappingDirection, UpdateMode


class MacroIndustryConstraintDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sw_l1_id: str
    constraint_direction: MappingDirection
    constraint_reason: str
    macro_version_ref: str


class IndustryRecheckDecisionDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sw_l1_id: str
    recheck_required: bool
    recommended_mode: UpdateMode | None = None
    reason_codes: list[str]
    triggered_by_macro_version: str


class RecheckQueueItemDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    queue_id: str
    sw_l1_id: str
    industry_id: str
    recommended_mode: UpdateMode
    status: str
    created_at: datetime
