from __future__ import annotations

from datetime import UTC, date, datetime

from contracts.macro_contracts import (
    MacroConstraintsSummaryDTO,
    MacroDeltaDTO,
    MacroIndustryMappingDTO,
    MacroMasterCardDTO,
    MacroThemeCardSummaryDTO,
)
from contracts.source_refs import SourceRefDTO
from macro.retriever import MacroEvent
from macro.service import MacroService
from macro.updater import MacroUpdater


class InMemoryMacroRepository:
    def __init__(self) -> None:
        self.master_snapshots: list[MacroMasterCardDTO] = []
        self.theme_snapshots: list[tuple[str, MacroThemeCardSummaryDTO]] = []
        self.deltas: list[MacroDeltaDTO] = []
        self.mappings: list[tuple[str, date, MacroIndustryMappingDTO]] = []
        self.run_logs: list[dict] = []

    def save_master_snapshot(self, master: MacroMasterCardDTO) -> None:
        self.master_snapshots.append(master)

    def save_theme_snapshot(self, theme: MacroThemeCardSummaryDTO, version: str) -> None:
        self.theme_snapshots.append((version, theme))

    def save_delta(self, delta: MacroDeltaDTO) -> None:
        self.deltas.append(delta)

    def save_industry_mapping(self, version: str, mapping: MacroIndustryMappingDTO, as_of_date: date) -> None:
        self.mappings.append((version, as_of_date, mapping))

    def save_run_log(self, payload: dict) -> None:
        self.run_logs.append(payload)

    def get_latest_master(self, as_of_date: date | None = None) -> MacroMasterCardDTO | None:
        if not self.master_snapshots:
            return None
        if as_of_date is None:
            return self.master_snapshots[-1]
        candidates = [m for m in self.master_snapshots if m.as_of_date <= as_of_date]
        if not candidates:
            return None
        return sorted(candidates, key=lambda x: x.as_of_date)[-1]

    def get_constraints_summary(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None:
        latest = self.get_latest_master(as_of_date=as_of_date)
        if latest is None:
            return None
        return MacroConstraintsSummaryDTO(
            version=latest.version,
            as_of_date=latest.as_of_date,
            current_macro_bias=latest.current_macro_bias,
            macro_mainline=latest.macro_mainline,
            style_impact=latest.a_share_style_impact,
            material_change=latest.material_change,
            confidence=latest.confidence,
        )

    def list_deltas(self, since_version: str | None = None, since_date: date | None = None) -> list[MacroDeltaDTO]:
        _ = (since_version, since_date)
        return self.deltas


def _event(event_id: str, title: str, summary: str, theme_type: str, bias_hint: str | None = None) -> MacroEvent:
    payload = {
        "event_id": event_id,
        "title": title,
        "summary": summary,
        "theme_type": theme_type,
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
    if bias_hint:
        payload["bias_hint"] = bias_hint
    return MacroEvent.model_validate(payload)


def test_macro_updater_creates_master_theme_delta_mapping() -> None:
    repo = InMemoryMacroRepository()
    updater = MacroUpdater(repository=repo)

    events = [
        _event("evt-1", "央行操作维持流动性", "流动性改善，风险偏好修复", "DOMESTIC_AGGREGATE", "LIQUIDITY_DOMINANT"),
        _event("evt-2", "政策会议强化预期", "政策预期提升，顺周期板块活跃", "POLICY_ENVIRONMENT"),
    ]

    master = updater.run_daily_incremental_update(as_of_date=date(2026, 3, 22), events=events)

    assert master.version.startswith("macro-master:20260322:")
    assert master.material_change.material_change is True
    assert len(repo.theme_snapshots) == 2
    assert len(repo.deltas) == 1
    assert len(repo.mappings) > 0
    assert repo.run_logs[-1]["status"] == "SUCCESS"


def test_macro_updater_with_no_new_events_keeps_bias_and_no_material_change() -> None:
    repo = InMemoryMacroRepository()
    updater = MacroUpdater(repository=repo)

    first = updater.run_daily_incremental_update(
        as_of_date=date(2026, 3, 22),
        events=[
            _event("evt-1", "海外扰动上行", "外部扰动增加不确定性", "OVERSEAS_MAPPING", "EXTERNAL_DISTURBANCE_DOMINANT"),
        ],
    )
    second = updater.run_daily_incremental_update(as_of_date=date(2026, 3, 23), events=[])

    assert second.current_macro_bias == first.current_macro_bias
    assert second.material_change.material_change is False
    assert len(repo.theme_snapshots) == 1
    assert len(repo.master_snapshots) == 2


def test_macro_service_can_run_incremental_update() -> None:
    repo = InMemoryMacroRepository()
    service = MacroService(repository=repo)

    master = service.run_daily_incremental_update(
        as_of_date=date(2026, 3, 24),
        events=[
            _event("evt-3", "风格偏好回暖", "主题活跃度提升", "MARKET_STYLE", "THEMATIC_RISK_APPETITE_DOMINANT"),
        ],
    )

    assert service.get_macro_master_card(as_of_date=date(2026, 3, 24)) is not None
    assert master.version == repo.master_snapshots[-1].version


def test_source_ref_structure_is_serializable() -> None:
    ref = SourceRefDTO(source_type="NEWS", title="test", retrieved_at=datetime.now(UTC))
    assert ref.model_dump(mode="json")["title"] == "test"
