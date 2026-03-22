from __future__ import annotations


class DebateNode:
    def __call__(self, state: dict) -> dict:
        state["debate_output"] = {
            "summary": "v1 placeholder",
            "market": state.get("market_output"),
            "fundamental": state.get("fundamental_output"),
        }
        return state
