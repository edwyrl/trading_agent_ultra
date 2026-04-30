from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from contracts.enums import EvaluationMode
from contracts.signals_contracts import (
    DashboardMetricCardDTO,
    DashboardTabDTO,
    SignalArtifactDTO,
    SignalEventDTO,
    SignalMetricPointDTO,
    SignalParamSweepPointDTO,
    SignalPluginMetaDTO,
    SignalRunRequestDTO,
    SignalRunStatusDTO,
    SignalStatDTO,
)
from signals.services.market_data_provider import MarketDataProvider


@dataclass
class SignalPluginState:
    metrics: list[SignalMetricPointDTO] = field(default_factory=list)
    events: list[SignalEventDTO] = field(default_factory=list)
    stats: list[SignalStatDTO] = field(default_factory=list)
    param_sweeps: list[SignalParamSweepPointDTO] = field(default_factory=list)
    artifacts: list[SignalArtifactDTO] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    transient: dict[str, Any] = field(default_factory=dict)


class BaseSignalPlugin(ABC):
    signal_key: str

    @abstractmethod
    def meta(self) -> SignalPluginMetaDTO:
        raise NotImplementedError

    @abstractmethod
    def default_config(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def compute_metrics(
        self,
        *,
        run_id: str,
        provider: MarketDataProvider,
        start_date: date,
        end_date: date,
        config: dict[str, Any],
        state: SignalPluginState,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def detect_events(self, *, run_id: str, config: dict[str, Any], state: SignalPluginState) -> None:
        raise NotImplementedError

    @abstractmethod
    def evaluate(
        self,
        *,
        run: SignalRunRequestDTO,
        provider: MarketDataProvider,
        state: SignalPluginState,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def build_artifacts(self, *, run_id: str, config: dict[str, Any], state: SignalPluginState) -> None:
        raise NotImplementedError

    @abstractmethod
    def build_key_metrics(
        self,
        *,
        run: SignalRunStatusDTO,
        metrics: list[SignalMetricPointDTO],
        events: list[SignalEventDTO],
        stats: list[SignalStatDTO],
        sweeps: list[SignalParamSweepPointDTO],
    ) -> list[DashboardMetricCardDTO]:
        raise NotImplementedError

    @abstractmethod
    def build_dashboard_tabs(
        self,
        *,
        run: SignalRunStatusDTO,
        metrics: list[SignalMetricPointDTO],
        events: list[SignalEventDTO],
        stats: list[SignalStatDTO],
        sweeps: list[SignalParamSweepPointDTO],
    ) -> list[DashboardTabDTO]:
        raise NotImplementedError

    def evaluation_modes(self) -> list[EvaluationMode]:
        return [EvaluationMode.EVENT_STUDY]
