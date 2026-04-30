from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.container import Container
from shared.db.session import SessionLocal
from shared.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class SignalWorkerConfig:
    worker_id: str = "signal-worker-api-local"
    poll_interval_seconds: float = 5.0
    max_jobs_per_tick: int = 1
    stale_lock_timeout_seconds: float = 1800.0


def run_signal_worker_once(
    *,
    worker_id: str,
    max_jobs: int = 1,
    stale_lock_timeout_seconds: float = 1800.0,
) -> list[dict[str, Any]]:
    """Claim jobs in short transactions, then execute each run in a fresh session."""
    outputs: list[dict[str, Any]] = []

    with SessionLocal() as session:
        try:
            container = Container(session=session)
            service = container.signal_service()
            requeued = service.requeue_stale_jobs(timeout_seconds=stale_lock_timeout_seconds)
            if requeued:
                logger.warning("Signal worker requeued %s stale job(s)", requeued)
            session.commit()
        except Exception:
            session.rollback()
            raise

    for _ in range(max(1, max_jobs)):
        with SessionLocal() as claim_session:
            try:
                container = Container(session=claim_session)
                service = container.signal_service()
                claimed = service.claim_next_job(worker_id=worker_id)
                if claimed is None:
                    claim_session.commit()
                    break
                claim_session.commit()
            except Exception:
                claim_session.rollback()
                raise

        with SessionLocal() as execute_session:
            try:
                container = Container(session=execute_session)
                service = container.signal_service()
                status = service.execute_run(run_id=claimed.run_id, mark_running=False)
                execute_session.commit()
                outputs.append(
                    {
                        "run_id": status.run_id,
                        "status": status.status.value,
                        "signal_key": status.signal_key,
                        "error": status.error,
                    }
                )
            except Exception:
                execute_session.rollback()
                raise
    return outputs


async def run_signal_worker_loop(*, config: SignalWorkerConfig, stop_event: asyncio.Event) -> None:
    logger.info(
        "Signal worker started: id=%s poll_interval=%.2fs max_jobs_per_tick=%s",
        config.worker_id,
        config.poll_interval_seconds,
        config.max_jobs_per_tick,
    )
    try:
        while not stop_event.is_set():
            try:
                items = await asyncio.to_thread(
                    run_signal_worker_once,
                    worker_id=config.worker_id,
                    max_jobs=config.max_jobs_per_tick,
                    stale_lock_timeout_seconds=config.stale_lock_timeout_seconds,
                )
                if items:
                    logger.info("Signal worker processed %s queued run(s): %s", len(items), items)
            except Exception:
                logger.exception("Signal worker tick failed")

            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=max(config.poll_interval_seconds, 0.2),
                )
            except TimeoutError:
                continue
    finally:
        logger.info("Signal worker stopped: id=%s", config.worker_id)
