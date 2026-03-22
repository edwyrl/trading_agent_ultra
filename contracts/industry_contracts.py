from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from contracts.confidence import ConfidenceDTO
from contracts.delta import DeltaDTO
from contracts.enums import IndustryScenarioBias, SwLevel
from contracts.source_refs import SourceRefDTO


class IndustryRefDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry_id: str
    industry_name: str
    sw_level: SwLevel


class IndustryThesisSummaryDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    as_of_date: date

    industry_id: str
    industry_name: str
    sw_level: SwLevel

    current_bias: IndustryScenarioBias
    bull_base_bear_summary: str
    key_drivers: list[str]
    key_risks: list[str]
    company_fit_questions: list[str]

    confidence: ConfidenceDTO


class IndustryThesisCardDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    as_of_date: date
    created_at: datetime

    industry_id: str
    industry_name: str
    sw_level: SwLevel

    last_news_update_at: datetime | None = None
    last_market_data_update_at: datetime | None = None
    last_full_refresh_at: datetime | None = None

    definition: str
    value_chain: str
    core_drivers: list[str]
    core_conflicts: list[str]

    bull_case: str
    base_case: str
    bear_case: str

    current_bias: IndustryScenarioBias
    bias_reason: str
    bias_shift_risk: list[str]

    key_metrics_to_watch: list[str]
    companies_to_watch: list[str]
    latest_changes: list[str]

    confidence: ConfidenceDTO
    source_refs: list[SourceRefDTO]
    concept_tags: list[str]


class IndustryDeltaDTO(DeltaDTO):
    model_config = ConfigDict(extra="forbid")
