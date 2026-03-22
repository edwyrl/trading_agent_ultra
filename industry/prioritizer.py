from __future__ import annotations

from collections.abc import Sequence

class IndustryPrioritizer:
    WEIGHTS = {
        "rotation_strength": 0.30,
        "news_heat": 0.20,
        "portfolio_relevance": 0.20,
        "change_frequency": 0.15,
        "recency": 0.15,
    }

    def _score_candidate(self, candidate: dict) -> tuple[float, dict]:
        recency = min(float(candidate.get("days_since_full_refresh", 0)) / 14.0, 1.0)
        breakdown = {
            "rotation_strength": float(candidate.get("rotation_strength", 0.0)),
            "news_heat": float(candidate.get("news_heat", 0.0)),
            "portfolio_relevance": float(candidate.get("portfolio_relevance", 0.0)),
            "change_frequency": float(candidate.get("change_frequency", 0.0)),
            "recency": recency,
        }
        score = sum(breakdown[key] * self.WEIGHTS[key] for key in self.WEIGHTS)
        return score, breakdown

    def select_weekly_candidates(
        self,
        candidates: Sequence[dict] | None = None,
        *,
        limit: int = 8,
        minimum: int = 5,
    ) -> list[dict]:
        if not candidates:
            return []
        if limit < 1:
            return []

        ranked: list[dict] = []
        for item in candidates:
            score, breakdown = self._score_candidate(item)
            ranked.append(
                {
                    **item,
                    "score": score,
                    "score_breakdown": breakdown,
                }
            )

        ranked.sort(key=lambda x: x["score"], reverse=True)
        target_count = min(limit, len(ranked))
        if len(ranked) >= minimum:
            target_count = max(minimum, target_count)

        for index, item in enumerate(ranked, start=1):
            item["rank_order"] = index
            item["selected"] = index <= target_count
            item.setdefault("reason", "Selected by weighted weekly prioritizer.")

        return ranked
