from __future__ import annotations

from datetime import UTC, date, datetime

from contracts.company_contracts import (
    CompanyContextDTO,
    ComputedMetricsDTO,
    DataRefDTO,
    IndustryMappingSignalForCompanyDTO,
    IndustryThesisForCompanyDTO,
    MacroConstraintsForCompanyDTO,
    VersionRefDTO,
)
from contracts.confidence import ConfidenceDTO
from contracts.enums import ConfidenceLevel, IndustryScenarioBias, MacroBiasTag, SwLevel
from contracts.industry_contracts import IndustryThesisSummaryDTO
from contracts.macro_contracts import MacroConstraintsSummaryDTO
from contracts.material_change import MaterialChangeDTO


class CompanyContextAssembler:
    def assemble(self, payload: dict) -> CompanyContextDTO:
        """Assemble normalized company context from deterministic upstream outputs."""
        return CompanyContextDTO.model_validate(payload)

    def assemble_from_components(
        self,
        *,
        ts_code: str,
        company_name: str,
        trade_date: date,
        sw_l1_id: str | None,
        sw_l1_name: str | None,
        sw_l2_id: str | None,
        sw_l2_name: str | None,
        sw_l3_id: str | None,
        sw_l3_name: str | None,
        primary_industry_level: SwLevel,
        concept_tags: list[str],
        computed_metrics: ComputedMetricsDTO,
        market_data_ref: DataRefDTO,
        financial_data_ref: DataRefDTO,
        news_data_ref: DataRefDTO,
        macro_summary: MacroConstraintsSummaryDTO | None,
        mapping_signal: IndustryMappingSignalForCompanyDTO | None,
        industry_summary: IndustryThesisSummaryDTO | None,
    ) -> CompanyContextDTO:
        macro_payload = self._build_macro_constraints_payload(
            macro_summary=macro_summary,
            mapping_signal=mapping_signal,
        )
        industry_payload = self._build_industry_summary_payload(industry_summary)

        macro_ref = VersionRefDTO(
            version=macro_summary.version if macro_summary else "macro:none",
            as_of_date=macro_summary.as_of_date if macro_summary else trade_date,
        )
        industry_ref = VersionRefDTO(
            version=industry_summary.version if industry_summary else "industry:none",
            as_of_date=industry_summary.as_of_date if industry_summary else trade_date,
        )

        context_version = f"company-context:{ts_code}:{trade_date:%Y%m%d}:01"
        return CompanyContextDTO(
            version=context_version,
            context_version=context_version,
            ts_code=ts_code,
            company_name=company_name,
            trade_date=trade_date,
            sw_l1_name=sw_l1_name,
            sw_l2_name=sw_l2_name,
            sw_l3_name=sw_l3_name,
            sw_l1_id=sw_l1_id,
            sw_l2_id=sw_l2_id,
            sw_l3_id=sw_l3_id,
            primary_industry_level=primary_industry_level,
            concept_tags=concept_tags[:10],
            as_of_date=trade_date,
            context_as_of_date=trade_date,
            market_data_ref=market_data_ref,
            financial_data_ref=financial_data_ref,
            news_data_ref=news_data_ref,
            computed_metrics=computed_metrics,
            macro_constraints_summary=macro_payload,
            industry_thesis_summary=industry_payload,
            macro_context_ref=macro_ref,
            industry_thesis_ref=industry_ref,
            source_refs=[],
        )

    def _build_macro_constraints_payload(
        self,
        *,
        macro_summary: MacroConstraintsSummaryDTO | None,
        mapping_signal: IndustryMappingSignalForCompanyDTO | None,
    ) -> MacroConstraintsForCompanyDTO:
        if macro_summary is None:
            fallback_signal = mapping_signal or IndustryMappingSignalForCompanyDTO(
                sw_l1_id="UNKNOWN",
                direction="NEUTRAL",
                reason="No macro summary available.",
            )
            return MacroConstraintsForCompanyDTO(
                macro_biases=[MacroBiasTag.POLICY_EXPECTATION_DOMINANT],
                macro_mainline="暂无宏观摘要，维持中性约束。",
                style_impact="中性",
                industry_mapping_signal_for_company=fallback_signal,
                material_change=MaterialChangeDTO(material_change=False, level="NONE", reasons=[]),
                reasoning_summary="Macro summary unavailable in current run.",
                confidence=ConfidenceDTO(score=0.3, level=ConfidenceLevel.LOW, note="Fallback payload"),
            )

        signal = mapping_signal or IndustryMappingSignalForCompanyDTO(
            sw_l1_id="UNKNOWN",
            direction="NEUTRAL",
            reason="No explicit mapping.",
        )
        return MacroConstraintsForCompanyDTO(
            macro_biases=macro_summary.current_macro_bias,
            macro_mainline=macro_summary.macro_mainline,
            style_impact=macro_summary.style_impact,
            industry_mapping_signal_for_company=signal,
            material_change=macro_summary.material_change,
            reasoning_summary=macro_summary.macro_mainline,
            confidence=macro_summary.confidence,
        )

    def _build_industry_summary_payload(
        self,
        industry_summary: IndustryThesisSummaryDTO | None,
    ) -> IndustryThesisForCompanyDTO:
        if industry_summary is None:
            return IndustryThesisForCompanyDTO(
                industry_level_used=SwLevel.L1,
                current_bias=IndustryScenarioBias.BASE,
                bull_base_bear_summary="暂无行业摘要，维持 base 假设。",
                key_drivers=[],
                key_risks=[],
                company_fit_questions=["行业摘要缺失时，公司核心假设是否仍成立？"],
                confidence=ConfidenceDTO(score=0.3, level=ConfidenceLevel.LOW, note="Fallback payload"),
            )

        return IndustryThesisForCompanyDTO(
            industry_level_used=industry_summary.sw_level,
            current_bias=industry_summary.current_bias,
            bull_base_bear_summary=industry_summary.bull_base_bear_summary,
            key_drivers=industry_summary.key_drivers,
            key_risks=industry_summary.key_risks,
            company_fit_questions=industry_summary.company_fit_questions,
            confidence=industry_summary.confidence,
        )
