from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any


_YES = {"Y", "YES", "TRUE", "1"}
_NO = {"N", "NO", "FALSE", "0"}
_IMPORTANCE = {"H", "M", "L"}


def load_feedback_rows(path: str | Path) -> list[dict[str, str]]:
    file_path = Path(path)
    with file_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        rows: list[dict[str, str]] = []
        for row in reader:
            normalized = {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            rows.append(normalized)
    return rows


def compute_weekly_metrics(rows: list[dict[str, str]]) -> dict[str, Any]:
    selected_eval = [r for r in rows if _selected_flag(r) is True and _yn(_field(r, "should_report")) is not None]
    non_selected_eval = [r for r in rows if _selected_flag(r) is False and _yn(_field(r, "should_report")) is not None]
    selected_importance = [
        r for r in rows if _selected_flag(r) is True and _field(r, "importance").upper() in _IMPORTANCE
    ]
    duplicate_eval = [r for r in rows if _yn(_field(r, "is_duplicate")) is not None]
    miss_rows = [r for r in rows if _has_miss(r)]

    selected_precision = _ratio(
        numerator=sum(1 for r in selected_eval if _yn(_field(r, "should_report")) is True),
        denominator=len(selected_eval),
    )
    non_selected_fn_proxy = _ratio(
        numerator=sum(1 for r in non_selected_eval if _yn(_field(r, "should_report")) is True),
        denominator=len(non_selected_eval),
    )
    importance_hit_rate = _ratio(
        numerator=sum(1 for r in selected_importance if _field(r, "importance").upper() == "H"),
        denominator=len(selected_importance),
    )
    duplicate_rate = _ratio(
        numerator=sum(1 for r in duplicate_eval if _yn(_field(r, "is_duplicate")) is True),
        denominator=len(duplicate_eval),
    )

    return {
        "row_count": len(rows),
        "selected_precision": selected_precision,
        "non_selected_fn_proxy": non_selected_fn_proxy,
        "importance_hit_rate": importance_hit_rate,
        "duplicate_rate": duplicate_rate,
        "miss_count": len(miss_rows),
        "denominators": {
            "selected_precision": len(selected_eval),
            "non_selected_fn_proxy": len(non_selected_eval),
            "importance_hit_rate": len(selected_importance),
            "duplicate_rate": len(duplicate_eval),
        },
        "topic_debug": {
            "fn_topics": _topic_top(
                r for r in non_selected_eval if _yn(_field(r, "should_report")) is True
            ),
            "selected_false_positive_topics": _topic_top(
                r for r in selected_eval if _yn(_field(r, "should_report")) is False
            ),
            "miss_topics": _topic_top(r for r in miss_rows),
        },
    }


def build_recommendations(rows: list[dict[str, str]], metrics: dict[str, Any], *, max_actions: int = 3) -> list[str]:
    _ = rows
    actions: list[str] = []
    fn_proxy = metrics.get("non_selected_fn_proxy")
    miss_count = int(metrics.get("miss_count") or 0)
    selected_precision = metrics.get("selected_precision")
    duplicate_rate = metrics.get("duplicate_rate")
    importance_hit_rate = metrics.get("importance_hit_rate")
    topics = metrics.get("topic_debug") or {}

    fn_topic = _top_topic_name(topics.get("fn_topics"))
    miss_topic = _top_topic_name(topics.get("miss_topics"))
    selected_fp_topic = _top_topic_name(topics.get("selected_false_positive_topics"))

    if ((isinstance(fn_proxy, float) and fn_proxy > 0.30) or miss_count >= 3) and len(actions) < max_actions:
        focus_topic = fn_topic or miss_topic or "高争议topic"
        actions.append(
            f"[FN/Miss] {focus_topic}: 下周将该topic阈值下调3分，或新增1-2条query以补漏。"
        )

    if isinstance(selected_precision, float) and selected_precision < 0.70 and len(actions) < max_actions:
        focus_topic = selected_fp_topic or "误报集中topic"
        actions.append(
            f"[Precision] {focus_topic}: 下周将该topic阈值上调3分，并收紧source/profile。"
        )

    if isinstance(duplicate_rate, float) and duplicate_rate > 0.20 and len(actions) < max_actions:
        actions.append("[Duplicate] dedup/cluster相似度阈值各下调0.02~0.03，提升合并力度。")

    if isinstance(importance_hit_rate, float) and importance_hit_rate < 0.50 and len(actions) < max_actions:
        actions.append("[Importance] 调整quotas：提高政策/核心数据topic配额，压低噪声topic配额。")

    return actions[:max_actions]


def build_weekly_report(rows: list[dict[str, str]], *, week_label: str) -> dict[str, Any]:
    metrics = compute_weekly_metrics(rows)
    recommendations = build_recommendations(rows, metrics, max_actions=3)
    return {
        "week_label": week_label,
        "metrics": metrics,
        "recommendations": recommendations,
    }


def render_weekly_markdown(report: dict[str, Any]) -> str:
    week = str(report.get("week_label") or "unknown-week")
    metrics = report.get("metrics") or {}
    recs = report.get("recommendations") or []

    sp = _pct(metrics.get("selected_precision"))
    fn = _pct(metrics.get("non_selected_fn_proxy"))
    ih = _pct(metrics.get("importance_hit_rate"))
    dr = _pct(metrics.get("duplicate_rate"))
    miss_count = int(metrics.get("miss_count") or 0)
    row_count = int(metrics.get("row_count") or 0)

    lines = [
        f"# Macro Eval Weekly Report ({week})",
        "",
        "## Metrics",
        f"- Row Count: {row_count}",
        f"- Selected Precision: {sp}",
        f"- Non-selected FN Proxy: {fn}",
        f"- Importance Hit Rate: {ih}",
        f"- Duplicate Rate: {dr}",
        f"- Miss Count: {miss_count}",
        "",
        "## Recommendations (max 3)",
    ]
    if recs:
        for idx, rec in enumerate(recs, start=1):
            lines.append(f"{idx}. {rec}")
    else:
        lines.append("1. 本周指标无明显异常，保持当前query/阈值/归并规则。")
    lines.append("")
    return "\n".join(lines)


def _ratio(*, numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _yn(value: str) -> bool | None:
    token = value.strip().upper()
    if token in _YES:
        return True
    if token in _NO:
        return False
    return None


def _selected_flag(row: dict[str, str]) -> bool | None:
    raw = _field(row, "selected")
    yn = _yn(raw)
    if yn is not None:
        return yn
    token = raw.strip().lower()
    if token in {"t", "true"}:
        return True
    if token in {"f", "false"}:
        return False
    return None


def _has_miss(row: dict[str, str]) -> bool:
    return bool(
        _field(row, "missed_note")
        or _field(row, "missed_title")
        or _field(row, "missed_url")
        or _field(row, "missed_reason")
    )


def _topic_top(rows: Any) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        topic = _field(row, "topic")
        if topic:
            counter[topic] += 1
    return [{"topic": topic, "count": count} for topic, count in counter.most_common(5)]


def _top_topic_name(items: Any) -> str:
    if not isinstance(items, list) or not items:
        return ""
    first = items[0]
    if not isinstance(first, dict):
        return ""
    return str(first.get("topic") or "")


def _pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _field(row: dict[str, str], key: str) -> str:
    return str(row.get(key) or "")
