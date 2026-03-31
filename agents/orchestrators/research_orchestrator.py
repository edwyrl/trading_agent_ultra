from __future__ import annotations

from typing import Iterator

from agents.contracts import AgentRunRequest, AgentRunResult
from agents.events import StreamingEvent
from agents.runtime import AgentRuntime


class ResearchOrchestrator:
    def __init__(self, runtime: AgentRuntime) -> None:
        self.runtime = runtime

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        return self.runtime.run(request)

    def stream(self, request: AgentRunRequest) -> Iterator[StreamingEvent]:
        return self.runtime.stream(request)
