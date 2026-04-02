from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LLMProvider(StrEnum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOONSHOT = "moonshot"
    SILICONFLOW = "siliconflow"


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    provider: LLMProvider
    api_model: str
    capabilities: list[str] = Field(default_factory=list)
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    description: str = ""

    @model_validator(mode="after")
    def _validate_tokens(self) -> "ModelSpec":
        if self.max_input_tokens is not None and self.max_input_tokens <= 0:
            raise ValueError("max_input_tokens must be positive")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        return self


class RoleModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    model_id: str
    temperature: float | None = None
    max_output_tokens: int | None = None
    system_prompt: str | None = None

    @model_validator(mode="after")
    def _validate_role_params(self) -> "RoleModelSpec":
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ValueError("temperature must be between 0 and 2")
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be positive")
        return self
