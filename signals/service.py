from __future__ import annotations

from datetime import UTC, datetime
from typing import Callable
from uuid import uuid4

from contracts.enums import SignalRunStatus, SignalSourceType
from contracts.signals_contracts import (
    DashboardMetricCardDTO,
    DashboardOverviewDTO,
    DashboardPayloadDTO,
    SignalArtifactDTO,
    SignalDateRangeDTO,
    SignalPluginMetaDTO,
    SignalRunRequestDTO,
    SignalRunStatusDTO,
)
from signals.plugins.base import SignalPluginState
from signals.plugins.registry import SignalRegistry
from signals.repository import SignalRepository
from signals.services.market_data_provider import MarketDataProvider


class RunCancelledError(RuntimeError):
    pass


class SignalDashboardAssembler:
    def build(
        self,
        *,
        plugin,
        run: SignalRunStatusDTO,
        metrics,
        events,
        stats,
        sweeps,
        artifacts: list[SignalArtifactDTO],
    ) -> DashboardPayloadDTO:
        config_summary = {
            "signal_key": run.signal_key,
            "source_type": run.source_type.value,
            "date_range": {
                "start_date": run.requested_start_date.isoformat(),
                "end_date": run.requested_end_date.isoformat(),
            },
            "config": run.config,
        }

        return DashboardPayloadDTO(
            run=run,
            overview=DashboardOverviewDTO(
                signal_key=run.signal_key,
                source_type=run.source_type,
                status=run.status,
                requested_start_date=run.requested_start_date,
                requested_end_date=run.requested_end_date,
                created_at=run.created_at,
                updated_at=run.updated_at,
                started_at=run.started_at,
                finished_at=run.finished_at,
            ),
            config_summary=config_summary,
            key_metrics=plugin.build_key_metrics(run=run, metrics=metrics, events=events, stats=stats, sweeps=sweeps),
            tabs=plugin.build_dashboard_tabs(run=run, metrics=metrics, events=events, stats=stats, sweeps=sweeps),
            artifacts=artifacts,
        )


