from __future__ import annotations


class ConceptTagExtractor:
    def extract(self, text_blobs: list[str], limit: int = 10) -> list[str]:
        """v1 placeholder for LLM-based concept tag extraction."""
        _ = text_blobs
        return [] if limit <= 0 else []
