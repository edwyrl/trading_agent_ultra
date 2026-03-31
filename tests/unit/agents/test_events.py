from __future__ import annotations

from agents.contracts import AgentRunRequest
from agents.events import ResearchStage, StreamingEvent


def test_streaming_event_json_roundtrip() -> None:
    request = AgentRunRequest(prompt="test prompt")
    event = StreamingEvent(
        run_id=request.run_id,
        stage=ResearchStage.RESEARCH,
        event_type="progress",
        message="collecting sources",
        data={"step": 1},
    )

    restored = StreamingEvent.model_validate(event.model_dump(mode="json"))

    assert restored.run_id == request.run_id
    assert restored.stage == ResearchStage.RESEARCH
    assert restored.data["step"] == 1
