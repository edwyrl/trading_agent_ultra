from __future__ import annotations

import math
from datetime import date
from typing import Any

from contracts.signals_contracts import DashboardMetricCardDTO, DashboardSectionDTO, DashboardSeriesPointDTO, SignalMetricPointDTO, SignalParamSweepPointDTO, SignalStatDTO
from signals.plugins.base import SignalPluginState


def make_metric_card(*, metric_key: str, label: str, value: float, unit: str = "", display: str | None = None) -> DashboardMetricCardDTO:
    return DashboardMetricCardDTO(
        metric_key=metric_key,
        label=label,
        value=float(value),
        unit=unit,
        display=display if display is not None else f"{value:.4f}",
    )


def section(*, section_key: str, title: str, section_type: str, payload: dict[str, Any], eyebrow: str = "") -> DashboardSectionDTO:
    return DashboardSectionDTO(
        section_key=section_key,
        title=title,
        section_type=section_type,
        eyebrow=eyebrow,
        payload=payload,
    )


def points_from_series(items: list[tuple[date, float]]) -> list[DashboardSeriesPointDTO]:
    return [DashboardSeriesPointDTO(date=item_date, value=float(value)) for item_date, value in items]


def named_series(*, metric_name: str, label: str, items: list[tuple[date, float]]) -> dict[str, Any]:
    return {
        "metric_name": metric_name,
        "label": label,
        "points": [point.model_dump(mode="json") for point in points_from_series(items)],
    }


def rows_by_date(state: SignalPluginState) -> list[dict[str, Any]]:
    return list(state.transient.get("rows", []))


def metric_series(metrics: list[SignalMetricPointDTO], *, metric_name: str) -> list[tuple[date, float]]:
    return [
        (item.metric_date, float(item.metric_value))
        for item in metrics
        if item.metric_name == metric_name
    ]


def metric_values(metrics: list[SignalMetricPointDTO], *, metric_name: str) -> list[float]:
    return [float(item.metric_value) for item in metrics if item.metric_name == metric_name]


def stats_map(state: SignalPluginState | list[SignalStatDTO]) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    source = state.stats if isinstance(state, SignalPluginState) else state
    for stat in source:
        out[(stat.stat_group, stat.stat_name)] = float(stat.stat_value)
    return out


def stat_payload(state: SignalPluginState | list[SignalStatDTO], *, stat_group: str, stat_name: str) -> dict[str, Any]:
    source = state.stats if isinstance(state, SignalPluginState) else state
    for stat in source:
        if stat.stat_group == stat_group and stat.stat_name == stat_name:
            return dict(stat.payload or {})
    return {}


def sweep_payload(state: SignalPluginState | list[SignalParamSweepPointDTO]) -> dict[str, Any]:
    source = state.param_sweeps if isinstance(state, SignalPluginState) else state
    if not source:
        return {
            "x_key": "",
            "y_key": "",
            "x_values": [],
            "y_values": [],
            "metrics": [],
            "cells": [],
        }
    x_key = source[0].x_key
    y_key = source[0].y_key
    x_values = sorted({float(item.x_value) for item in source})
    y_values = sorted({float(item.y_value) for item in source})
    metric_names = sorted({item.metric_name for item in source})
    cell_map: dict[tuple[float, float], dict[str, float]] = {}
    for item in source:
        key = (float(item.x_value), float(item.y_value))
        cell_map.setdefault(key, {})[item.metric_name] = float(item.metric_value)
    cells = [
        {"x_value": key[0], "y_value": key[1], "metrics": metrics}
        for key, metrics in sorted(cell_map.items(), key=lambda item: (item[0][0], item[0][1]))
    ]
    return {
        "x_key": x_key,
        "y_key": y_key,
        "x_values": x_values,
        "y_values": y_values,
        "metrics": metric_names,
        "cells": cells,
    }


def yearly_event_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[int, int] = {}
    for row in rows:
        if not row.get("is_signal_event"):
            continue
        counts[row["date"].year] = counts.get(row["date"].year, 0) + 1
    return [{"category": str(year), "value": count} for year, count in sorted(counts.items())]


def mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return float(sum(values) / len(values))


def std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    avg = mean(values)
    return float(math.sqrt(sum((value - avg) ** 2 for value in values) / (len(values) - 1)))


def rolling_consecutive_true(flags: list[bool], consecutive_days: int) -> list[bool]:
    out: list[bool] = []
    streak = 0
    for flag in flags:
        streak = streak + 1 if flag else 0
        out.append(streak >= consecutive_days)
    return out


def rolling_percentile(values: list[float], lookback: int) -> list[float]:
    out: list[float] = []
    for index, value in enumerate(values):
        start = max(0, index - lookback + 1)
        window = values[start : index + 1]
        if len(window) < 20:
            out.append(0.0)
            continue
        out.append(float(sum(1 for item in window if item <= value)) / float(len(window)))
    return out


def expanding_percentile(values: list[float]) -> list[float]:
    out: list[float] = []
    seen: list[float] = []
    for value in values:
        seen.append(value)
        out.append(float(sum(1 for item in seen if item <= value)) / float(len(seen)))
    return out


def cooldown_events(flags: list[bool], cooldown: int) -> list[bool]:
    out = [False for _ in flags]
    last_index = -cooldown - 1
    for index, flag in enumerate(flags):
        if not flag:
            continue
        if (index - last_index) <= cooldown:
            continue
        out[index] = True
        last_index = index
    return out


def risk_score(*, hist_pct: float, is_signal: bool, recent_days: int) -> float:
    score = hist_pct * 60.0
    score += min(recent_days / 10.0, 1.0) * 25.0
    if is_signal:
        score += 15.0
    return float(min(max(score, 0.0), 100.0))
