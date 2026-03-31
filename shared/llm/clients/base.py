from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from shared.llm.models import LLMProvider


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str | None = None
    role: str | None = None
    messages: list[ChatMessage] = Field(default_factory=list)
    temperature: float | None = None
    max_output_tokens: int | None = None


class CompletionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: LLMProvider
    model_id: str
    text: str
    finish_reason: str | None = None


class ProviderClient(Protocol):
    provider: LLMProvider

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        ...


class BaseProviderClient:
    provider: LLMProvider

    def __init__(self, *, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        _ = request
        raise NotImplementedError("provider client is a placeholder in this phase")
