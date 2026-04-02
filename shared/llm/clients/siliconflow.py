from __future__ import annotations

from shared.llm.clients.base import BaseProviderClient
from shared.llm.models import LLMProvider


class SiliconFlowClient(BaseProviderClient):
    provider = LLMProvider.SILICONFLOW
