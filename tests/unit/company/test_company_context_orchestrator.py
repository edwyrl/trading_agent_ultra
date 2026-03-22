from __future__ import annotations

from datetime import UTC, date, datetime

from company.services.company_context_assembler import CompanyContextAssembler
from company.services.company_data_service import CompanyDataService
from company.services.concept_tag_extractor import ConceptTagExtractor
from company.tools.industry_summary_tool import IndustrySummaryTool
from company.tools.macro_constraints_tool import MacroConstraintsTool
from company.tools.metrics_tools import MetricsTools
from contracts.company_contracts import CompanyContextDTO
from contracts.confidence import ConfidenceDTO
from contracts.enums import (
    ConfidenceLevel,
    IndustryScenarioBias,
    MacroBiasTag,
    MappingDirection,
    MaterialChangeLevel,
    SwLevel,
)
from contracts.industry_contracts import IndustryThesisSummaryDTO
from contracts.macro_contracts import MacroConstraintsSummaryDTO, MacroIndustryMappingDTO
from contracts.material_change import MaterialChangeDTO
from integration.company_context_orchestrator import CompanyContextOrchestrator


class StubMacroProvider:
    def get_macro_constraints_summary(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None:
        _ = as_of_date
        return MacroConstraintsSummaryDTO(
            version="macro-v1",
            as_of_date=date(2026, 3, 22),
            current_macro_bias=[MacroBiasTag.POLICY_EXPECTATION_DOMINANT],
            macro_mainline="政策预期偏强",
            style_impact="成长风格活跃",
            material_change=MaterialChangeDTO(material_change=True, level=MaterialChangeLevel.MEDIUM, reasons=["test"]),
            confidence=ConfidenceDTO(score=0.7, level=ConfidenceLevel.MEDIUM),
        )

    def get_macro_industry_mappings(self, version: str | None = None) -> list[MacroIndustryMappingDTO]:
        _ = version
        return [
            MacroIndustryMappingDTO(
                sw_l1_id="801010",
                sw_l1_name="农林牧渔",
                direction=MappingDirection.POSITIVE,
                score=0.5,
                reason="macro test",
            )
        ]


class StubIndustryProvider:
    def get_industry_thesis_summary(
        self,
        industry_id: str,
        preferred_levels: list[SwLevel] | None = None,
    ) -> IndustryThesisSummaryDTO | None:
        _ = preferred_levels
        return IndustryThesisSummaryDTO(
            version=f"industry-v1:{industry_id}",
            as_of_date=date(2026, 3, 22),
            industry_id=industry_id,
            industry_name="农林牧渔",
            sw_level=SwLevel.L1,
            current_bias=IndustryScenarioBias.BASE,
            bull_base_bear_summary="bull/base/bear",
            key_drivers=["driver-a"],
            key_risks=["risk-a"],
            company_fit_questions=["question-a"],
            confidence=ConfidenceDTO(score=0.66, level=ConfidenceLevel.MEDIUM),
        )


class StubCompanyRepository:
    def __init__(self) -> None:
        self.saved: CompanyContextDTO | None = None

    def save_company_context(self, context: CompanyContextDTO) -> None:
        self.saved = context

    def get_latest_context(self, ts_code: str, trade_date: date | None = None) -> CompanyContextDTO | None:
        _ = (ts_code, trade_date)
        return self.saved

    def save_analysis_run(self, payload: dict) -> None:
        _ = payload

    def save_analyst_output(self, payload: dict) -> None:
        _ = payload


class StubTagExtractor(ConceptTagExtractor):
    def extract(self, text_blobs: list[str], limit: int = 10) -> list[str]:
        _ = text_blobs
        return ["国企改革", "高分红"][:limit]


def test_company_context_orchestrator_builds_and_saves_context() -> None:
    repo = StubCompanyRepository()

    orchestrator = CompanyContextOrchestrator(
        company_data_service=CompanyDataService(),
        metrics_tools=MetricsTools(),
        concept_tag_extractor=StubTagExtractor(),
        macro_constraints_tool=MacroConstraintsTool(provider=StubMacroProvider()),
        industry_summary_tool=IndustrySummaryTool(provider=StubIndustryProvider()),
        assembler=CompanyContextAssembler(),
        repository=repo,
    )

    context = orchestrator.build(ts_code="000001.SZ", trade_date=date(2026, 3, 22))

    assert context.ts_code == "000001.SZ"
    assert context.macro_context_ref.version == "macro-v1"
    assert context.industry_thesis_summary.current_bias == IndustryScenarioBias.BASE
    assert context.macro_constraints_summary.industry_mapping_signal_for_company.direction == MappingDirection.POSITIVE
    assert repo.saved is not None
    assert repo.saved.context_version == context.context_version
    assert context.computed_metrics.highlight_flags == []


def test_company_context_uses_fallbacks_when_macro_and_industry_missing() -> None:
    class EmptyMacroProvider(StubMacroProvider):
        def get_macro_constraints_summary(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None:
            _ = as_of_date
            return None

        def get_macro_industry_mappings(self, version: str | None = None) -> list[MacroIndustryMappingDTO]:
            _ = version
            return []

    class EmptyIndustryProvider(StubIndustryProvider):
        def get_industry_thesis_summary(
            self,
            industry_id: str,
            preferred_levels: list[SwLevel] | None = None,
        ) -> IndustryThesisSummaryDTO | None:
            _ = (industry_id, preferred_levels)
            return None

    orchestrator = CompanyContextOrchestrator(
        company_data_service=CompanyDataService(),
        metrics_tools=MetricsTools(),
        concept_tag_extractor=StubTagExtractor(),
        macro_constraints_tool=MacroConstraintsTool(provider=EmptyMacroProvider()),
        industry_summary_tool=IndustrySummaryTool(provider=EmptyIndustryProvider()),
        assembler=CompanyContextAssembler(),
        repository=None,
    )

    context = orchestrator.build(ts_code="000001.SZ", trade_date=date(2026, 3, 22))
    assert context.macro_constraints_summary.confidence.level == ConfidenceLevel.LOW
    assert context.industry_thesis_summary.confidence.level == ConfidenceLevel.LOW
    assert context.industry_thesis_summary.current_bias == IndustryScenarioBias.BASE
    assert context.macro_constraints_summary.industry_mapping_signal_for_company.direction == MappingDirection.NEUTRAL
    assert context.context_as_of_date == date(2026, 3, 22)
