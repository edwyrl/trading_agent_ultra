from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from app.container import Container
from app.main import create_app
from contracts.enums import SignalRunStatus, SignalSourceType
from contracts.signals_contracts import SignalRunRequestDTO, SignalRunStatusDTO
from shared.db.session import get_db_session
from signals import default_signal_registry
from signals.service import SignalResearchService
from signals.services.market_data_provider import DailySnapshotRow


class _FakeSession:
    def commit(self) -> None:
        return None


class _FakeProvider:
    def list_trade_days(self, *, start_date: date, end_date: date) -> list[date]:
        out = []
        cur = start_date
        while cur <= end_date:
            out.append(cur)
            cur += timedelta(days=1)
        return out

    def fetch_daily_snapshot(self, *, as_of_date: date) -> list[DailySnapshotRow]:
        boost = 4000.0 if as_of_date.day % 5 in {1, 2} else 0.0
        rows: list[DailySnapshotRow] = []
        for index in range(60):
            amount = 1000.0 + index * 12.0
            vol = 100.0 + index
            if index == 0:
                amount += boost
            elif index == 1:
                amount += boost
            rows.append(
                DailySnapshotRow(
                    ts_code=f"000{index:03d}.SZ",
                    close=10.0 + index / 100,
                    pre_close=10.0,
                    pct_chg=((index % 5) - 2) * 0.9,
                    amount=amount,
                    vol=vol,
                    turnover_rate=2.0 + index / 20,
                )
            )
        return rows

    def fetch_market_returns(self, *, start_date: date, end_date: date) -> dict[date, float]:
        out: dict[date, float] = {}
        cur = start_date
        i = 0
        while cur <= end_date:
            out[cur] = 0.002 if i % 3 == 0 else -0.001
            i += 1
            cur += timedelta(days=1)
        return out


class _InMemoryRepo:
    def __init__(self) -> None:
        self.runs: dict[str, SignalRunStatusDTO] = {}
        self.jobs: dict[str, dict] = {}
        self.metrics: dict[str, list] = {}
        self.events: dict[str, list] = {}
        self.stats: dict[str, list] = {}
        self.sweeps: dict[str, list] = {}
        self.artifacts: dict[str, list] = {}

    def create_run_and_enqueue(self, *, run_id: str, request: SignalRunRequestDTO) -> SignalRunStatusDTO:
        now = datetime.now(UTC)
        status = SignalRunStatusDTO(
            run_id=run_id,
            signal_key=request.signal_key,
            source_type=request.source_type,
            status=SignalRunStatus.PENDING,
            requested_start_date=request.date_range.start_date,
            requested_end_date=request.date_range.end_date,
            created_at=now,
            updated_at=now,
            config=request.config,
        )
        self.runs[run_id] = status
        self.jobs[run_id] = {"status": SignalRunStatus.PENDING, "attempt": 0, "max": request.max_retries}
        return status

    def list_runs(self, *, status=None, limit: int = 50, offset: int = 0):
        runs = list(self.runs.values())
        if status is not None:
            runs = [item for item in runs if item.status == status]
        return runs[offset : offset + limit]

    def get_run(self, run_id: str):
        return self.runs.get(run_id)

    def get_pending_job(self, *, worker_id: str):
        _ = worker_id
        for run_id, item in self.jobs.items():
            if item["status"] == SignalRunStatus.PENDING:
                item["status"] = SignalRunStatus.RUNNING
                return run_id
        return None

    def mark_run_running(self, *, run_id: str) -> None:
        run = self.runs[run_id]
        self.runs[run_id] = run.model_copy(update={"status": SignalRunStatus.RUNNING, "started_at": datetime.now(UTC)})

    def mark_run_succeeded(self, *, run_id: str, summary: dict) -> None:
        run = self.runs[run_id]
        self.jobs[run_id]["status"] = SignalRunStatus.SUCCEEDED
        self.runs[run_id] = run.model_copy(
            update={
                "status": SignalRunStatus.SUCCEEDED,
                "summary": summary,
                "finished_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "error": None,
            }
        )

    def mark_run_failed(self, *, run_id: str, error: str) -> None:
        run = self.runs[run_id]
        job = self.jobs[run_id]
        job["attempt"] += 1
        if job["attempt"] <= job["max"]:
            job["status"] = SignalRunStatus.PENDING
            self.runs[run_id] = run.model_copy(update={"status": SignalRunStatus.PENDING, "error": error})
            return
        job["status"] = SignalRunStatus.FAILED
        self.runs[run_id] = run.model_copy(update={"status": SignalRunStatus.FAILED, "error": error})

    def cancel_run(self, *, run_id: str, reason: str) -> SignalRunStatusDTO:
        run = self.runs.get(run_id)
        if run is None:
            raise ValueError(f"run not found: {run_id}")
        if run.status in {SignalRunStatus.SUCCEEDED, SignalRunStatus.FAILED, SignalRunStatus.CANCELED}:
            raise ValueError(f"run is not cancelable: {run_id}")
        if run_id in self.jobs:
            self.jobs[run_id]["status"] = SignalRunStatus.CANCELED
        updated = run.model_copy(update={"status": SignalRunStatus.CANCELED, "error": reason, "finished_at": datetime.now(UTC), "updated_at": datetime.now(UTC)})
        self.runs[run_id] = updated
        return updated

    def delete_run(self, *, run_id: str) -> bool:
        run = self.runs.get(run_id)
        if run is None:
            return False
        if run.status not in {SignalRunStatus.SUCCEEDED, SignalRunStatus.FAILED, SignalRunStatus.CANCELED}:
            raise ValueError(f"run is not deletable: {run_id}")
        self.runs.pop(run_id, None)
        self.jobs.pop(run_id, None)
        self.metrics.pop(run_id, None)
        self.events.pop(run_id, None)
        self.stats.pop(run_id, None)
        self.sweeps.pop(run_id, None)
        self.artifacts.pop(run_id, None)
        return True

    def replace_metrics(self, *, run_id: str, metrics):
        self.metrics[run_id] = list(metrics)

    def replace_events(self, *, run_id: str, events):
        self.events[run_id] = list(events)

    def replace_stats(self, *, run_id: str, stats):
        self.stats[run_id] = list(stats)

    def replace_param_sweeps(self, *, run_id: str, points):
        self.sweeps[run_id] = list(points)

    def replace_artifacts(self, *, run_id: str, artifacts):
        self.artifacts[run_id] = list(artifacts)

    def list_metrics(self, *, run_id: str):
        return self.metrics.get(run_id, [])

    def list_events(self, *, run_id: str):
        return self.events.get(run_id, [])

    def list_stats(self, *, run_id: str):
        return self.stats.get(run_id, [])

    def list_param_sweeps(self, *, run_id: str):
        return self.sweeps.get(run_id, [])

    def list_artifacts(self, *, run_id: str):
        return self.artifacts.get(run_id, [])


