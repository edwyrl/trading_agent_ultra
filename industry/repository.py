from __future__ import annotations

from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from contracts.industry_contracts import IndustryDeltaDTO, IndustryThesisCardDTO, IndustryThesisSummaryDTO
from contracts.enums import SwLevel
from industry.models import (
    IndustryDeltaModel,
    IndustryThesisLatestModel,
    IndustryThesisSnapshotModel,
    IndustryWeeklyRefreshCandidateModel,
)


class IndustryRepository(Protocol):
    def save_snapshot(self, thesis: IndustryThesisCardDTO) -> None: ...

    def save_delta(self, delta: IndustryDeltaDTO) -> None: ...

    def get_latest(self, industry_id: str, sw_level: SwLevel) -> IndustryThesisCardDTO | None: ...

    def get_summary(self, industry_id: str, preferred_levels: list[SwLevel]) -> IndustryThesisSummaryDTO | None: ...

    def list_deltas(self, industry_id: str, since_version: str | None = None) -> list[IndustryDeltaDTO]: ...

    def save_weekly_candidates(self, week_key: str, candidates: list[dict]) -> None: ...


class PostgresIndustryRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_snapshot(self, thesis: IndustryThesisCardDTO) -> None:
        snapshot = IndustryThesisSnapshotModel(
            version=thesis.version,
            industry_id=thesis.industry_id,
            industry_name=thesis.industry_name,
            sw_level=thesis.sw_level.value,
            as_of_date=thesis.as_of_date,
            current_bias=thesis.current_bias.value,
            confidence_score=thesis.confidence.score,
            payload=thesis.model_dump(mode="json"),
        )
        self.session.add(snapshot)

        latest = self.session.get(
            IndustryThesisLatestModel,
            {"industry_id": thesis.industry_id, "sw_level": thesis.sw_level.value},
        )
        if latest:
            latest.latest_version = thesis.version
            latest.as_of_date = thesis.as_of_date
        else:
            latest = IndustryThesisLatestModel(
                industry_id=thesis.industry_id,
                sw_level=thesis.sw_level.value,
                latest_version=thesis.version,
                as_of_date=thesis.as_of_date,
            )
            self.session.add(latest)

    def save_delta(self, delta: IndustryDeltaDTO) -> None:
        row = IndustryDeltaModel(
            delta_id=delta.delta_id,
            industry_id=delta.entity_id,
            from_version=delta.from_version,
            to_version=delta.to_version,
            as_of_date=delta.as_of_date,
            material_change=delta.material_change.material_change,
            payload=delta.model_dump(mode="json"),
        )
        self.session.add(row)

    def get_latest(self, industry_id: str, sw_level: SwLevel) -> IndustryThesisCardDTO | None:
        latest = self.session.get(IndustryThesisLatestModel, {"industry_id": industry_id, "sw_level": sw_level.value})
        if not latest:
            return None

        query = select(IndustryThesisSnapshotModel).where(IndustryThesisSnapshotModel.version == latest.latest_version)
        snapshot = self.session.execute(query).scalars().first()
        if not snapshot:
            return None
        return IndustryThesisCardDTO.model_validate(snapshot.payload)

    def get_summary(self, industry_id: str, preferred_levels: list[SwLevel]) -> IndustryThesisSummaryDTO | None:
        for level in preferred_levels:
            thesis = self.get_latest(industry_id=industry_id, sw_level=level)
            if thesis:
                return IndustryThesisSummaryDTO(
                    version=thesis.version,
                    as_of_date=thesis.as_of_date,
                    industry_id=thesis.industry_id,
                    industry_name=thesis.industry_name,
                    sw_level=thesis.sw_level,
                    current_bias=thesis.current_bias,
                    bull_base_bear_summary=f"Bull: {thesis.bull_case}; Base: {thesis.base_case}; Bear: {thesis.bear_case}",
                    key_drivers=thesis.core_drivers,
                    key_risks=thesis.core_conflicts,
                    company_fit_questions=thesis.bias_shift_risk,
                    confidence=thesis.confidence,
                )
        return None

    def list_deltas(self, industry_id: str, since_version: str | None = None) -> list[IndustryDeltaDTO]:
        query = select(IndustryDeltaModel).where(IndustryDeltaModel.industry_id == industry_id)
        if since_version:
            query = query.where(IndustryDeltaModel.to_version > since_version)
        rows = self.session.execute(query.order_by(IndustryDeltaModel.as_of_date.desc())).scalars().all()
        return [IndustryDeltaDTO.model_validate(row.payload) for row in rows]

    def save_weekly_candidates(self, week_key: str, candidates: list[dict]) -> None:
        for idx, candidate in enumerate(candidates, start=1):
            row = IndustryWeeklyRefreshCandidateModel(
                week_key=week_key,
                industry_id=candidate["industry_id"],
                score=candidate["score"],
                score_breakdown=candidate.get("score_breakdown", {}),
                selected=candidate.get("selected", False),
                rank_order=idx,
                reason=candidate.get("reason", ""),
            )
            self.session.add(row)
