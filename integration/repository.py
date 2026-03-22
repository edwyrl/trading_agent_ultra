from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from contracts.enums import UpdateMode
from contracts.integration_contracts import RecheckQueueItemDTO
from integration.models import IndustryRecheckQueueModel


class IntegrationRepository(Protocol):
    def enqueue_recheck(self, item: RecheckQueueItemDTO, reason_codes: list[str], triggered_by_macro_version: str) -> None: ...

    def list_pending_rechecks(self) -> list[RecheckQueueItemDTO]: ...

    def update_recheck_status(self, queue_id: str, status: str, note: str | None = None) -> None: ...


class PostgresIntegrationRepository:
    def __init__(self, session: Session):
        self.session = session

    def enqueue_recheck(self, item: RecheckQueueItemDTO, reason_codes: list[str], triggered_by_macro_version: str) -> None:
        existing = self.session.execute(
            select(IndustryRecheckQueueModel).where(IndustryRecheckQueueModel.queue_id == item.queue_id)
        ).scalars().first()
        if existing:
            return

        row = IndustryRecheckQueueModel(
            queue_id=item.queue_id,
            sw_l1_id=item.sw_l1_id,
            industry_id=item.industry_id,
            recommended_mode=item.recommended_mode.value,
            status=item.status,
            reason_codes=reason_codes,
            triggered_by_macro_version=triggered_by_macro_version,
            note=None,
        )
        self.session.add(row)

    def list_pending_rechecks(self) -> list[RecheckQueueItemDTO]:
        rows = self.session.execute(
            select(IndustryRecheckQueueModel)
            .where(IndustryRecheckQueueModel.status == "PENDING")
            .order_by(IndustryRecheckQueueModel.created_at.asc())
        ).scalars().all()

        return [
            RecheckQueueItemDTO(
                queue_id=row.queue_id,
                sw_l1_id=row.sw_l1_id,
                industry_id=row.industry_id,
                recommended_mode=UpdateMode(row.recommended_mode),
                status=row.status,
                reason_codes=row.reason_codes or [],
                triggered_by_macro_version=row.triggered_by_macro_version,
                created_at=row.created_at,
            )
            for row in rows
        ]

    def update_recheck_status(self, queue_id: str, status: str, note: str | None = None) -> None:
        row = self.session.execute(
            select(IndustryRecheckQueueModel).where(IndustryRecheckQueueModel.queue_id == queue_id)
        ).scalars().first()
        if not row:
            return
        row.status = status
        row.note = note
