from __future__ import annotations

import ast
import base64
import json
import math
import statistics
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any, Callable

from contracts.enums import EvaluationMode
from contracts.signals_contracts import (
    DashboardMetricCardDTO,
    DashboardTabDTO,
    SignalArtifactDTO,
    SignalEventDTO,
    SignalMetricPointDTO,
    SignalParamSweepPointDTO,
    SignalPluginMetaDTO,
    SignalRunRequestDTO,
    SignalRunStatusDTO,
    SignalStatDTO,
)
from signals.plugins.base import BaseSignalPlugin, SignalPluginState
from signals.plugins.common import make_metric_card, metric_series, section, stats_map
from signals.services.market_data_provider import MarketDataProvider

DEFAULT_CUSTOM_SIGNAL_SCRIPT = '''def compute_signal(ctx):
    threshold = ctx["params"].get("threshold", 0.8)
    metrics = []
    events = []

    for day in ctx["trade_days"]:
        rows = ctx["snapshots"][day]
        eligible = [row for row in rows if row["pct_chg"] is not None]
        if not eligible:
            continue

        adv_ratio = sum(1 for row in eligible if row["pct_chg"] > 0) / len(eligible)
        metrics.append({"date": day, "metric_name": "adv_ratio", "value": adv_ratio})

        if adv_ratio >= threshold:
            events.append({
                "date": day,
                "score": adv_ratio,
                "payload": {"adv_ratio": adv_ratio, "threshold": threshold},
            })

    return {
        "metrics": metrics,
        "events": events,
        "stats": [
            {"group": "summary", "name": "trade_day_count", "value": len(ctx["trade_days"])},
            {"group": "summary", "name": "event_count", "value": len(events)},
        ],
        "summary": {
            "headline_metric_label": "Events",
            "headline_metric_display": str(len(events)),
        },
    }
'''

_DISALLOWED_NODES = (
    ast.AsyncFunctionDef,
    ast.Await,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Lambda,
    ast.Nonlocal,
    ast.Raise,
    ast.Try,
    ast.With,
)

_DISALLOWED_CALLS = {"__import__", "compile", "eval", "exec", "globals", "input", "locals", "open"}
_SAFE_BUILTINS = {
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "int": int,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "range": range,
    "round": round,
    "set": set,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "zip": zip,
}


