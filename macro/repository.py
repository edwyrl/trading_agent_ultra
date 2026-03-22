from __future__ import annotations

from datetime import date
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from contracts.macro_contracts import (
    MacroConstraintsSummaryDTO,
    MacroDeltaDTO,
    MacroIndustryMappingDTO,
    MacroMasterCardDTO,
    MacroThemeCardSummaryDTO,
)
from macro.models import (
    MacroDeltaModel,
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

    def get_latest_master(self, as_of_date: date | None = None) -> MacroMasterCardDTO | None: ...

    def get_constraints_summary(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None: ...

    def list_deltas(self, since_version: str | None = None, since_date: date | None = None) -> list[MacroDeltaDTO]: ...


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
