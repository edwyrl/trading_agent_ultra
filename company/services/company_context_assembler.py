from __future__ import annotations

from contracts.company_contracts import CompanyContextDTO


class CompanyContextAssembler:
    def assemble(self, payload: dict) -> CompanyContextDTO:
        """Assemble normalized company context from deterministic upstream outputs."""
        return CompanyContextDTO.model_validate(payload)
