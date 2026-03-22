from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from contracts.confidence import ConfidenceDTO
from contracts.enums import IndustryScenarioBias, MappingDirection, MacroBiasTag, SwLevel
from contracts.material_change import MaterialChangeDTO
from contracts.source_refs import SourceRefDTO


class VersionRefDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    as_of_date: date


class DataRefDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ref_id: str
    as_of_date: date
    updated_at: datetime


class MetricValueDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: float | int | str | None
    explanation: str | None = None


class HighlightFlagDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    message: str
    severity: str = "INFO"


class ComputedMetricsDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technical_metrics: dict[str, MetricValueDTO]
    valuation_metrics: dict[str, MetricValueDTO]
    financial_quality_metrics: dict[str, MetricValueDTO]
    risk_metrics: dict[str, MetricValueDTO]
    highlight_flags: list[HighlightFlagDTO] = Field(default_factory=list, max_length=5)


class IndustryMappingSignalForCompanyDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sw_l1_id: str
    direction: MappingDirection
    reason: str


class MacroConstraintsForCompanyDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    macro_biases: list[MacroBiasTag] = Field(min_length=1, max_length=3)
    macro_mainline: str
    style_impact: str
    industry_mapping_signal_for_company: IndustryMappingSignalForCompanyDTO
    material_change: MaterialChangeDTO
    reasoning_summary: str
    confidence: ConfidenceDTO


class IndustryThesisForCompanyDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    industry_level_used: SwLevel
    current_bias: IndustryScenarioBias
    bull_base_bear_summary: str
    key_drivers: list[str]
    key_risks: list[str]
    company_fit_questions: list[str]
    confidence: ConfidenceDTO


class CompanyContextDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str
    context_version: str

    ts_code: str
    company_name: str
    trade_date: date

    sw_l1_name: str | None = None
    sw_l2_name: str | None = None
    sw_l3_name: str | None = None
    sw_l1_id: str | None = None
    sw_l2_id: str | None = None
    sw_l3_id: str | None = None
    primary_industry_level: SwLevel
    concept_tags: list[str] = Field(default_factory=list, max_length=10)

    as_of_date: date
    context_as_of_date: date

    market_data_ref: DataRefDTO
    financial_data_ref: DataRefDTO
    news_data_ref: DataRefDTO

    computed_metrics: ComputedMetricsDTO
    macro_constraints_summary: MacroConstraintsForCompanyDTO
    industry_thesis_summary: IndustryThesisForCompanyDTO

    macro_context_ref: VersionRefDTO
    industry_thesis_ref: VersionRefDTO

    source_refs: list[SourceRefDTO] = Field(default_factory=list)
