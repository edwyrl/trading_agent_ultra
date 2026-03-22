from __future__ import annotations

from contracts.enums import UpdateMode
from contracts.industry_contracts import IndustryThesisSummaryDTO
from contracts.integration_contracts import IndustryRecheckDecisionDTO
from contracts.macro_contracts import MacroDeltaDTO


def decide_industry_recheck(
    macro_delta: MacroDeltaDTO,
    industry_summary: IndustryThesisSummaryDTO,
) -> IndustryRecheckDecisionDTO:
    # v1 deterministic skeleton: if material change, recommend MARKET refresh, else no action.
    if macro_delta.material_change.material_change:
        return IndustryRecheckDecisionDTO(
            sw_l1_id=industry_summary.industry_id,
            recheck_required=True,
            recommended_mode=UpdateMode.MARKET,
            reason_codes=["MACRO_MATERIAL_CHANGE"],
            triggered_by_macro_version=macro_delta.to_version,
        )

    return IndustryRecheckDecisionDTO(
        sw_l1_id=industry_summary.industry_id,
        recheck_required=False,
        recommended_mode=None,
        reason_codes=["NO_ACTION"],
        triggered_by_macro_version=macro_delta.to_version,
    )
