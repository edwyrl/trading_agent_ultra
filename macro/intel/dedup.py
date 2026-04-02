from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher

from macro.intel.models import RawArticle, normalize_title


class DocumentDeduplicator:
    def __init__(
        self,
        title_similarity_threshold: float = 0.9,
        *,
        by: list[str] | None = None,
        time_window_hours: int | None = None,
    ):
        self.title_similarity_threshold = title_similarity_threshold
        by_keys = [x.strip().lower() for x in (by or []) if x and x.strip()]
        # Legacy behavior: title similarity dedup by default.
        self.by = set(by_keys or ["headline_similarity"])
        self.time_window_hours = time_window_hours

    def dedup(self, rows: list[RawArticle]) -> list[RawArticle]:
        by_url: dict[str, RawArticle] = {}
        for row in rows:
            key = row.url.strip().lower()
            if key not in by_url:
                by_url[key] = row

        unique_rows = sorted(
            by_url.values(),
            key=lambda r: r.published_at or datetime.now(UTC),
            reverse=True,
        )
        kept: list[RawArticle] = []

        for row in unique_rows:
            title = normalize_title(row.title)
            if not title:
                continue

            if any(self._is_duplicate(row, existing) for existing in kept):
                continue
            kept.append(row)

        return kept

    @staticmethod
    def _similar(a: str, b: str) -> float:
        return SequenceMatcher(None, a, b).ratio()

    def _is_duplicate(self, row: RawArticle, existing: RawArticle) -> bool:
        if not self._within_time_window(row, existing):
            return False

        row_title = normalize_title(row.title)
        existing_title = normalize_title(existing.title)

        if "headline_similarity" in self.by and self._similar(row_title, existing_title) >= self.title_similarity_threshold:
            return True

        inst_match = self._field_match(
            enabled="institution" in self.by,
            left=self._extract_institution(row),
            right=self._extract_institution(existing),
        )
        event_match = self._field_match(
            enabled="event_type" in self.by,
            left=self._extract_event_type(row),
            right=self._extract_event_type(existing),
        )
        figures_match = self._key_figures_match(row, existing) if "key_figures" in self.by else None

        matches = [x for x in [inst_match, event_match, figures_match] if x is not None]
        # Require strong structured agreement to avoid false positive collapse.
        return len(matches) >= 2 and all(matches)

    def _within_time_window(self, a: RawArticle, b: RawArticle) -> bool:
        if self.time_window_hours is None or "time_window" not in self.by:
            return True
        a_ts = a.published_at or datetime.now(UTC)
        b_ts = b.published_at or datetime.now(UTC)
        return abs(a_ts - b_ts) <= timedelta(hours=self.time_window_hours)

    @staticmethod
    def _field_match(*, enabled: bool, left: str | None, right: str | None) -> bool | None:
        if not enabled:
            return None
        if not left or not right:
            return None
        return left == right

    def _extract_institution(self, row: RawArticle) -> str | None:
        text = self._combined_text(row)
        mapping = [
            ("pbc", ["中国人民银行", "央行", "pbc"]),
            ("fed", ["federal reserve", "fomc", "powell", "fed"]),
            ("treasury", ["treasury", "财政部", "美财政部"]),
            ("stats_bureau", ["国家统计局", "bls", "bea", "census"]),
            ("opec", ["opec"]),
            ("ecb", ["ecb", "欧洲央行"]),
            ("imf", ["imf"]),
        ]
        for key, keywords in mapping:
            if any(k.lower() in text for k in keywords):
                return key
        return None

    def _extract_event_type(self, row: RawArticle) -> str | None:
        text = self._combined_text(row)
        event_map = [
            ("monetary_policy", ["降息", "加息", "lpr", "mlf", "逆回购", "fomc", "rate", "利率"]),
            ("inflation_data", ["cpi", "ppi", "pce", "inflation", "通胀"]),
            ("labor_data", ["payroll", "unemployment", "就业", "失业率", "jobless"]),
            ("sanctions_trade", ["制裁", "sanction", "export control", "关税", "tariff"]),
            ("geopolitical_conflict", ["冲突", "war", "geopolit", "霍尔木兹", "red sea", "苏伊士"]),
            ("liquidity_stress", ["liquidity", "流动性", "repo", "挤兑", "bank run", "主权债"]),
            ("market_anomaly", ["油价", "gold", "dollar", "yield", "美元", "美债", "波动"]),
        ]
        for key, keywords in event_map:
            if any(k.lower() in text for k in keywords):
                return key
        return None

    def _key_figures_match(self, a: RawArticle, b: RawArticle) -> bool | None:
        figs_a = self._extract_key_figures(a)
        figs_b = self._extract_key_figures(b)
        if not figs_a or not figs_b:
            return None
        return bool(set(figs_a) & set(figs_b))

    def _extract_key_figures(self, row: RawArticle) -> list[str]:
        text = self._combined_text(row)
        pattern = r"\d+(?:\.\d+)?\s?(?:%|bp|bps|亿|万亿|trillion|billion|million|mn)"
        matches = re.findall(pattern, text, flags=re.IGNORECASE)
        normalized: list[str] = []
        for token in matches:
            cleaned = " ".join(token.lower().split())
            if cleaned not in normalized:
                normalized.append(cleaned)
        return normalized[:4]

    @staticmethod
    def _combined_text(row: RawArticle) -> str:
        return f"{row.title} {row.content}".lower()