class SignalResearchService:
    def __init__(
        self,
        *,
        repository: SignalRepository,
        provider_factory: Callable[[SignalSourceType], MarketDataProvider],
        registry: SignalRegistry,
        dashboard_assembler: SignalDashboardAssembler | None = None,
    ):
        self.repository = repository
        self.provider_factory = provider_factory
        self.registry = registry
        self.dashboard_assembler = dashboard_assembler or SignalDashboardAssembler()

    def submit_run(self, request: SignalRunRequestDTO) -> SignalRunStatusDTO:
        run_id = f"signal-run:{uuid4().hex}"
        plugin = self.registry.get(request.signal_key)
        validated = plugin.validate_config(request.config)
        normalized_request = SignalRunRequestDTO(
            signal_key=request.signal_key,
            date_range=request.date_range,
            config=validated,
            source_type=request.source_type,
            max_retries=request.max_retries,
            metadata=request.metadata,
        )
        return self.repository.create_run_and_enqueue(run_id=run_id, request=normalized_request)

    def list_runs(self, *, status: SignalRunStatus | None = None, limit: int = 50, offset: int = 0) -> list[SignalRunStatusDTO]:
        return self.repository.list_runs(status=status, limit=limit, offset=offset)

    def get_run(self, run_id: str) -> SignalRunStatusDTO | None:
        return self.repository.get_run(run_id)

    def list_plugins(self) -> list[SignalPluginMetaDTO]:
        return [plugin.meta() for plugin in self.registry.list_plugins()]

    def list_artifacts(self, run_id: str) -> list[SignalArtifactDTO]:
        return self.repository.list_artifacts(run_id=run_id)

    def cancel_run(self, run_id: str, *, reason: str = "Canceled by user.") -> SignalRunStatusDTO:
        return self.repository.cancel_run(run_id=run_id, reason=reason)

    def delete_run(self, run_id: str) -> bool:
        return self.repository.delete_run(run_id=run_id)

    def requeue_stale_jobs(self, *, timeout_seconds: float) -> int:
        return self.repository.requeue_stale_jobs(timeout_seconds=timeout_seconds)

    def get_dashboard(self, run_id: str) -> DashboardPayloadDTO:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        plugin = self.registry.get(run.signal_key)
        return self.dashboard_assembler.build(
            plugin=plugin,
            run=run,
            metrics=self.repository.list_metrics(run_id=run_id),
            events=self.repository.list_events(run_id=run_id),
            stats=self.repository.list_stats(run_id=run_id),
            sweeps=self.repository.list_param_sweeps(run_id=run_id),
            artifacts=self.repository.list_artifacts(run_id=run_id),
        )

    def execute_next_job(self, *, worker_id: str) -> SignalRunStatusDTO | None:
        claimed = self.claim_next_job(worker_id=worker_id)
        if claimed is None:
            return None
        return self.execute_run(run_id=claimed.run_id, mark_running=False)

    def claim_next_job(self, *, worker_id: str) -> SignalRunStatusDTO | None:
        run_id = self.repository.get_pending_job(worker_id=worker_id)
        if run_id is None:
            return None
        self.repository.mark_run_running(run_id=run_id)
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"run not found after claim: {run_id}")
        return run

    def execute_run(self, *, run_id: str, mark_running: bool = True) -> SignalRunStatusDTO:
        run = self.repository.get_run(run_id)
        if run is None:
            raise ValueError(f"run not found: {run_id}")

        if mark_running:
            self.repository.mark_run_running(run_id=run_id)
            run = self.repository.get_run(run_id)
            if run is None:
                raise ValueError(f"run not found after mark running: {run_id}")

        plugin = self.registry.get(run.signal_key)
        provider = self.provider_factory(run.source_type)

        try:
            state = SignalPluginState()
            request = SignalRunRequestDTO(
                signal_key=run.signal_key,
                date_range=SignalDateRangeDTO(
                    start_date=run.requested_start_date,
                    end_date=run.requested_end_date,
                ),
                config=run.config,
                source_type=run.source_type,
            )
            config = plugin.validate_config(run.config)
            plugin.compute_metrics(
                run_id=run_id,
                provider=provider,
                start_date=run.requested_start_date,
                end_date=run.requested_end_date,
                config=config,
                state=state,
            )
            self._ensure_run_not_canceled(run_id)
            plugin.detect_events(run_id=run_id, config=config, state=state)
            self._ensure_run_not_canceled(run_id)
            plugin.evaluate(run=request, provider=provider, state=state)
            self._ensure_run_not_canceled(run_id)
            plugin.build_artifacts(run_id=run_id, config=config, state=state)
            self._ensure_run_not_canceled(run_id)

            self.repository.replace_metrics(run_id=run_id, metrics=state.metrics)
            self.repository.replace_events(run_id=run_id, events=state.events)
            self.repository.replace_stats(run_id=run_id, stats=state.stats)
            self.repository.replace_param_sweeps(run_id=run_id, points=state.param_sweeps)
            self.repository.replace_artifacts(run_id=run_id, artifacts=state.artifacts)
            self._ensure_run_not_canceled(run_id)

            summary = {
                **state.summary,
                "metric_points": len(state.metrics),
                "events": len(state.events),
                "stats": len(state.stats),
                "param_sweeps": len(state.param_sweeps),
                "artifacts": len(state.artifacts),
                "completed_at": datetime.now(UTC).isoformat(),
            }
            self.repository.mark_run_succeeded(run_id=run_id, summary=summary)
        except Exception as exc:
            latest = self.repository.get_run(run_id)
            if latest is None:
                raise ValueError(f"run missing after execution failure: {run_id}") from exc
            if latest.status == SignalRunStatus.CANCELED:
                return latest
            self.repository.mark_run_failed(run_id=run_id, error=str(exc))

        latest = self.repository.get_run(run_id)
        if latest is None:
            raise ValueError(f"run missing after execution: {run_id}")
        return latest

    def _ensure_run_not_canceled(self, run_id: str) -> None:
        current = self.repository.get_run(run_id)
        if current is None:
            raise ValueError(f"run not found: {run_id}")
        if current.status == SignalRunStatus.CANCELED:
            raise RunCancelledError(f"run canceled: {run_id}")
