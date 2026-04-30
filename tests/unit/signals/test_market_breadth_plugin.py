from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from contracts.enums import SignalRunStatus, SignalSourceType
from contracts.signals_contracts import SignalDateRangeDTO, SignalRunRequestDTO, SignalRunStatusDTO
from signals.plugins.base import SignalPluginState
from signals.plugins.market_breadth_crowding import MarketBreadthCrowdingPlugin
from signals.services.market_data_provider import DailySnapshotRow


class _FakeProvider:
    def __init__(self, days: int = 45) -> None:
        self._start = date(2026, 4, 1)
        self._days = days

    def list_trade_days(self, *, start_date: date, end_date: date) -> list[date]:
        days = [self._start + timedelta(days=i) for i in range(self._days)]
        return [day for day in days if start_date <= day <= end_date]

    def fetch_daily_snapshot(self, *, as_of_date: date) -> list[DailySnapshotRow]:
        rows: list[DailySnapshotRow] = []
        bullish = as_of_date.day % 6 in {2, 3}
        for index in range(80):
            pct_chg = 6.5 if bullish and index < 18 else (1.5 if bullish and index < 45 else -1.2)
            if not bullish:
                pct_chg = -5.8 if index < 12 else (-1.3 if index < 40 else 1.0)
            turnover = 7.5 if bullish and index < 25 else 2.0 + index / 40
            rows.append(
                DailySnapshotRow(
                    ts_code=f"000{index:03d}.SZ",
                    close=10.0 + index / 50,
                    pre_close=10.0,
                    pct_chg=pct_chg,
                    amount=1000.0 + index * 8,
                    vol=120.0 + index,
                    turnover_rate=turnover,
                )
            )
        return rows

    def fetch_market_returns(self, *, start_date: date, end_date: date) -> dict[date, float]:
        out: dict[date, float] = {}
        cur = start_date
        step = 0
        while cur <= end_date:
            out[cur] = 0.0012 if step % 2 == 0 else -0.0007
            step += 1
            cur += timedelta(days=1)
        return out


def test_market_breadth_plugin_full_flow(tmp_path) -> None:
    plugin = MarketBreadthCrowdingPlugin()
    provider = _FakeProvider(days=55)
    config = plugin.validate_config({"artifact_dir": str(tmp_path), "threshold": 0.6, "consecutive_days": 1})

    state = SignalPluginState()
    start = date(2026, 4, 1)
    end = date(2026, 5, 20)

    plugin.compute_metrics(run_id="run-1", provider=provider, start_date=start, end_date=end, config=config, state=state)
    plugin.detect_events(run_id="run-1", config=config, state=state)
    plugin.evaluate(
        run=SignalRunRequestDTO(signal_key=plugin.signal_key, date_range=SignalDateRangeDTO(start_date=start, end_date=end), config=config),
        provider=provider,
        state=state,
    )
    plugin.build_artifacts(run_id="run-1", config=config, state=state)

    assert any(item.metric_name == "crowding_score" for item in state.metrics)
    assert any(item.metric_name == "high_turnover_ratio" for item in state.metrics)
    assert any(item.metric_name == "market_close_proxy" for item in state.metrics)
    assert any(item.metric_name == "is_signal_event" and item.metric_value > 0 for item in state.metrics) or state.events == []
    assert state.stats

    run_status = SignalRunStatusDTO(
        run_id="run-1",
        signal_key=plugin.signal_key,
        source_type=SignalSourceType.POSTGRES,
        status=SignalRunStatus.SUCCEEDED,
        requested_start_date=start,
        requested_end_date=end,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        config=config,
        summary={},
    )
    tabs = plugin.build_dashboard_tabs(run=run_status, metrics=state.metrics, events=state.events, stats=state.stats, sweeps=state.param_sweeps)
    assert [tab.tab_key for tab in tabs] == ["overview", "breadth", "event-study", "forward-returns", "sensitivity", "current-regime"]
