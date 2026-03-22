from __future__ import annotations

from contracts.enums import MacroBiasTag, MaterialChangeLevel, MappingDirection
from contracts.material_change import MaterialChangeDTO
from contracts.macro_contracts import MacroIndustryMappingDTO, MacroMasterCardDTO

class MacroTriggers:
    def is_material_change(self, changed_fields: list[str]) -> bool:
        return bool(changed_fields)

    def evaluate_material_change(
        self,
        previous_master: MacroMasterCardDTO | None,
        new_biases: list[MacroBiasTag],
        changed_theme_count: int,
        new_mappings: list[MacroIndustryMappingDTO],
    ) -> MaterialChangeDTO:
        if previous_master is None:
            return MaterialChangeDTO(
                material_change=True,
                level=MaterialChangeLevel.LOW,
                reasons=["INITIAL_BASELINE_CREATED"],
            )

        reasons: list[str] = []
        level = MaterialChangeLevel.NONE
        material_change = False

        if previous_master.current_macro_bias != new_biases:
            material_change = True
            level = MaterialChangeLevel.HIGH
            reasons.append("BIAS_SET_CHANGED")

        if changed_theme_count >= 2:
            material_change = True
            if level != MaterialChangeLevel.HIGH:
                level = MaterialChangeLevel.MEDIUM
            reasons.append("MULTI_THEME_UPDATED")

        mapping_sign = {m.sw_l1_id: m.direction for m in new_mappings}
        old_sign = {}
        for sw_l1_id in previous_master.sw_l1_positive:
            old_sign[sw_l1_id] = MappingDirection.POSITIVE
        for sw_l1_id in previous_master.sw_l1_negative:
            old_sign[sw_l1_id] = MappingDirection.NEGATIVE

        flips = 0
        for sw_l1_id, direction in mapping_sign.items():
            if sw_l1_id in old_sign and old_sign[sw_l1_id] != direction:
                flips += 1
        if flips >= 2:
            material_change = True
            if level == MaterialChangeLevel.NONE:
                level = MaterialChangeLevel.MEDIUM
            reasons.append("INDUSTRY_MAPPING_FLIP")

        if not material_change:
            reasons.append("NO_SIGNIFICANT_CHANGE")

        return MaterialChangeDTO(
            material_change=material_change,
            level=level,
            reasons=reasons,
        )
