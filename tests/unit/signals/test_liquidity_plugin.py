from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from contracts.enums import SignalRunStatus, SignalSourceType
from contracts.signals_contracts import SignalDateRangeDTO, SignalRunRequestDTO, SignalRunStatusDTO
from signals.plugins.base import SignalPluginState
from signals.plugins.liquidity_concentration import LiquidityConcentrationPlugin
from signals.services.market_data_provider import DailySnapshotRow


class _FakeProvider:
    def __init__(self, days: int = 40) -> None:
        self._start = date(2026, 4, 1)
        self._days = days

    def list_trade_days(self, *, start_date: date, end_date: date) -> list[date]:
        days = [self._start + timedelta(days=i) for i in range(self._days)]
        return [d for d in days if start_date <= d <= end_date]

    def fetch_daily_snapshot(self, *, as_of_date: date) -> list[DailySnapshotRow]:
        day_bias = 3000.0 if as_of_date.day % 7 in {2, 3, 4} else 0.0
        rows: list[DailySnapshotRow] = []
        for index in range(60):
            amount = 1000.0 + index * 10.0
            vol = 100.0 + index
            if index == 0:
                amount += day_bias * 8
                vol += day_bias / 10
            elif index == 1:
                amount += day_bias * 6
                vol += day_bias / 12
            elif index == 2:
                amount += day_bias * 4
                vol += day_bias / 15
            rows.append(
                DailySnapshotRow(
                    ts_code=f"000{index:03d}.SZ",
                    close=10.0 + index / 100,
                    pre_close=10.0,
                    pct_chg=((index % 5) - 2) * 0.8,
                    amount=amount,
                    vol=vol,
                    turnover_rate=2.0 + index / 20,
                )
            )
        return rows

    def fetch_market_returns(self, *, start_date: date, end_date: date) -> dict[date, float]:
        out: dict[date, float] = {}
        cur = start_date
        step = 0
        while cur <= end_date:
            out[cur] = 0.001 if step % 2 == 0 else -0.0005
            cur += timedelta(days=1)
            step += 1
        return out


def test_liquidity_plugin_full_flow(tmp_path) -> None:
    plugin = LiquidityConcentrationPlugin()
    provider = _FakeProvider(days=50)
    config = plugin.validate_config(
        {
            "artifact_dir": str(tmp_path),
            "threshold": 0.07,
            "consecutive_days": 1,
            "signal_cooldown": 1,
            "sens_top_pcts": [0.05],
            "sens_thresholds": [0.05, 0.07],
        }
    )

    state = SignalPluginState()
    start = date(2026, 4, 1)
    end = date(2026, 5, 20)

    plugin.compute_metrics(
        run_id="run-1",
        provider=provider,
        start_date=start,
        end_date=end,
        config=config,
        state=state,
    )
    plugin.detect_events(run_id="run-1", config=config, state=state)
    plugin.evaluate(
        run=SignalRunRequestDTO(
            signal_key="liquidity_concentration",
            date_range=SignalDateRangeDTO(start_date=start, end_date=end),
            config=config,
        ),
        provider=provider,
        state=state,
    )
    plugin.build_artifacts(run_id="run-1", config=config, state=state)

    assert state.metrics
    assert any(item.metric_name == "top_ratio" for item in state.metrics)
    assert any(item.metric_name == "is_signal_event" for item in state.metrics)
    assert any(item.metric_name == "market_close_proxy" for item in state.metrics)
    assert state.events
    assert state.stats
    forward_stat = next(item for item in state.stats if item.stat_group == "forward_returns")
    assert forward_stat.payload["horizons"]
    event_stat = next(item for item in state.stats if item.stat_group == "event_study")
    assert "event_paths" in event_stat.payload
    assert state.param_sweeps
    assert len(state.artifacts) == 2

    run_status = SignalRunStatusDTO(
        run_id="run-1",
        signal_key="liquidity_concentration",
        source_type=SignalSourceType.POSTGRES,
        status=SignalRunStatus.SUCCEEDED,
        requested_start_date=start,
        requested_end_date=end,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        config=config,
        summary={},
    )
    key_metrics = plugin.build_key_metrics(
        run=run_status,
        metrics=state.metrics,
        events=state.events,
        stats=state.stats,
        sweeps=state.param_sweeps,
    )
    assert any(metric.metric_key == "horizon_10d_alpha" for metric in key_metrics)
    tabs = plugin.build_dashboard_tabs(
        run=run_status,
        metrics=state.metrics,
        events=state.events,
        stats=state.stats,
        sweeps=state.param_sweeps,
    )
    assert [tab.tab_key for tab in tabs] == ["overview", "event-study", "forward-returns", "sensitivity", "current-regime"]