def test_signal_api_submit_worker_query_chain(monkeypatch, tmp_path) -> None:
    app = create_app(enable_signal_worker=False)
    repo = _InMemoryRepo()
    service = SignalResearchService(
        repository=repo,
        provider_factory=lambda _source: _FakeProvider(),
        registry=default_signal_registry(),
    )

    monkeypatch.setattr(Container, "signal_service", lambda self: service)

    def _override_db_session():
        yield _FakeSession()

    app.dependency_overrides[get_db_session] = _override_db_session

    client = TestClient(app)
    response = client.post(
        "/api/signals/runs",
        json={
            "signal_key": "liquidity_concentration",
            "date_range": {"start_date": "2026-04-01", "end_date": "2026-04-20"},
            "config": {"artifact_dir": str(tmp_path), "threshold": 0.3},
        },
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]
    assert response.json()["status"] == "PENDING"

    status = service.execute_next_job(worker_id="test-worker")
    assert status is not None
    assert status.status == SignalRunStatus.SUCCEEDED

    run_resp = client.get(f"/api/signals/runs/{run_id}")
    assert run_resp.status_code == 200
    assert run_resp.json()["status"] == "SUCCEEDED"

    dashboard_resp = client.get(f"/api/signals/runs/{run_id}/dashboard")
    assert dashboard_resp.status_code == 200
    assert dashboard_resp.json()["run"]["run_id"] == run_id
    assert "overview" in dashboard_resp.json()
    assert "key_metrics" in dashboard_resp.json()
    assert dashboard_resp.json()["tabs"]
    assert any(tab["tab_key"] == "sensitivity" for tab in dashboard_resp.json()["tabs"])

    artifacts_resp = client.get(f"/api/signals/runs/{run_id}/artifacts")
    assert artifacts_resp.status_code == 200
    assert len(artifacts_resp.json()) >= 2

    plugins_resp = client.get("/api/signals/plugins")
    assert plugins_resp.status_code == 200
    assert any(item["signal_key"] == "liquidity_concentration" for item in plugins_resp.json())

    app.dependency_overrides.clear()


def test_signal_api_cancel_and_delete_run(monkeypatch) -> None:
    app = create_app(enable_signal_worker=False)
    repo = _InMemoryRepo()
    service = SignalResearchService(
        repository=repo,
        provider_factory=lambda _source: _FakeProvider(),
        registry=default_signal_registry(),
    )
    monkeypatch.setattr(Container, "signal_service", lambda self: service)

    def _override_db_session():
        yield _FakeSession()

    app.dependency_overrides[get_db_session] = _override_db_session
    client = TestClient(app)

    response = client.post(
        "/api/signals/runs",
        json={
            "signal_key": "liquidity_concentration",
            "date_range": {"start_date": "2026-04-01", "end_date": "2026-04-20"},
            "config": {},
        },
    )
    run_id = response.json()["run_id"]

    cancel_resp = client.post(f"/api/signals/runs/{run_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELED"

    delete_resp = client.delete(f"/api/signals/runs/{run_id}")
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/api/signals/runs/{run_id}")
    assert missing_resp.status_code == 404

    app.dependency_overrides.clear()
