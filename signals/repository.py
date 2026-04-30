from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from contracts.enums import SignalRunStatus, SignalSourceType
from contracts.signals_contracts import (
    SignalArtifactDTO,
    SignalEventDTO,
    SignalMetricPointDTO,
    SignalParamSweepPointDTO,
    SignalRunRequestDTO,
    SignalRunStatusDTO,
    SignalStatDTO,
)
from signals.models import (
    SignalArtifactModel,
    SignalEventModel,
    SignalJobQueueModel,
    SignalMetricTimeseriesModel,
    SignalParamSweepModel,
    SignalRunModel,
    SignalStatModel,
)
from shared.time_utils import utc_now


class SignalRepository(Protocol):
    def create_run_and_enqueue(self, *, run_id: str, request: SignalRunRequestDTO) -> SignalRunStatusDTO: ...

    def list_runs(self, *, status: SignalRunStatus | None = None, limit: int = 50, offset: int = 0) -> list[SignalRunStatusDTO]: ...

    def get_run(self, run_id: str) -> SignalRunStatusDTO | None: ...

    def get_pending_job(self, *, worker_id: str) -> str | None: ...

    def requeue_stale_jobs(self, *, timeout_seconds: float) -> int: ...

    def mark_run_running(self, *, run_id: str) -> None: ...

    def mark_run_succeeded(self, *, run_id: str, summary: dict) -> None: ...

    def mark_run_failed(self, *, run_id: str, error: str) -> None: ...

    def cancel_run(self, *, run_id: str, reason: str) -> SignalRunStatusDTO: ...

    def delete_run(self, *, run_id: str) -> bool: ...

    def replace_metrics(self, *, run_id: str, metrics: list[SignalMetricPointDTO]) -> None: ...

    def replace_events(self, *, run_id: str, events: list[SignalEventDTO]) -> None: ...

    def replace_stats(self, *, run_id: str, stats: list[SignalStatDTO]) -> None: ...

    def replace_param_sweeps(self, *, run_id: str, points: list[SignalParamSweepPointDTO]) -> None: ...

    def replace_artifacts(self, *, run_id: str, artifacts: list[SignalArtifactDTO]) -> None: ...

    def list_metrics(self, *, run_id: str) -> list[SignalMetricPointDTO]: ...

    def list_events(self, *, run_id: str) -> list[SignalEventDTO]: ...

    def list_stats(self, *, run_id: str) -> list[SignalStatDTO]: ...

    def list_param_sweeps(self, *, run_id: str) -> list[SignalParamSweepPointDTO]: ...

    def list_artifacts(self, *, run_id: str) -> list[SignalArtifactDTO]: ...


class PostgresSignalRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_run_and_enqueue(self, *, run_id: str, request: SignalRunRequestDTO) -> SignalRunStatusDTO:
        now = utc_now()
        run = SignalRunModel(
            run_id=run_id,
            signal_key=request.signal_key,
            source_type=request.source_type.value,
            status=SignalRunStatus.PENDING.value,
            requested_start_date=request.date_range.start_date,
            requested_end_date=request.date_range.end_date,
            config=request.config,
            summary={},
            created_at=now,
            updated_at=now,
        )
        job = SignalJobQueueModel(
            run_id=run_id,
            status=SignalRunStatus.PENDING.value,
            attempt_count=0,
            max_retries=request.max_retries,
            note="queued",
            next_run_at=now,
            created_at=now,
            updated_at=now,
        )
        self.session.add(run)
        self.session.add(job)
        return self._to_run_status(run)

    def list_runs(
        self,
        *,
        status: SignalRunStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[SignalRunStatusDTO]:
        query = select(SignalRunModel)
        if status is not None:
            query = query.where(SignalRunModel.status == status.value)
        rows = self.session.execute(
            query.order_by(SignalRunModel.created_at.desc()).limit(max(1, min(limit, 200))).offset(max(offset, 0))
        ).scalars()
        return [self._to_run_status(row) for row in rows]

    def get_run(self, run_id: str) -> SignalRunStatusDTO | None:
        row = self.session.execute(select(SignalRunModel).where(SignalRunModel.run_id == run_id)).scalars().first()
        if row is None:
            return None
        return self._to_run_status(row)

    def get_pending_job(self, *, worker_id: str) -> str | None:
        now = datetime.now(UTC)
        stmt = (
            select(SignalJobQueueModel)
            .where(SignalJobQueueModel.status == SignalRunStatus.PENDING.value)
            .where(SignalJobQueueModel.next_run_at <= now)
            .order_by(SignalJobQueueModel.created_at.asc())
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        row = self.session.execute(stmt).scalars().first()
        if row is None:
            return None
        row.status = SignalRunStatus.RUNNING.value
        row.locked_by = worker_id
        row.locked_at = now
        row.updated_at = now
        row.note = "worker claimed"
        return row.run_id

    def requeue_stale_jobs(self, *, timeout_seconds: float) -> int:
        now = datetime.now(UTC)
        cutoff = now - timedelta(seconds=max(timeout_seconds, 1.0))
        rows = (
            self.session.execute(
                select(SignalJobQueueModel)
                .where(SignalJobQueueModel.status == SignalRunStatus.RUNNING.value)
                .where(SignalJobQueueModel.locked_at.is_not(None))
                .where(SignalJobQueueModel.locked_at <= cutoff)
                .with_for_update(skip_locked=True)
            )
            .scalars()
            .all()
        )
        requeued = 0
        for queue in rows:
            run = (
                self.session.execute(select(SignalRunModel).where(SignalRunModel.run_id == queue.run_id))
                .scalars()
                .first()
            )
            queue.attempt_count += 1
            queue.updated_at = now
            queue.locked_by = None
            queue.locked_at = None
            queue.next_run_at = now
            if queue.attempt_count > queue.max_retries:
                queue.status = SignalRunStatus.FAILED.value
                queue.note = "stale worker lock exceeded max retries"
                if run is not None:
                    run.status = SignalRunStatus.FAILED.value
                    run.error = queue.note
                    run.finished_at = now
                    run.updated_at = now
            else:
                queue.status = SignalRunStatus.PENDING.value
                queue.note = "stale worker lock requeued"
                if run is not None:
                    run.status = SignalRunStatus.PENDING.value
                    run.error = queue.note
                    run.updated_at = now
            requeued += 1
        return requeued

    def mark_run_running(self, *, run_id: str) -> None:
        now = utc_now()
        run = self.session.execute(select(SignalRunModel).where(SignalRunModel.run_id == run_id)).scalars().first()
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        run.status = SignalRunStatus.RUNNING.value
        run.started_at = now
        run.updated_at = now

    def mark_run_succeeded(self, *, run_id: str, summary: dict) -> None:
        now = utc_now()
        run = self.session.execute(select(SignalRunModel).where(SignalRunModel.run_id == run_id)).scalars().first()
        queue = self.session.execute(select(SignalJobQueueModel).where(SignalJobQueueModel.run_id == run_id)).scalars().first()
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        run.status = SignalRunStatus.SUCCEEDED.value
        run.summary = summary
        run.error = None
        run.finished_at = now
        run.updated_at = now
        if queue is not None:
            queue.status = SignalRunStatus.SUCCEEDED.value
            queue.updated_at = now
            queue.note = "succeeded"

    def mark_run_failed(self, *, run_id: str, error: str) -> None:
        now = utc_now()
        run = self.session.execute(select(SignalRunModel).where(SignalRunModel.run_id == run_id)).scalars().first()
        queue = self.session.execute(select(SignalJobQueueModel).where(SignalJobQueueModel.run_id == run_id)).scalars().first()
        if run is None:
            raise ValueError(f"run not found: {run_id}")

        run.error = error
        run.updated_at = now

        if queue is None:
            run.status = SignalRunStatus.FAILED.value
            run.finished_at = now
            return

        queue.attempt_count += 1
        queue.updated_at = now
        queue.note = error[:1000]
        if queue.attempt_count <= queue.max_retries:
            queue.status = SignalRunStatus.PENDING.value
            queue.next_run_at = now
            queue.locked_by = None
            queue.locked_at = None
            run.status = SignalRunStatus.PENDING.value
        else:
            queue.status = SignalRunStatus.FAILED.value
            run.status = SignalRunStatus.FAILED.value
            run.finished_at = now

    def cancel_run(self, *, run_id: str, reason: str) -> SignalRunStatusDTO:
        now = utc_now()
        run = self.session.execute(select(SignalRunModel).where(SignalRunModel.run_id == run_id)).scalars().first()
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        if run.status in {SignalRunStatus.SUCCEEDED.value, SignalRunStatus.FAILED.value, SignalRunStatus.CANCELED.value}:
            raise ValueError(f"run is not cancelable: {run_id}")

        queue = self.session.execute(select(SignalJobQueueModel).where(SignalJobQueueModel.run_id == run_id)).scalars().first()
        run.status = SignalRunStatus.CANCELED.value
        run.error = reason
        run.updated_at = now
        run.finished_at = now
        if queue is not None:
            queue.status = SignalRunStatus.CANCELED.value
            queue.note = reason[:1000]
            queue.updated_at = now
            queue.locked_by = None
            queue.locked_at = None
            queue.next_run_at = now
        return self._to_run_status(run)

    def delete_run(self, *, run_id: str) -> bool:
        run = self.session.execute(select(SignalRunModel).where(SignalRunModel.run_id == run_id)).scalars().first()
        if run is None:
            return False
        if run.status not in {SignalRunStatus.SUCCEEDED.value, SignalRunStatus.FAILED.value, SignalRunStatus.CANCELED.value}:
            raise ValueError(f"run is not deletable: {run_id}")

        self.session.execute(delete(SignalMetricTimeseriesModel).where(SignalMetricTimeseriesModel.run_id == run_id))
        self.session.execute(delete(SignalEventModel).where(SignalEventModel.run_id == run_id))
        self.session.execute(delete(SignalStatModel).where(SignalStatModel.run_id == run_id))
        self.session.execute(delete(SignalParamSweepModel).where(SignalParamSweepModel.run_id == run_id))
        self.session.execute(delete(SignalArtifactModel).where(SignalArtifactModel.run_id == run_id))
        self.session.execute(delete(SignalJobQueueModel).where(SignalJobQueueModel.run_id == run_id))
        self.session.execute(delete(SignalRunModel).where(SignalRunModel.run_id == run_id))
        return True

    def replace_metrics(self, *, run_id: str, metrics: list[SignalMetricPointDTO]) -> None:
        self.session.execute(delete(SignalMetricTimeseriesModel).where(SignalMetricTimeseriesModel.run_id == run_id))
        self.session.add_all(
            [
                SignalMetricTimeseriesModel(
                    run_id=run_id,
                    metric_name=item.metric_name,
                    metric_date=item.metric_date,
                    metric_value=item.metric_value,
                    payload=item.payload,
                )
                for item in metrics
            ]
        )

    def replace_events(self, *, run_id: str, events: list[SignalEventDTO]) -> None:
        self.session.execute(delete(SignalEventModel).where(SignalEventModel.run_id == run_id))
        self.session.add_all(
            [
                SignalEventModel(
                    run_id=run_id,
                    event_id=item.event_id,
                    event_date=item.event_date,
                    event_type=item.event_type,
                    score=item.score,
                    payload=item.payload,
                )
                for item in events
            ]
        )

    def replace_stats(self, *, run_id: str, stats: list[SignalStatDTO]) -> None:
        self.session.execute(delete(SignalStatModel).where(SignalStatModel.run_id == run_id))
        self.session.add_all(
            [
                SignalStatModel(
                    run_id=run_id,
                    stat_group=item.stat_group,
                    stat_name=item.stat_name,
                    stat_value=item.stat_value,
                    payload=item.payload,
                )
                for item in stats
            ]
        )

    def replace_param_sweeps(self, *, run_id: str, points: list[SignalParamSweepPointDTO]) -> None:
        self.session.execute(delete(SignalParamSweepModel).where(SignalParamSweepModel.run_id == run_id))
        self.session.add_all(
            [
                SignalParamSweepModel(
                    run_id=run_id,
                    sweep_name=item.sweep_name,
                    x_key=item.x_key,
                    x_value=item.x_value,
                    y_key=item.y_key,
                    y_value=item.y_value,
                    metric_name=item.metric_name,
                    metric_value=item.metric_value,
                    payload=item.payload,
                )
                for item in points
            ]
        )

    def replace_artifacts(self, *, run_id: str, artifacts: list[SignalArtifactDTO]) -> None:
        self.session.execute(delete(SignalArtifactModel).where(SignalArtifactModel.run_id == run_id))
        self.session.add_all(
            [
                SignalArtifactModel(
                    run_id=run_id,
                    artifact_type=item.artifact_type,
                    artifact_key=item.artifact_key,
                    uri=item.uri,
                    content_type=item.content_type,
                    size_bytes=item.size_bytes,
                    payload=item.payload,
                )
                for item in artifacts
            ]
        )

    def list_metrics(self, *, run_id: str) -> list[SignalMetricPointDTO]:
        rows = self.session.execute(
            select(SignalMetricTimeseriesModel)
            .where(SignalMetricTimeseriesModel.run_id == run_id)
            .order_by(SignalMetricTimeseriesModel.metric_date.asc(), SignalMetricTimeseriesModel.metric_name.asc())
        ).scalars()
        return [
            SignalMetricPointDTO(
                metric_name=row.metric_name,
                metric_date=row.metric_date,
                metric_value=row.metric_value,
                payload=row.payload or {},
            )
            for row in rows
        ]

    def list_events(self, *, run_id: str) -> list[SignalEventDTO]:
        rows = self.session.execute(
            select(SignalEventModel).where(SignalEventModel.run_id == run_id).order_by(SignalEventModel.event_date.asc())
        ).scalars()
        return [
            SignalEventDTO(
                event_id=row.event_id,
                event_date=row.event_date,
                event_type=row.event_type,
                score=row.score,
                payload=row.payload or {},
            )
            for row in rows
        ]

    def list_stats(self, *, run_id: str) -> list[SignalStatDTO]:
        rows = self.session.execute(
            select(SignalStatModel)
            .where(SignalStatModel.run_id == run_id)
            .order_by(SignalStatModel.stat_group.asc(), SignalStatModel.stat_name.asc())
        ).scalars()
        return [
            SignalStatDTO(
                stat_group=row.stat_group,
                stat_name=row.stat_name,
                stat_value=row.stat_value,
                payload=row.payload or {},
            )
            for row in rows
        ]

    def list_param_sweeps(self, *, run_id: str) -> list[SignalParamSweepPointDTO]:
        rows = self.session.execute(
            select(SignalParamSweepModel)
            .where(SignalParamSweepModel.run_id == run_id)
            .order_by(SignalParamSweepModel.sweep_name.asc(), SignalParamSweepModel.x_value.asc(), SignalParamSweepModel.y_value.asc())
        ).scalars()
        return [
            SignalParamSweepPointDTO(
                sweep_name=row.sweep_name,
                x_key=row.x_key,
                x_value=row.x_value,
                y_key=row.y_key,
                y_value=row.y_value,
                metric_name=row.metric_name,
                metric_value=row.metric_value,
                payload=row.payload or {},
            )
            for row in rows
        ]

    def list_artifacts(self, *, run_id: str) -> list[SignalArtifactDTO]:
        rows = self.session.execute(
            select(SignalArtifactModel).where(SignalArtifactModel.run_id == run_id).order_by(SignalArtifactModel.created_at.asc())
        ).scalars()
        return [
            SignalArtifactDTO(
                artifact_type=row.artifact_type,
                artifact_key=row.artifact_key,
                uri=row.uri,
                content_type=row.content_type,
                size_bytes=row.size_bytes,
                payload=row.payload or {},
            )
            for row in rows
        ]

    @staticmethod
    def _to_run_status(row: SignalRunModel) -> SignalRunStatusDTO:
        return SignalRunStatusDTO(
            run_id=row.run_id,
            signal_key=row.signal_key,
            source_type=SignalSourceType(row.source_type),
            status=SignalRunStatus(row.status),
            requested_start_date=row.requested_start_date,
            requested_end_date=row.requested_end_date,
            created_at=row.created_at,
            updated_at=row.updated_at,
            started_at=row.started_at,
            finished_at=row.finished_at,
            config=row.config or {},
            summary=row.summary or {},
            error=row.error,
        )
