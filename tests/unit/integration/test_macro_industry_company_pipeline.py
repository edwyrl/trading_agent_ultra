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
    EntityType,
    IndustryScenarioBias,
    MacroBiasTag,
    MappingDirection,
    MaterialChangeLevel,
    SourceType,
    SwLevel,
    UpdateMode,
)
from contracts.integration_contracts import RecheckQueueItemDTO
from contracts.industry_contracts import IndustryThesisSummaryDTO
from contracts.macro_contracts import MacroConstraintsSummaryDTO, MacroDeltaDTO, MacroIndustryMappingDTO
from contracts.material_change import MaterialChangeDTO
from contracts.source_refs import SourceRefDTO
from integration.company_context_orchestrator import CompanyContextOrchestrator
from integration.industry_recheck_orchestrator import IndustryRecheckOrchestrator
from integration.linkage_service import MacroIndustryLinkageService
from integration.recheck_executor import IndustryRecheckExecutor


class InMemoryIntegrationRepository:
    def __init__(self) -> None:
        self.items: dict[str, RecheckQueueItemDTO] = {}

    def enqueue_recheck(self, item: RecheckQueueItemDTO, reason_codes: list[str], triggered_by_macro_version: str) -> None:
        item.reason_codes = reason_codes
        item.triggered_by_macro_version = triggered_by_macro_version
        self.items[item.queue_id] = item

    def list_pending_rechecks(self) -> list[RecheckQueueItemDTO]:
        return [item for item in self.items.values() if item.status == "PENDING"]

    def update_recheck_status(self, queue_id: str, status: str, note: str | None = None) -> None:
        _ = note
        if queue_id in self.items:
            self.items[queue_id].status = status


class StubMacroService:
    def get_macro_delta(self, since_version: str | None = None, since_date: date | None = None) -> list[MacroDeltaDTO]:
        _ = (since_version, since_date)
        return [
            MacroDeltaDTO(
                delta_id="macro-delta:v1",
                entity_type=EntityType.MACRO_MASTER,
                entity_id="macro_master",
                from_version="v0",
                to_version="macro-v1",
                as_of_date=date(2026, 3, 22),
                changed_fields=["current_macro_bias"],
                summary="test",
                reasons=["test"],
                impact_scope=["industry"],
                material_change=MaterialChangeDTO(
                    material_change=True,
                    level=MaterialChangeLevel.MEDIUM,
                    reasons=["test"],
                ),
                source_refs=[
                    SourceRefDTO(
                        source_type=SourceType.INTERNAL_SUMMARY,
                        title="test-source",
                        retrieved_at=datetime.now(UTC),
                    )
                ],
                created_at=datetime.now(UTC),
            )
        ]

    def get_macro_industry_mappings(self, version: str | None = None) -> list[MacroIndustryMappingDTO]:
        _ = version
        return [
            MacroIndustryMappingDTO(
                sw_l1_id="801010",
                sw_l1_name="农林牧渔",
                direction=MappingDirection.POSITIVE,
                score=0.6,
                reason="macro positive",
            )
        ]

    def get_macro_constraints_summary(self, as_of_date: date | None = None) -> MacroConstraintsSummaryDTO | None:
        _ = as_of_date
        return MacroConstraintsSummaryDTO(
            version="macro-v1",
            as_of_date=date(2026, 3, 22),
            current_macro_bias=[MacroBiasTag.POLICY_EXPECTATION_DOMINANT],
            macro_mainline="政策预期主导",
            style_impact="成长偏强",
            material_change=MaterialChangeDTO(
                material_change=True,
                level=MaterialChangeLevel.MEDIUM,
                reasons=["test"],
            ),
            confidence=ConfidenceDTO(score=0.7, level=ConfidenceLevel.MEDIUM),
        )


class StubIndustryService:
    def __init__(self) -> None:
        self.refresh_calls: list[tuple[str, UpdateMode]] = []

    def refresh_industry_thesis(self, industry_id: str, mode: UpdateMode):
        self.refresh_calls.append((industry_id, mode))

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
            company_fit_questions=["fit-a"],
            confidence=ConfidenceDTO(score=0.65, level=ConfidenceLevel.MEDIUM),
        )


class StubCompanyRepository:
    def __init__(self) -> None:
        self.contexts: list[CompanyContextDTO] = []
        self.runs: list[dict] = []

    def save_company_context(self, context: CompanyContextDTO) -> None:
        self.contexts.append(context)

    def get_latest_context(self, ts_code: str, trade_date: date | None = None) -> CompanyContextDTO | None:
        _ = (ts_code, trade_date)
        return self.contexts[-1] if self.contexts else None

    def save_analysis_run(self, payload: dict) -> None:
        self.runs.append(payload)

    def save_analyst_output(self, payload: dict) -> None:
        _ = payload


def test_macro_industry_company_pipeline_smoke() -> None:
    macro_service = StubMacroService()
    integration_repo = InMemoryIntegrationRepository()
    linkage = MacroIndustryLinkageService(
        macro_service=macro_service,
        orchestrator=IndustryRecheckOrchestrator(repository=integration_repo),
    )

    queued = linkage.enqueue_from_recent_deltas()
    assert len(queued) == 1

    industry_service = StubIndustryService()
    executor = IndustryRecheckExecutor(
        repository=integration_repo,
        industry_service=industry_service,
        initial_delay_seconds=0.0,
    )
    stats = executor.run_pending()
    assert stats == {"total": 1, "done": 1, "failed": 0}

    company_repo = StubCompanyRepository()
    company_orchestrator = CompanyContextOrchestrator(
        company_data_service=CompanyDataService(),
        metrics_tools=MetricsTools(),
        concept_tag_extractor=ConceptTagExtractor(),
        macro_constraints_tool=MacroConstraintsTool(provider=macro_service),
        industry_summary_tool=IndustrySummaryTool(provider=industry_service),
        assembler=CompanyContextAssembler(),
        repository=company_repo,
    )

    context = company_orchestrator.build(ts_code="000001.SZ", trade_date=date(2026, 3, 22))
    assert context.macro_constraints_summary.industry_mapping_signal_for_company.direction == MappingDirection.POSITIVE
    assert context.industry_thesis_summary.current_bias == IndustryScenarioBias.BASE
    assert len(company_repo.runs) == 1
    assert company_repo.runs[0]["status"] == "SUCCESS"
