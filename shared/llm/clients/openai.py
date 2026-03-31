from __future__ import annotations

from shared.llm.clients.base import BaseProviderClient
from shared.llm.models import LLMProvider


class OpenAIClient(BaseProviderClient):
    provider = LLMProvider.OPENAI
