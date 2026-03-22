from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from contracts.enums import EntityType
from contracts.material_change import MaterialChangeDTO
from contracts.source_refs import SourceRefDTO


class DeltaDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    delta_id: str
    entity_type: EntityType
    entity_id: str

    from_version: str
    to_version: str
    as_of_date: date

    changed_fields: list[str]
    summary: str
    reasons: list[str]
    impact_scope: list[str]

    material_change: MaterialChangeDTO
    source_refs: list[SourceRefDTO]

    created_at: datetime
