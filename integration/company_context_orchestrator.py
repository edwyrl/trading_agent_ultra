from __future__ import annotations

from datetime import date
import uuid

from company.repository import CompanyRepository
from company.services.company_context_assembler import CompanyContextAssembler
from company.services.company_data_service import CompanyDataService
from company.services.concept_tag_extractor import ConceptTagExtractor
from company.tools.industry_summary_tool import IndustrySummaryTool
from company.tools.macro_constraints_tool import MacroConstraintsTool
from company.tools.metrics_tools import MetricsTools
from contracts.company_contracts import CompanyContextDTO, DataRefDTO
from contracts.enums import SwLevel
from shared.logging import get_logger


class CompanyContextOrchestrator:
    """Build company_context from deterministic inputs + macro/industry summaries."""

    def __init__(
        self,
        *,
        company_data_service: CompanyDataService,
        metrics_tools: MetricsTools,
        concept_tag_extractor: ConceptTagExtractor,
        macro_constraints_tool: MacroConstraintsTool,
        industry_summary_tool: IndustrySummaryTool,
        assembler: CompanyContextAssembler,
        repository: CompanyRepository | None = None,
    ):
        self.company_data_service = company_data_service
        self.metrics_tools = metrics_tools
        self.concept_tag_extractor = concept_tag_extractor
        self.macro_constraints_tool = macro_constraints_tool
        self.industry_summary_tool = industry_summary_tool
        self.assembler = assembler
        self.repository = repository
        self.logger = get_logger(__name__)

    def build(self, ts_code: str, trade_date: date) -> CompanyContextDTO:
        run_id = f"company-run:{ts_code}:{trade_date:%Y%m%d}:{uuid.uuid4().hex[:8]}"
        pending_context_version = f"company-context:{ts_code}:{trade_date:%Y%m%d}:pending"

        self.logger.info("company_context_build_start run_id=%s ts_code=%s trade_date=%s", run_id, ts_code, trade_date)
        try:
            bundle = self.company_data_service.fetch_company_bundle(ts_code=ts_code, trade_date=trade_date)

            computed_metrics = self.metrics_tools.compute(
                market_data=bundle.get("market_data", {}),
                financial_data=bundle.get("financial_data", {}),
            )
            concept_tags = self.concept_tag_extractor.extract(bundle.get("news_texts", []), limit=10)

            macro_summary = self.macro_constraints_tool.get(as_of_date=trade_date)
            sw_l1_id = bundle.get("sw_l1_id") or "UNKNOWN"
            mapping_signal = self.macro_constraints_tool.get_mapping_signal(
                sw_l1_id=sw_l1_id,
                version=macro_summary.version if macro_summary else None,
            )

            industry_lookup_id = self._pick_industry_lookup_id(bundle)
            industry_summary = None
            if industry_lookup_id:
                industry_summary = self.industry_summary_tool.get(
                    industry_id=industry_lookup_id,
                    preferred_levels=[SwLevel.L3, SwLevel.L2, SwLevel.L1],
                )

            context = self.assembler.assemble_from_components(
                ts_code=bundle.get("ts_code", ts_code),
                company_name=bundle.get("company_name", ts_code),
                trade_date=bundle.get("trade_date", trade_date),
                sw_l1_id=bundle.get("sw_l1_id"),
                sw_l1_name=bundle.get("sw_l1_name"),
                sw_l2_id=bundle.get("sw_l2_id"),
                sw_l2_name=bundle.get("sw_l2_name"),
                sw_l3_id=bundle.get("sw_l3_id"),
                sw_l3_name=bundle.get("sw_l3_name"),
                primary_industry_level=bundle.get("primary_industry_level", SwLevel.L1),
                concept_tags=concept_tags,
                computed_metrics=computed_metrics,
                market_data_ref=DataRefDTO.model_validate(bundle["market_data_ref"]),
                financial_data_ref=DataRefDTO.model_validate(bundle["financial_data_ref"]),
                news_data_ref=DataRefDTO.model_validate(bundle["news_data_ref"]),
                macro_summary=macro_summary,
                mapping_signal=mapping_signal,
                industry_summary=industry_summary,
            )

            if self.repository is not None:
                self.repository.save_company_context(context)
                self._save_analysis_run(
                    {
                        "run_id": run_id,
                        "ts_code": ts_code,
                        "trade_date": trade_date,
                        "context_version": context.context_version,
                        "status": "SUCCESS",
                        "note": None,
                    }
                )

            self.logger.info(
                "company_context_build_done run_id=%s ts_code=%s context_version=%s",
                run_id,
                ts_code,
                context.context_version,
            )
            return context
        except Exception as exc:
            self._save_analysis_run(
                {
                    "run_id": run_id,
                    "ts_code": ts_code,
                    "trade_date": trade_date,
                    "context_version": pending_context_version,
                    "status": "FAILED",
                    "note": str(exc),
                }
            )
            self.logger.error(
                "company_context_build_failed run_id=%s ts_code=%s error=%s",
                run_id,
                ts_code,
                exc,
            )
            raise

    def _pick_industry_lookup_id(self, bundle: dict) -> str | None:
        return bundle.get("sw_l3_id") or bundle.get("sw_l2_id") or bundle.get("sw_l1_id")

    def _save_analysis_run(self, payload: dict) -> None:
        if self.repository is None:
            return
        try:
            self.repository.save_analysis_run(payload)
        except Exception as exc:  # pragma: no cover - runtime safety only
            self.logger.error("company_analysis_run_persist_failed run_id=%s error=%s", payload.get("run_id"), exc)
