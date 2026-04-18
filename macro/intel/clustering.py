from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher

from macro.intel.models import EventCluster, RawArticle, normalize_title


class EventClusterer:
    def __init__(self, *, time_window_hours: int = 48, title_similarity_threshold: float = 0.86):
        self.time_window_hours = time_window_hours
        self.title_similarity_threshold = title_similarity_threshold

    def cluster(self, rows: list[RawArticle]) -> list[EventCluster]:
        if not rows:
            return []

        rows = sorted(rows, key=lambda x: x.published_at or datetime.now(UTC), reverse=True)
        clusters: list[EventCluster] = []

        for row in rows:
            matched = self._find_match(clusters, row)
            if matched is None:
                clusters.append(
                    EventCluster(
                        cluster_id=self._stable_cluster_id(row),
                        topic=row.topic,
                        layer=row.layer,
                        theme_type=row.theme_type,
                        representative_title=row.title,
                        articles=[row],
                    )
                )
                continue
            matched.articles.append(row)

        return clusters

    @staticmethod
    def _stable_cluster_id(row: RawArticle) -> str:
        topic = "_".join(row.topic.strip().lower().split())[:24] or "topic"
        fingerprint = f"{row.topic}|{normalize_title(row.title)}"
        digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:20]
        return f"clu:{topic}:{digest}"

    def _find_match(self, clusters: list[EventCluster], row: RawArticle) -> EventCluster | None:
        for clu in clusters:
            if clu.topic != row.topic:
                continue
            representative = clu.articles[0]
            if not self._within_time_window(representative, row):
                continue
            sim = SequenceMatcher(None, normalize_title(clu.representative_title), normalize_title(row.title)).ratio()
            if sim >= self.title_similarity_threshold:
                return clu
        return None

    def _within_time_window(self, a: RawArticle, b: RawArticle) -> bool:
        a_ts = a.published_at or datetime.now(UTC)
        b_ts = b.published_at or datetime.now(UTC)
        return abs(a_ts - b_ts) <= timedelta(hours=self.time_window_hours)
