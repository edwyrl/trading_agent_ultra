from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterator, Protocol

from agents.contracts import AgentComparisonRequest, AgentRunRequest, AgentRunResult, AgentRunStatus
from agents.events import ResearchStage, StreamingEvent
from shared.llm.router import LLMRouter


class AgentRuntime(Protocol):
    def run(self, request: AgentRunRequest) -> AgentRunResult:
        ...

    def stream(self, request: AgentRunRequest) -> Iterator[StreamingEvent]:
        ...

    def compare(self, request: AgentComparisonRequest) -> dict[str, AgentRunResult]:
        ...


class StubAgentRuntime:
    def __init__(self, router: LLMRouter) -> None:
        self.router = router

    def run(self, request: AgentRunRequest) -> AgentRunResult:
        route = self.router.resolve(model_id=request.model_id, role=request.role)
        now = datetime.now(UTC)
        return AgentRunResult(
            run_id=request.run_id,
            status=AgentRunStatus.NOT_IMPLEMENTED,
            role=route.role or request.role,
            model_id=route.model.model_id,
            summary="Agent runtime placeholder: no real LLM invocation yet.",
            started_at=now,
            finished_at=now,
        )

    def stream(self, request: AgentRunRequest) -> Iterator[StreamingEvent]:
        yield StreamingEvent(
            run_id=request.run_id,
            stage=ResearchStage.PREPARE,
            event_type="started",
            message="Agent stream started (placeholder).",
        )
        yield StreamingEvent(
            run_id=request.run_id,
            stage=ResearchStage.COMPLETED,
            event_type="completed",
            message="Agent stream completed (placeholder).",
        )

    def compare(self, request: AgentComparisonRequest) -> dict[str, AgentRunResult]:
        return {
            "left": self.run(request.left),
            "right": self.run(request.right),
        }
