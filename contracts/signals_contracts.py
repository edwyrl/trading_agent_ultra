from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from contracts.enums import EvaluationMode, SignalRunStatus, SignalSourceType


class SignalDateRangeDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _validate_range(self) -> "SignalDateRangeDTO":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class SignalRunRequestDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_key: str = Field(min_length=1)
    date_range: SignalDateRangeDTO
    config: dict[str, Any] = Field(default_factory=dict)
    source_type: SignalSourceType = SignalSourceType.POSTGRES
    max_retries: int = Field(default=3, ge=0, le=20)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SignalRunStatusDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    signal_key: str
    source_type: SignalSourceType
    status: SignalRunStatus
    requested_start_date: date
    requested_end_date: date
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class SignalMetricPointDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_name: str
    metric_date: date
    metric_value: float
    payload: dict[str, Any] = Field(default_factory=dict)


class SignalEventDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_date: date
    event_type: str = "SIGNAL_EVENT"
    score: float | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SignalStatDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stat_group: str
    stat_name: str
    stat_value: float
    payload: dict[str, Any] = Field(default_factory=dict)


class SignalParamSweepPointDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sweep_name: str
    x_key: str
    x_value: float
    y_key: str
    y_value: float
    metric_name: str
    metric_value: float
    payload: dict[str, Any] = Field(default_factory=dict)


class SignalArtifactDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: str
    artifact_key: str
    uri: str
    content_type: str
    size_bytes: int = Field(ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class FactorValuePointDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_date: date
    ts_code: str
    factor_value: float
    payload: dict[str, Any] = Field(default_factory=dict)


class BacktestResultDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    engine: str
    summary: dict[str, Any] = Field(default_factory=dict)
    nav_series: list[dict[str, Any]] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class DashboardSeriesPointDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    value: float


class DashboardSeriesDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_name: str
    points: list[DashboardSeriesPointDTO] = Field(default_factory=list)


class DashboardOverviewDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_key: str
    source_type: SignalSourceType
    status: SignalRunStatus
    requested_start_date: date
    requested_end_date: date
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DashboardMetricCardDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_key: str
    label: str
    value: float
    unit: str = ""
    display: str = ""


class DashboardSectionDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_key: str
    title: str
    section_type: str
    eyebrow: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class DashboardTabDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tab_key: str
    label: str
    sections: list[DashboardSectionDTO] = Field(default_factory=list)


class DashboardPayloadDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run: SignalRunStatusDTO
    overview: DashboardOverviewDTO
    config_summary: dict[str, Any] = Field(default_factory=dict)
    key_metrics: list[DashboardMetricCardDTO] = Field(default_factory=list)
    tabs: list[DashboardTabDTO] = Field(default_factory=list)
    artifacts: list[SignalArtifactDTO] = Field(default_factory=list)


class SignalPluginMetaDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_key: str
    name: str
    description: str
    version: str
    config_schema: dict[str, Any] = Field(default_factory=dict)
    default_config: dict[str, Any] = Field(default_factory=dict)
    evaluation_modes: list[EvaluationMode] = Field(default_factory=lambda: [EvaluationMode.EVENT_STUDY])


class SignalExecutionOutputDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric_points: list[SignalMetricPointDTO] = Field(default_factory=list)
    events: list[SignalEventDTO] = Field(default_factory=list)
    stats: list[SignalStatDTO] = Field(default_factory=list)
    param_sweeps: list[SignalParamSweepPointDTO] = Field(default_factory=list)
    artifacts: list[SignalArtifactDTO] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
