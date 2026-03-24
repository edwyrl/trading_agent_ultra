from __future__ import annotations

from difflib import SequenceMatcher

from macro.intel.models import RawArticle, normalize_title


class DocumentDeduplicator:
    def __init__(self, title_similarity_threshold: float = 0.9):
        self.title_similarity_threshold = title_similarity_threshold

    def dedup(self, rows: list[RawArticle]) -> list[RawArticle]:
        by_url: dict[str, RawArticle] = {}
        for row in rows:
            key = row.url.strip().lower()
            if key not in by_url:
                by_url[key] = row

        unique_rows = list(by_url.values())
        kept: list[RawArticle] = []
        normalized_titles: list[str] = []

        for row in unique_rows:
            title = normalize_title(row.title)
            if not title:
                continue
            if title in normalized_titles:
                continue
            if any(self._similar(title, existing) >= self.title_similarity_threshold for existing in normalized_titles):
                continue
            kept.append(row)
            normalized_titles.append(title)

        return kept

    @staticmethod
    def _similar(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()
