from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from contracts.enums import SignalRunStatus, SignalSourceType
from contracts.signals_contracts import SignalDateRangeDTO, SignalRunRequestDTO, SignalRunStatusDTO
from signals.plugins.base import SignalPluginState
from signals.plugins.custom_python_signal import CustomPythonSignalPlugin
from signals.services.market_data_provider import DailySnapshotRow


class _FakeProvider:
    def list_trade_days(self, *, start_date: date, end_date: date) -> list[date]:
        out = []
        cur = start_date
        while cur <= end_date:
            out.append(cur)
            cur += timedelta(days=1)
        return out

    def fetch_daily_snapshot(self, *, as_of_date: date) -> list[DailySnapshotRow]:
        bullish = as_of_date.day % 2 == 0
        return [
            DailySnapshotRow(
                ts_code=f"000{index:03d}.SZ",
                close=10.0,
                pre_close=10.0,
                pct_chg=1.0 if bullish or index < 7 else -1.0,
                amount=1000.0,
                vol=100.0,
                turnover_rate=2.0,
            )
            for index in range(10)
        ]

    def fetch_market_returns(self, *, start_date: date, end_date: date) -> dict[date, float]:
        return {}


def test_custom_python_signal_executes_user_function(tmp_path) -> None:
    plugin = CustomPythonSignalPlugin()
    script = """
def compute_signal(ctx):
    metrics = []
    events = []
    threshold = ctx["params"]["threshold"]
    for day in ctx["trade_days"]:
        rows = ctx["snapshots"][day]
        adv_ratio = sum(1 for row in rows if row["pct_chg"] > 0) / len(rows)
        metrics.append({"date": day, "metric_name": "adv_ratio", "value": adv_ratio})
        if adv_ratio >= threshold:
            events.append({"date": day, "score": adv_ratio})
    return {
        "metrics": metrics,
        "events": events,
        "stats": [{"group": "summary", "name": "event_count", "value": len(events)}],
        "summary": {"headline_metric_display": str(len(events))},
    }
"""
    config = plugin.validate_config(
        {
            "script": script,
            "params": {"threshold": 0.9},
            "artifact_dir": str(tmp_path),
        }
    )
    state = SignalPluginState()
    start = date(2026, 4, 1)
    end = date(2026, 4, 4)

    plugin.compute_metrics(
        run_id="run-custom",
        provider=_FakeProvider(),
        start_date=start,
        end_date=end,
        config=config,
        state=state,
    )
    plugin.detect_events(run_id="run-custom", config=config, state=state)
    plugin.evaluate(
        run=SignalRunRequestDTO(
            signal_key=plugin.signal_key,
            date_range=SignalDateRangeDTO(start_date=start, end_date=end),
            config=config,
        ),
        provider=_FakeProvider(),
        state=state,
    )
    plugin.build_artifacts(run_id="run-custom", config=config, state=state)

    assert len(state.metrics) == 4
    assert len(state.events) == 2
    assert state.summary["headline_metric_display"] == "2"
    assert len(state.artifacts) == 2

    run = SignalRunStatusDTO(
        run_id="run-custom",
        signal_key=plugin.signal_key,
        source_type=SignalSourceType.POSTGRES,
        status=SignalRunStatus.SUCCEEDED,
        requested_start_date=start,
        requested_end_date=end,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        config=config,
        summary=state.summary,
    )
    tabs = plugin.build_dashboard_tabs(
        run=run,
        metrics=state.metrics,
        events=state.events,
        stats=state.stats,
        sweeps=state.param_sweeps,
    )
    assert [tab.tab_key for tab in tabs] == ["overview", "events", "stats"]


def test_custom_python_signal_rejects_imports() -> None:
    plugin = CustomPythonSignalPlugin()
    with pytest.raises(ValueError, match="Import"):
        plugin.validate_config({"script": "import os\ndef compute_signal(ctx):\n    return {}\n"})


def test_custom_python_signal_rejects_dunder_attributes() -> None:
    plugin = CustomPythonSignalPlugin()
    with pytest.raises(ValueError, match="Dunder attributes"):
        plugin.validate_config({"script": "def compute_signal(ctx):\n    return ().__class__\n"})


def test_custom_python_signal_requires_metric_name() -> None:
    plugin = CustomPythonSignalPlugin()
    config = plugin.validate_config(
        {
            "script": "def compute_signal(ctx):\n    return {\"metrics\": [{\"date\": ctx[\"trade_days\"][0], \"value\": 1.0}]}\n",
        }
    )
    with pytest.raises(ValueError, match="metric_name"):
        plugin.compute_metrics(
            run_id="run-custom",
            provider=_FakeProvider(),
            start_date=date(2026, 4, 1),
            end_date=date(2026, 4, 1),
            config=config,
            state=SignalPluginState(),
        )
