from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.signals import router as signals_router
from shared.logging import get_logger
from signals.worker import SignalWorkerConfig, run_signal_worker_loop

logger = get_logger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return float(value)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _build_signal_worker_config() -> SignalWorkerConfig:
    return SignalWorkerConfig(
        worker_id=os.getenv("SIGNAL_WORKER_ID", "signal-worker-api-local"),
        poll_interval_seconds=_env_float("SIGNAL_WORKER_POLL_INTERVAL_SECONDS", 5.0),
        max_jobs_per_tick=_env_int("SIGNAL_WORKER_MAX_JOBS_PER_TICK", 1),
        stale_lock_timeout_seconds=_env_float("SIGNAL_WORKER_STALE_LOCK_TIMEOUT_SECONDS", 1800.0),
    )


def _lifespan(*, enable_signal_worker: bool | None):
    @asynccontextmanager
    async def _manager(app: FastAPI) -> AsyncIterator[None]:
        worker_enabled = (
            _env_bool("SIGNAL_WORKER_AUTOSTART", True)
            if enable_signal_worker is None
            else enable_signal_worker
        )
        worker_task: asyncio.Task[None] | None = None
        stop_event: asyncio.Event | None = None
        if worker_enabled:
            stop_event = asyncio.Event()
            config = _build_signal_worker_config()
            worker_task = asyncio.create_task(
                run_signal_worker_loop(config=config, stop_event=stop_event),
                name="signal-worker-api-local",
            )
            app.state.signal_worker_task = worker_task
            app.state.signal_worker_config = config
        else:
            logger.info("Signal worker autostart disabled")

        try:
            yield
        finally:
            if stop_event is not None:
                stop_event.set()
            if worker_task is not None:
                await worker_task

    return _manager


def create_app(*, enable_signal_worker: bool | None = None) -> FastAPI:
    app = FastAPI(
        title="Trading Agent Ultra API",
        version="0.1.0",
        lifespan=_lifespan(enable_signal_worker=enable_signal_worker),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(signals_router)

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()


def main() -> None:
    logger.info("FastAPI app initialized. Use uvicorn app.main:app to run server.")


if __name__ == "__main__":
    main()
