from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from contracts.enums import SignalRunStatus
from signals import worker


class _FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _FakeContainer:
    def __init__(self, *, service):
        self._service = service

    def signal_service(self):
        return self._service


def _status(run_id: str):
    return SimpleNamespace(
        run_id=run_id,
        status=SignalRunStatus.SUCCEEDED,
        signal_key="liquidity_concentration",
        error=None,
    )


def test_run_signal_worker_once_commits_each_processed_job(monkeypatch) -> None:
    session = _FakeSession()
    statuses = [_status("run-1"), _status("run-2"), None]

    class _FakeService:
        def requeue_stale_jobs(self, *, timeout_seconds: float):
            assert timeout_seconds == 1800.0
            return 0

        def claim_next_job(self, *, worker_id: str):
            assert worker_id == "test-worker"
            return statuses.pop(0)

        def execute_run(self, *, run_id: str, mark_running: bool):
            assert mark_running is False
            return _status(run_id)

    monkeypatch.setattr(worker, "SessionLocal", lambda: session)
    monkeypatch.setattr(worker, "Container", lambda *, session: _FakeContainer(service=_FakeService()))

    outputs = worker.run_signal_worker_once(worker_id="test-worker", max_jobs=5)

    assert [item["run_id"] for item in outputs] == ["run-1", "run-2"]
    assert session.commits == 6
    assert session.rollbacks == 0


def test_run_signal_worker_once_rolls_back_unhandled_failure(monkeypatch) -> None:
    session = _FakeSession()

    class _FakeService:
        def requeue_stale_jobs(self, *, timeout_seconds: float):
            _ = timeout_seconds
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(worker, "SessionLocal", lambda: session)
    monkeypatch.setattr(worker, "Container", lambda *, session: _FakeContainer(service=_FakeService()))

    with pytest.raises(RuntimeError, match="database unavailable"):
        worker.run_signal_worker_once(worker_id="test-worker", max_jobs=1)

    assert session.commits == 0
    assert session.rollbacks == 1


def test_api_lifespan_starts_and_stops_signal_worker(monkeypatch) -> None:
    events: list[tuple[str, str]] = []

    async def _fake_worker_loop(*, config, stop_event):
        events.append(("start", config.worker_id))
        await stop_event.wait()
        events.append(("stop", config.worker_id))

    monkeypatch.setattr("app.main.run_signal_worker_loop", _fake_worker_loop)

    with TestClient(create_app(enable_signal_worker=True)) as client:
        assert client.get("/healthz").status_code == 200

    assert events == [
        ("start", "signal-worker-api-local"),
        ("stop", "signal-worker-api-local"),
    ]