class CustomPythonSignalPlugin(BaseSignalPlugin):
    signal_key = "custom_python_signal"

    def meta(self) -> SignalPluginMetaDTO:
        return SignalPluginMetaDTO(
            signal_key=self.signal_key,
            name="Custom Python Signal",
            description="Run a user-provided compute_signal(ctx) function against daily A-share snapshots.",
            version="v1",
            config_schema={
                "script": {
                    "type": "string",
                    "widget": "code",
                    "default": DEFAULT_CUSTOM_SIGNAL_SCRIPT,
                },
                "params": {
                    "type": "json",
                    "widget": "json",
                    "default": {"threshold": 0.8},
                },
                "artifact_dir": {"type": "string", "default": "logs/signals"},
            },
            default_config=self.default_config(),
            evaluation_modes=[EvaluationMode.EVENT_STUDY],
        )

    def default_config(self) -> dict[str, Any]:
        return {
            "script": DEFAULT_CUSTOM_SIGNAL_SCRIPT,
            "params": {"threshold": 0.8},
            "artifact_dir": "logs/signals",
        }

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_config(), **config}
        script = str(merged.get("script", "")).strip()
        if not script:
            raise ValueError("script is required")
        if len(script) > 50_000:
            raise ValueError("script must be <= 50000 characters")
        params = merged.get("params", {})
        if not isinstance(params, dict):
            raise ValueError("params must be a JSON object")
        _compile_custom_function(script)
        merged["script"] = script
        merged["params"] = params
        return merged

    def compute_metrics(
        self,
        *,
        run_id: str,
        provider: MarketDataProvider,
        start_date: date,
        end_date: date,
        config: dict[str, Any],
        state: SignalPluginState,
    ) -> None:
        trade_days = provider.list_trade_days(start_date=start_date, end_date=end_date)
        snapshots = {
            day.isoformat(): [asdict(row) for row in provider.fetch_daily_snapshot(as_of_date=day)]
            for day in trade_days
        }
        context = {
            "run_id": run_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "trade_days": [day.isoformat() for day in trade_days],
            "snapshots": snapshots,
            "params": dict(config.get("params", {})),
        }
        compute_signal = _compile_custom_function(str(config["script"]))
        result = compute_signal(context)
        if not isinstance(result, dict):
            raise ValueError("compute_signal(ctx) must return a dict")

        state.metrics = _parse_metrics(result.get("metrics", []))
        state.events = _parse_events(run_id=run_id, raw_events=result.get("events", []))
        state.stats = _parse_stats(result.get("stats", []))
        _ensure_summary_stats(state=state, trade_day_count=len(trade_days))
        state.summary = _build_summary(result.get("summary", {}), state=state)
        state.transient = {"result": result}

    def detect_events(self, *, run_id: str, config: dict[str, Any], state: SignalPluginState) -> None:
        _ = (run_id, config, state)

    def evaluate(
        self,
        *,
        run: SignalRunRequestDTO,
        provider: MarketDataProvider,
        state: SignalPluginState,
    ) -> None:
        _ = (run, provider, state)

    def build_artifacts(self, *, run_id: str, config: dict[str, Any], state: SignalPluginState) -> None:
        artifact_dir = Path(config.get("artifact_dir", "logs/signals")) / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        report_payload = {
            "summary": state.summary,
            "metrics": [item.model_dump(mode="json") for item in state.metrics],
            "events": [item.model_dump(mode="json") for item in state.events],
            "stats": [item.model_dump(mode="json") for item in state.stats],
            "script": config.get("script", ""),
            "params": config.get("params", {}),
        }
        report_path = artifact_dir / "report.json"
        report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        png_path = artifact_dir / "dashboard.png"
        png_path.write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wm5d8QAAAAASUVORK5CYII="))

        state.artifacts = [
            SignalArtifactDTO(
                artifact_type="json",
                artifact_key="report",
                uri=str(report_path.resolve()),
                content_type="application/json",
                size_bytes=report_path.stat().st_size,
                payload={"label": "Research Report"},
            ),
            SignalArtifactDTO(
                artifact_type="png",
                artifact_key="dashboard",
                uri=str(png_path.resolve()),
                content_type="image/png",
                size_bytes=png_path.stat().st_size,
                payload={"label": "Dashboard Snapshot"},
            ),
        ]

    def build_key_metrics(
        self,
        *,
        run: SignalRunStatusDTO,
        metrics: list[SignalMetricPointDTO],
        events: list[SignalEventDTO],
        stats: list[SignalStatDTO],
        sweeps: list[SignalParamSweepPointDTO],
    ) -> list[DashboardMetricCardDTO]:
        _ = (run, metrics, events, sweeps)
        stat_values = stats_map(stats)
        cards = [
            make_metric_card(metric_key="metric_points", label="Metric Points", value=float(len(metrics)), display=f"{len(metrics)}"),
            make_metric_card(metric_key="event_count", label="Events", value=float(len(events)), display=f"{len(events)}"),
        ]
        for (group, name), value in list(stat_values.items())[:4]:
            cards.append(make_metric_card(metric_key=f"{group}_{name}", label=name.replace("_", " ").title(), value=value))
        return cards[:6]

    def build_dashboard_tabs(
        self,
        *,
        run: SignalRunStatusDTO,
        metrics: list[SignalMetricPointDTO],
        events: list[SignalEventDTO],
        stats: list[SignalStatDTO],
        sweeps: list[SignalParamSweepPointDTO],
    ) -> list[DashboardTabDTO]:
        _ = (run, sweeps)
        metric_names = sorted({item.metric_name for item in metrics})
        series = [
            {
                "metric_name": metric_name,
                "label": metric_name.replace("_", " ").title(),
                "points": [
                    {"date": metric_date.isoformat(), "value": value}
                    for metric_date, value in metric_series(metrics, metric_name=metric_name)
                ],
            }
            for metric_name in metric_names[:8]
        ]
        stat_rows = [
            {"group": stat.stat_group, "name": stat.stat_name, "value": stat.stat_value}
            for stat in stats
        ]
        event_rows = [
            {
                "event_date": event.event_date.isoformat(),
                "event_type": event.event_type,
                "score": event.score,
            }
            for event in events
        ]
        return [
            DashboardTabDTO(
                tab_key="overview",
                label="Overview",
                sections=[
                    section(
                        section_key="custom-metrics",
                        title="Custom Signal Metrics",
                        section_type="timeseries",
                        eyebrow="Custom",
                        payload={"series": series, "y_axis_label": "Value"},
                    )
                ],
            ),
            DashboardTabDTO(
                tab_key="events",
                label="Events",
                sections=[
                    section(
                        section_key="custom-events",
                        title="Signal Events",
                        section_type="table",
                        eyebrow="Events",
                        payload={"columns": ["event_date", "event_type", "score"], "rows": event_rows},
                    )
                ],
            ),
            DashboardTabDTO(
                tab_key="stats",
                label="Stats",
                sections=[
                    section(
                        section_key="custom-stats",
                        title="Custom Signal Stats",
                        section_type="table",
                        eyebrow="Stats",
                        payload={"columns": ["group", "name", "value"], "rows": stat_rows},
                    )
                ],
            ),
        ]


