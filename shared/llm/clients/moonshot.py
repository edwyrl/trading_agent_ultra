from __future__ import annotations

from shared.llm.clients.base import BaseProviderClient
from shared.llm.models import LLMProvider


class MoonshotClient(BaseProviderClient):
    provider = LLMProvider.MOONSHOT
