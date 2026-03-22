from __future__ import annotations

from contracts.integration_contracts import RecheckQueueItemDTO
from industry.service import IndustryService
from integration.repository import IntegrationRepository


class IndustryRecheckExecutor:
    """Consume pending recheck queue and invoke industry refresh service."""

    def __init__(self, repository: IntegrationRepository, industry_service: IndustryService):
        self.repository = repository
        self.industry_service = industry_service

    def run_pending(self, limit: int | None = None) -> dict[str, int]:
        pending = self.repository.list_pending_rechecks()
        if limit is not None:
            pending = pending[:limit]

        stats = {"total": len(pending), "done": 0, "failed": 0}
        for item in pending:
            self._process_one(item=item, stats=stats)
        return stats

    def _process_one(self, item: RecheckQueueItemDTO, stats: dict[str, int]) -> None:
        try:
            self.industry_service.refresh_industry_thesis(
                industry_id=item.industry_id,
                mode=item.recommended_mode,
            )
            self.repository.update_recheck_status(queue_id=item.queue_id, status="DONE", note=None)
            stats["done"] += 1
        except Exception as exc:  # pragma: no cover - kept to ensure queue safety in runtime
            self.repository.update_recheck_status(queue_id=item.queue_id, status="FAILED", note=str(exc))
            stats["failed"] += 1
