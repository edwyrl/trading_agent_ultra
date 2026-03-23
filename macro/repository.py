from __future__ import annotations

from datetime import date
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from contracts.macro_contracts import (
    MacroConstraintsSummaryDTO,
    MacroDeltaDTO,
    MacroEventHistoryDTO,
    MacroEventViewDTO,
    MacroIndustryMappingDTO,
    MacroMasterCardDTO,
    MacroThemeCardSummaryDTO,
)
from macro.models import (
    MacroDeltaModel,
    MacroEventHistoryModel,
    MacroEventViewModel,
    MacroIndustryMappingSnapshotModel,
    MacroMasterSnapshotModel,
    MacroRunLogModel,
    MacroThemeSnapshotModel,
)


class MacroRepository(Protocol):
    def save_master_snapshot(self, master: MacroMasterCardDTO) -> None: ...

    def save_theme_snapshot(self, theme: MacroThemeCardSummaryDTO, version: str) -> None: ...

    def save_delta(self, delta: MacroDeltaDTO) -> None: ...

    def save_industry_mapping(self, version: str, mapping: MacroIndustryMappingDTO, as_of_date: date) -> None: ...

    def save_run_log(self, payload: dict) -> None: ...

    def next_event_seq(self, event_id: str) -> int: ...

    def save_event_history(self, event: MacroEventHistoryDTO) -> None: ...

    def save_event_view(self, view: MacroEventViewDTO) -> None: ...

    def get_latest_master(self, as_of_date: date | None = None) -> MacroMasterCardDTO | None: ...

    def get_constraints_summary(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None: ...

    def list_deltas(self, since_version: str | None = None, since_date: date | None = None) -> list[MacroDeltaDTO]: ...

    def list_industry_mappings(self, version: str | None = None) -> list[MacroIndustryMappingDTO]: ...

    def list_latest_event_history(self, as_of_date: date | None = None) -> list[MacroEventHistoryDTO]: ...

    def list_event_views(
        self,
        *,
        history_ids: list[str] | None = None,
        event_ids: list[str] | None = None,
        as_of_date: date | None = None,
    ) -> list[MacroEventViewDTO]: ...


class PostgresMacroRepository:
    def __init__(self, session: Session):
        self.session = session

    def save_master_snapshot(self, master: MacroMasterCardDTO) -> None:
        row = MacroMasterSnapshotModel(
            version=master.version,
            as_of_date=master.as_of_date,
            current_macro_bias=[v.value for v in master.current_macro_bias],
            macro_mainline=master.macro_mainline,
            reasoning=master.reasoning,
            confidence_score=master.confidence.score,
            material_change=master.material_change.material_change,
            payload=master.model_dump(mode="json"),
        )
        self.session.add(row)

    def save_theme_snapshot(self, theme: MacroThemeCardSummaryDTO, version: str) -> None:
        row = MacroThemeSnapshotModel(
            version=version,
            theme_type=theme.theme_type.value,
            as_of_date=theme.as_of_date,
            payload=theme.model_dump(mode="json"),
        )
        self.session.add(row)

    def save_delta(self, delta: MacroDeltaDTO) -> None:
        row = MacroDeltaModel(
            delta_id=delta.delta_id,
            entity_id=delta.entity_id,
            from_version=delta.from_version,
            to_version=delta.to_version,
            as_of_date=delta.as_of_date,
            material_change=delta.material_change.material_change,
            payload=delta.model_dump(mode="json"),
        )
        self.session.add(row)

    def save_industry_mapping(self, version: str, mapping: MacroIndustryMappingDTO, as_of_date: date) -> None:
        row = MacroIndustryMappingSnapshotModel(
            version=version,
            as_of_date=as_of_date,
            sw_l1_id=mapping.sw_l1_id,
            sw_l1_name=mapping.sw_l1_name,
            direction=mapping.direction.value,
            score=mapping.score,
            reason=mapping.reason,
            payload=mapping.model_dump(mode="json"),
        )
        self.session.add(row)

    def save_run_log(self, payload: dict) -> None:
        row = MacroRunLogModel(**payload)
        self.session.add(row)

    def next_event_seq(self, event_id: str) -> int:
        max_seq = self.session.execute(
            select(func.max(MacroEventHistoryModel.event_seq)).where(MacroEventHistoryModel.event_id == event_id)
        ).scalar_one_or_none()
        return int(max_seq or 0) + 1

    def save_event_history(self, event: MacroEventHistoryDTO) -> None:
        row = MacroEventHistoryModel(
            history_id=event.history_id,
            event_id=event.event_id,
            event_seq=event.event_seq,
            as_of_date=event.as_of_date,
            event_status=event.event_status.value,
            title=event.title,
            fact_summary=event.fact_summary,
            theme_type=event.theme_type.value,
            bias_hint=event.bias_hint.value if event.bias_hint else None,
            source_refs=[s.model_dump(mode="json") for s in event.source_refs],
            created_at=event.created_at,
        )
        self.session.add(row)

    def save_event_view(self, view: MacroEventViewDTO) -> None:
        row = MacroEventViewModel(
            view_id=view.view_id,
            event_id=view.event_id,
            history_id=view.history_id,
            as_of_date=view.as_of_date,
            view_type=view.view_type.value,
            stance=view.stance.value,
            view_text=view.view_text,
            score=view.score,
            score_reason=view.score_reason,
            source_refs=[s.model_dump(mode="json") for s in view.source_refs],
            created_at=view.created_at,
        )
        self.session.add(row)

    def get_latest_master(self, as_of_date: date | None = None) -> MacroMasterCardDTO | None:
        query = select(MacroMasterSnapshotModel)
        if as_of_date:
            query = query.where(MacroMasterSnapshotModel.as_of_date <= as_of_date)
        query = query.order_by(MacroMasterSnapshotModel.as_of_date.desc())
        row = self.session.execute(query).scalars().first()
        if not row:
            return None
        return MacroMasterCardDTO.model_validate(row.payload)

    def get_constraints_summary(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None:
        master = self.get_latest_master(as_of_date=as_of_date)
        if not master:
            return None
        return MacroConstraintsSummaryDTO(
            version=master.version,
            as_of_date=master.as_of_date,
            current_macro_bias=master.current_macro_bias,
            macro_mainline=master.macro_mainline,
            style_impact=master.a_share_style_impact,
            material_change=master.material_change,
            confidence=master.confidence,
        )

    def list_deltas(self, since_version: str | None = None, since_date: date | None = None) -> list[MacroDeltaDTO]:
        query = select(MacroDeltaModel)
        if since_version:
            query = query.where(MacroDeltaModel.to_version > since_version)
        if since_date:
            query = query.where(MacroDeltaModel.as_of_date >= since_date)
        rows = self.session.execute(query.order_by(MacroDeltaModel.as_of_date.desc())).scalars().all()
        return [MacroDeltaDTO.model_validate(row.payload) for row in rows]

    def list_industry_mappings(self, version: str | None = None) -> list[MacroIndustryMappingDTO]:
        query = select(MacroIndustryMappingSnapshotModel)
        if version:
            query = query.where(MacroIndustryMappingSnapshotModel.version == version)
        else:
            latest_master = self.get_latest_master()
            if not latest_master:
                return []
            query = query.where(MacroIndustryMappingSnapshotModel.version == latest_master.version)

        rows = self.session.execute(query.order_by(MacroIndustryMappingSnapshotModel.sw_l1_id.asc())).scalars().all()
        return [MacroIndustryMappingDTO.model_validate(row.payload) for row in rows]

    def list_latest_event_history(self, as_of_date: date | None = None) -> list[MacroEventHistoryDTO]:
        subq = select(
            MacroEventHistoryModel.event_id,
            func.max(MacroEventHistoryModel.event_seq).label("max_seq"),
        )
        if as_of_date:
            subq = subq.where(MacroEventHistoryModel.as_of_date <= as_of_date)
        subq = subq.group_by(MacroEventHistoryModel.event_id).subquery()

        query = (
            select(MacroEventHistoryModel)
            .join(
                subq,
                (MacroEventHistoryModel.event_id == subq.c.event_id)
                & (MacroEventHistoryModel.event_seq == subq.c.max_seq),
            )
            .order_by(MacroEventHistoryModel.created_at.desc())
        )
        rows = self.session.execute(query).scalars().all()
        return [
            MacroEventHistoryDTO(
                history_id=row.history_id,
                event_id=row.event_id,
                event_seq=row.event_seq,
                as_of_date=row.as_of_date,
                event_status=row.event_status,
                title=row.title,
                fact_summary=row.fact_summary,
                theme_type=row.theme_type,
                bias_hint=row.bias_hint,
                source_refs=row.source_refs or [],
                created_at=row.created_at,
            )
            for row in rows
        ]

    def list_event_views(
        self,
        *,
        history_ids: list[str] | None = None,
        event_ids: list[str] | None = None,
        as_of_date: date | None = None,
    ) -> list[MacroEventViewDTO]:
        query = select(MacroEventViewModel)
        if history_ids:
            query = query.where(MacroEventViewModel.history_id.in_(history_ids))
        if event_ids:
            query = query.where(MacroEventViewModel.event_id.in_(event_ids))
        if as_of_date:
            query = query.where(MacroEventViewModel.as_of_date <= as_of_date)

        rows = self.session.execute(query.order_by(MacroEventViewModel.created_at.desc())).scalars().all()
        return [
            MacroEventViewDTO(
                view_id=row.view_id,
                event_id=row.event_id,
                history_id=row.history_id,
                as_of_date=row.as_of_date,
                view_type=row.view_type,
                stance=row.stance,
                view_text=row.view_text,
                score=row.score,
                score_reason=row.score_reason,
                source_refs=row.source_refs or [],
                created_at=row.created_at,
            )
            for row in rows
        ]
