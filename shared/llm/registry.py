from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from shared.llm.models import ModelSpec, RoleModelSpec


class LLMRegistry:
    def __init__(self, *, models: dict[str, ModelSpec], roles: dict[str, RoleModelSpec]) -> None:
        self._models = models
        self._roles = roles

    @classmethod
    def from_yaml(cls, path: str | Path) -> "LLMRegistry":
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "LLMRegistry":
        model_rows = raw.get("models", [])
        role_rows = raw.get("roles", {})

        models: dict[str, ModelSpec] = {}
        for row in model_rows:
            spec = ModelSpec.model_validate(row)
            if spec.model_id in models:
                raise ValueError(f"duplicated model_id: {spec.model_id}")
            models[spec.model_id] = spec

        roles: dict[str, RoleModelSpec] = {}
        for role_name, row in role_rows.items():
            spec = RoleModelSpec.model_validate({"role": role_name, **row})
            if spec.model_id not in models:
                raise ValueError(
                    f"role `{spec.role}` points to unknown model `{spec.model_id}`"
                )
            roles[spec.role] = spec

        return cls(models=models, roles=roles)

    def list_models(self) -> list[ModelSpec]:
        return list(self._models.values())

    def list_roles(self) -> list[RoleModelSpec]:
        return list(self._roles.values())

    def get_model(self, model_id: str) -> ModelSpec:
        try:
            return self._models[model_id]
        except KeyError as exc:
            raise KeyError(f"unknown model_id: {model_id}") from exc

    def get_role(self, role: str) -> RoleModelSpec:
        try:
            return self._roles[role]
        except KeyError as exc:
            raise KeyError(f"unknown role: {role}") from exc