def _compile_custom_function(script: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    tree = ast.parse(script, mode="exec")
    for node in ast.walk(tree):
        if isinstance(node, _DISALLOWED_NODES):
            raise ValueError(f"Unsupported syntax in custom signal script: {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            raise ValueError("Dunder names are not allowed in custom signal scripts")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise ValueError("Dunder attributes are not allowed in custom signal scripts")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _DISALLOWED_CALLS:
            raise ValueError(f"Function is not allowed in custom signal script: {node.func.id}")
    namespace: dict[str, Any] = {}
    globals_dict = {
        "__builtins__": _SAFE_BUILTINS,
        "math": math,
        "statistics": statistics,
    }
    exec(compile(tree, "<custom_signal_script>", "exec"), globals_dict, namespace)
    func = namespace.get("compute_signal")
    if not callable(func):
        raise ValueError("script must define compute_signal(ctx)")
    return func


def _parse_metrics(raw_metrics: Any) -> list[SignalMetricPointDTO]:
    if not isinstance(raw_metrics, list):
        raise ValueError("metrics must be a list")
    out: list[SignalMetricPointDTO] = []
    for item in raw_metrics:
        if not isinstance(item, dict):
            raise ValueError("each metric must be an object")
        metric_name = item.get("metric_name") or item.get("name")
        if not metric_name:
            raise ValueError("each metric must include metric_name or name")
        out.append(
            SignalMetricPointDTO(
                metric_name=str(metric_name),
                metric_date=date.fromisoformat(str(item["date"])),
                metric_value=float(item["value"]),
                payload=dict(item.get("payload", {})),
            )
        )
    return out


def _parse_events(*, run_id: str, raw_events: Any) -> list[SignalEventDTO]:
    if not isinstance(raw_events, list):
        raise ValueError("events must be a list")
    out: list[SignalEventDTO] = []
    for index, item in enumerate(raw_events):
        if not isinstance(item, dict):
            raise ValueError("each event must be an object")
        event_date = date.fromisoformat(str(item["date"]))
        out.append(
            SignalEventDTO(
                event_id=str(item.get("event_id") or f"{run_id}:custom:{event_date.isoformat()}:{index}"),
                event_date=event_date,
                event_type=str(item.get("event_type", "SIGNAL_EVENT")),
                score=float(item["score"]) if item.get("score") is not None else None,
                payload=dict(item.get("payload", {})),
            )
        )
    return out


def _parse_stats(raw_stats: Any) -> list[SignalStatDTO]:
    if raw_stats is None:
        return []
    if not isinstance(raw_stats, list):
        raise ValueError("stats must be a list")
    out: list[SignalStatDTO] = []
    for item in raw_stats:
        if not isinstance(item, dict):
            raise ValueError("each stat must be an object")
        stat_name = item.get("stat_name") or item.get("name")
        if not stat_name:
            raise ValueError("each stat must include stat_name or name")
        out.append(
            SignalStatDTO(
                stat_group=str(item.get("stat_group") or item.get("group") or "summary"),
                stat_name=str(stat_name),
                stat_value=float(item.get("stat_value", item.get("value", 0.0))),
                payload=dict(item.get("payload", {})),
            )
        )
    return out


def _ensure_summary_stats(*, state: SignalPluginState, trade_day_count: int) -> None:
    existing = {(item.stat_group, item.stat_name) for item in state.stats}
    if ("summary", "trade_day_count") not in existing:
        state.stats.append(SignalStatDTO(stat_group="summary", stat_name="trade_day_count", stat_value=float(trade_day_count)))
    if ("summary", "event_count") not in existing:
        state.stats.append(SignalStatDTO(stat_group="summary", stat_name="event_count", stat_value=float(len(state.events))))


def _build_summary(raw_summary: Any, *, state: SignalPluginState) -> dict[str, Any]:
    summary = dict(raw_summary) if isinstance(raw_summary, dict) else {}
    summary.setdefault("status", "success")
    summary.setdefault("metric_points", len(state.metrics))
    summary.setdefault("event_count", len(state.events))
    summary.setdefault("headline_metric_label", "Events")
    summary.setdefault("headline_metric_display", str(len(state.events)))
    return summary
