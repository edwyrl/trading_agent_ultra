from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from contracts.confidence import ConfidenceDTO
from contracts.enums import ConfidenceLevel, IndustryScenarioBias, SourceType, SwLevel, UpdateMode
from contracts.industry_contracts import IndustryDeltaDTO, IndustryThesisCardDTO, IndustryThesisSummaryDTO
from contracts.source_refs import SourceRefDTO
from industry.prioritizer import IndustryPrioritizer
from industry.service import IndustryService
from industry.triggers import IndustryRefreshTrigger
from industry.updater import IndustryUpdater


class FakeIndustryRepository:
    def __init__(self, seed: IndustryThesisCardDTO):
        self._latest: dict[tuple[str, SwLevel], IndustryThesisCardDTO] = {(seed.industry_id, seed.sw_level): seed}
        self.deltas: list[IndustryDeltaDTO] = []
        self.weekly_candidates: list[dict] = []

    def save_snapshot(self, thesis: IndustryThesisCardDTO) -> None:
        self._latest[(thesis.industry_id, thesis.sw_level)] = thesis

    def save_delta(self, delta: IndustryDeltaDTO) -> None:
        self.deltas.append(delta)

    def get_latest(self, industry_id: str, sw_level: SwLevel) -> IndustryThesisCardDTO | None:
        return self._latest.get((industry_id, sw_level))

    def get_summary(self, industry_id: str, preferred_levels: list[SwLevel]) -> IndustryThesisSummaryDTO | None:
        for level in preferred_levels:
            thesis = self.get_latest(industry_id, level)
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
        rows = [d for d in self.deltas if d.entity_id == industry_id]
        if since_version:
            rows = [d for d in rows if d.to_version > since_version]
        return rows

    def save_weekly_candidates(self, week_key: str, candidates: list[dict]) -> None:
        _ = week_key
        self.weekly_candidates = candidates


def build_seed_thesis(*, now: datetime, industry_id: str = "801010") -> IndustryThesisCardDTO:
    return IndustryThesisCardDTO(
        version=f"{industry_id}:v1",
        as_of_date=date(2026, 3, 22),
        created_at=now - timedelta(days=3),
        industry_id=industry_id,
        industry_name="农林牧渔",
        sw_level=SwLevel.L1,
        last_news_update_at=now - timedelta(days=2),
        last_market_data_update_at=now - timedelta(days=1),
        last_full_refresh_at=now - timedelta(days=3),
        definition="行业定义",
        value_chain="产业链",
        core_drivers=["需求改善"],
        core_conflicts=["成本波动"],
        bull_case="bull",
        base_case="base",
        bear_case="bear",
        current_bias=IndustryScenarioBias.BASE,
        bias_reason="中性等待验证",
        bias_shift_risk=["政策扰动"],
        key_metrics_to_watch=["库存周转"],
        companies_to_watch=["000001.SZ"],
        latest_changes=["初始版本"],
        confidence=ConfidenceDTO(score=0.6, level=ConfidenceLevel.MEDIUM),
        source_refs=[
            SourceRefDTO(
                source_type=SourceType.INTERNAL_SUMMARY,
                title="seed",
                retrieved_at=now,
                note="test seed",
            )
        ],
        concept_tags=["国企改革"],
    )


def test_refresh_industry_thesis_market_creates_new_snapshot_and_delta() -> None:
    fixed_now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    seed = build_seed_thesis(now=fixed_now)
    repo = FakeIndustryRepository(seed)

    service = IndustryService(
        repository=repo,
        updater=IndustryUpdater(now_provider=lambda: fixed_now),
        triggers=IndustryRefreshTrigger(now_provider=lambda: fixed_now),
    )

    updated = service.refresh_industry_thesis(seed.industry_id, UpdateMode.MARKET, sw_level=SwLevel.L1)

    assert updated is not None
    assert updated.version != seed.version
    assert len(repo.deltas) == 1
    assert repo.deltas[0].from_version == seed.version
    assert repo.deltas[0].to_version == updated.version


def test_get_industry_thesis_auto_refresh_runs_when_trigger_hit() -> None:
    fixed_now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    seed = build_seed_thesis(now=fixed_now)
    repo = FakeIndustryRepository(seed)

    # Force full refresh by setting very old full refresh timestamp.
    seed = seed.model_copy(update={"last_full_refresh_at": fixed_now - timedelta(days=10)})
    repo.save_snapshot(seed)

    service = IndustryService(
        repository=repo,
        updater=IndustryUpdater(now_provider=lambda: fixed_now),
        triggers=IndustryRefreshTrigger(now_provider=lambda: fixed_now),
    )

    thesis = service.get_industry_thesis(seed.industry_id, SwLevel.L1, as_of_date=date(2026, 3, 22), auto_refresh=True)

    assert thesis is not None
    assert thesis.version != seed.version
    assert repo.deltas
    assert repo.deltas[-1].material_change.material_change is True


def test_get_weekly_refresh_candidates_returns_ranked_list() -> None:
    fixed_now = datetime(2026, 3, 22, 10, 0, tzinfo=UTC)
    seed = build_seed_thesis(now=fixed_now)
    repo = FakeIndustryRepository(seed)

    service = IndustryService(
        repository=repo,
        prioritizer=IndustryPrioritizer(),
    )

    signals = [
        {
            "industry_id": f"80{i:04d}",
            "rotation_strength": 0.9 - i * 0.05,
            "news_heat": 0.8 - i * 0.03,
            "portfolio_relevance": 0.5,
            "change_frequency": 0.4,
            "days_since_full_refresh": 7 + i,
        }
        for i in range(10)
    ]

    ranked = service.get_weekly_refresh_candidates(limit=8, week_key="2026-W12", candidate_signals=signals)

    assert len(ranked) == 10
    assert sum(1 for row in ranked if row["selected"]) == 8
    assert repo.weekly_candidates
    assert ranked[0]["score"] >= ranked[-1]["score"]
