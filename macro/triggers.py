from __future__ import annotations


class MacroTriggers:
    def is_material_change(self, changed_fields: list[str]) -> bool:
        return bool(changed_fields)
