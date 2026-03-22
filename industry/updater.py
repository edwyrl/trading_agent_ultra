from __future__ import annotations

from datetime import date, datetime
from collections.abc import Callable
from typing import Any

from contracts.confidence import ConfidenceDTO
from contracts.enums import ConfidenceLevel, EntityType, MaterialChangeLevel, UpdateMode
from contracts.industry_contracts import IndustryDeltaDTO, IndustryThesisCardDTO
from contracts.material_change import MaterialChangeDTO
from shared.time_utils import utc_now


class IndustryUpdater:
    def __init__(self, now_provider: Callable[[], datetime] | None = None):
        self._now_provider = now_provider or utc_now

    @staticmethod
    def _confidence_level(score: float) -> ConfidenceLevel:
        if score < 0.4:
            return ConfidenceLevel.LOW
        if score < 0.7:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.HIGH

    def _next_version(self, thesis: IndustryThesisCardDTO, mode: UpdateMode, now: datetime) -> str:
        return f"{thesis.industry_id}:{now.strftime('%Y%m%d%H%M%S')}:{mode.value.lower()}"

    def update(
        self,
        thesis: IndustryThesisCardDTO,
        mode: UpdateMode,
        incremental_inputs: dict[str, Any] | None = None,
        *,
        as_of_date: date | None = None,
    ) -> tuple[IndustryThesisCardDTO, IndustryDeltaDTO]:
        payload = incremental_inputs or {}
        now = self._now_provider()
        target_date = as_of_date or thesis.as_of_date

        changed_fields: list[str] = []
        latest_changes = list(thesis.latest_changes)
        latest_changes.append(f"{mode.value} update @ {target_date.isoformat()}")
        latest_changes = latest_changes[-10:]
        changed_fields.append("latest_changes")

        new_conf_score = thesis.confidence.score
        if mode == UpdateMode.LIGHT:
            new_conf_score = min(1.0, thesis.confidence.score + 0.01)
            changed_fields.extend(["last_news_update_at", "confidence"])
        elif mode == UpdateMode.MARKET:
            new_conf_score = min(1.0, thesis.confidence.score + 0.02)
            changed_fields.extend(["last_market_data_update_at", "confidence", "key_metrics_to_watch"])
        elif mode == UpdateMode.FULL:
            new_conf_score = min(1.0, thesis.confidence.score + 0.03)
            changed_fields.extend(
                [
                    "last_news_update_at",
                    "last_market_data_update_at",
                    "last_full_refresh_at",
                    "confidence",
                ]
            )

        new_conf = ConfidenceDTO(
            score=new_conf_score,
            level=self._confidence_level(new_conf_score),
            note=f"Adjusted by {mode.value} update.",
        )

        updates: dict[str, Any] = {
            "version": self._next_version(thesis, mode, now),
            "as_of_date": target_date,
            "created_at": now,
            "latest_changes": latest_changes,
            "confidence": new_conf,
        }

        if mode in (UpdateMode.LIGHT, UpdateMode.FULL):
            updates["last_news_update_at"] = now
        if mode in (UpdateMode.MARKET, UpdateMode.FULL):
            updates["last_market_data_update_at"] = now
            metric_updates = list(thesis.key_metrics_to_watch)
            marker = payload.get("market_metric_marker", f"market_refresh:{target_date.isoformat()}")
            metric_updates.append(marker)
            updates["key_metrics_to_watch"] = metric_updates[-12:]
        if mode == UpdateMode.FULL:
            updates["last_full_refresh_at"] = now

        updated = thesis.model_copy(update=updates)

        material_change = MaterialChangeDTO(
            material_change=mode == UpdateMode.FULL,
            level=MaterialChangeLevel.MEDIUM if mode == UpdateMode.FULL else MaterialChangeLevel.LOW,
            reasons=[f"industry_{mode.value.lower()}_update"],
        )

        delta = IndustryDeltaDTO(
            delta_id=f"{thesis.industry_id}:{updated.version}",
            entity_type=EntityType.INDUSTRY_THESIS,
            entity_id=thesis.industry_id,
            from_version=thesis.version,
            to_version=updated.version,
            as_of_date=target_date,
            changed_fields=changed_fields,
            summary=payload.get("summary", f"{mode.value} update applied"),
            reasons=[f"mode={mode.value}"],
            impact_scope=[f"industry:{thesis.industry_id}", f"sw_level:{thesis.sw_level.value}"],
            material_change=material_change,
            source_refs=thesis.source_refs[:5],
            created_at=now,
        )
        return updated, delta
