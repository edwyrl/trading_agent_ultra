from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from contracts.confidence import ConfidenceDTO
from contracts.delta import DeltaDTO
from contracts.enums import MacroBiasTag, MacroThemeType, MappingDirection
from contracts.material_change import MaterialChangeDTO
from contracts.source_refs import SourceRefDTO


class MacroIndustryMappingDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sw_l1_id: str
    sw_l1_name: str
    direction: MappingDirection
    score: float | None = None
    reason: str


class MacroThemeCardSummaryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_type: MacroThemeType
    as_of_date: date
    current_view: str
    latest_changes: list[str]
    drivers: list[str]
    risks: list[str]
    a_share_style_impact: str
    sw_l1_positive: list[str]
    sw_l1_negative: list[str]
    sw_l1_neutral: list[str]
    reasoning: str
    source_refs: list[SourceRefDTO]
    confidence: ConfidenceDTO


class MacroMasterCardDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    as_of_date: date
    created_at: datetime

    current_macro_bias: list[MacroBiasTag] = Field(min_length=1, max_length=3)
    macro_mainline: str
    key_changes: list[str]
    risk_opportunity_flags: list[str]
    a_share_style_impact: str

    sw_l1_positive: list[str]
    sw_l1_negative: list[str]
    sw_l1_neutral: list[str]

    reasoning: str
    source_refs: list[SourceRefDTO]
    confidence: ConfidenceDTO
    material_change: MaterialChangeDTO


class MacroConstraintsSummaryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    as_of_date: date
    current_macro_bias: list[MacroBiasTag] = Field(min_length=1, max_length=3)
    macro_mainline: str
    style_impact: str
    material_change: MaterialChangeDTO
    confidence: ConfidenceDTO


class MacroDeltaDTO(DeltaDTO):
    model_config = ConfigDict(extra="forbid")
