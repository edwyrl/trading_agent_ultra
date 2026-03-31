from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from shared.llm.models import ModelSpec, RoleModelSpec
from shared.llm.registry import LLMRegistry


class ResolvedModelRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: ModelSpec
    role: str | None = None
    role_spec: RoleModelSpec | None = None


class LLMRouter:
    def __init__(self, registry: LLMRegistry) -> None:
        self.registry = registry

    def resolve(self, *, model_id: str | None = None, role: str | None = None) -> ResolvedModelRoute:
        if not model_id and not role:
            raise ValueError("either model_id or role must be provided")

        if model_id:
            model = self.registry.get_model(model_id)
            role_spec = self.registry.get_role(role) if role else None
            return ResolvedModelRoute(model=model, role=role, role_spec=role_spec)

        assert role is not None
        role_spec = self.registry.get_role(role)
        model = self.registry.get_model(role_spec.model_id)
        return ResolvedModelRoute(model=model, role=role_spec.role, role_spec=role_spec)
