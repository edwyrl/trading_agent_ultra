from __future__ import annotations

from contracts.integration_contracts import RecheckQueueItemDTO
from industry.service import IndustryService
from integration.repository import IntegrationRepository
from shared.logging import get_logger
from shared.retry import run_with_retry


class IndustryRecheckExecutor:
    """Consume pending recheck queue and invoke industry refresh service."""

    def __init__(
        self,
        repository: IntegrationRepository,
        industry_service: IndustryService,
        *,
        max_attempts: int = 3,
        initial_delay_seconds: float = 0.2,
        backoff_factor: float = 2.0,
    ):
        self.repository = repository
        self.industry_service = industry_service
        self.max_attempts = max_attempts
        self.initial_delay_seconds = initial_delay_seconds
        self.backoff_factor = backoff_factor
        self.logger = get_logger(__name__)

    def run_pending(self, limit: int | None = None) -> dict[str, int]:
        pending = self.repository.list_pending_rechecks()
        if limit is not None:
            pending = pending[:limit]

        stats = {"total": len(pending), "done": 0, "failed": 0}
        self.logger.info("industry_recheck_run_start total=%s limit=%s", len(pending), limit)
        for item in pending:
            self._process_one(item=item, stats=stats)
        self.logger.info(
            "industry_recheck_run_done total=%s done=%s failed=%s",
            stats["total"],
            stats["done"],
            stats["failed"],
        )
        return stats

    def _process_one(self, item: RecheckQueueItemDTO, stats: dict[str, int]) -> None:
        try:
            def _refresh_once() -> None:
                self.industry_service.refresh_industry_thesis(
                    industry_id=item.industry_id,
                    mode=item.recommended_mode,
                )

            _, retry = run_with_retry(
                _refresh_once,
                operation_name=f"industry_recheck:{item.industry_id}",
                max_attempts=self.max_attempts,
                initial_delay_seconds=self.initial_delay_seconds,
                backoff_factor=self.backoff_factor,
            )
            self.repository.update_recheck_status(
                queue_id=item.queue_id,
                status="DONE",
                note=f"attempts={retry.attempts}",
            )
            stats["done"] += 1
            self.logger.info(
                "industry_recheck_item_done queue_id=%s industry_id=%s mode=%s attempts=%s",
                item.queue_id,
                item.industry_id,
                item.recommended_mode.value,
                retry.attempts,
            )
        except Exception as exc:  # pragma: no cover - runtime safety
            self.repository.update_recheck_status(queue_id=item.queue_id, status="FAILED", note=str(exc))
            stats["failed"] += 1
            self.logger.error(
                "industry_recheck_item_failed queue_id=%s industry_id=%s mode=%s error=%s",
                item.queue_id,
                item.industry_id,
                item.recommended_mode.value,
                exc,
            )
