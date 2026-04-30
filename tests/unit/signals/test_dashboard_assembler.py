from __future__ import annotations

from datetime import UTC, date, datetime

from contracts.enums import SignalRunStatus, SignalSourceType
from contracts.signals_contracts import (
    SignalArtifactDTO,
    SignalEventDTO,
    SignalMetricPointDTO,
    SignalParamSweepPointDTO,
    SignalRunStatusDTO,
    SignalStatDTO,
)
from signals.plugins.liquidity_concentration import LiquidityConcentrationPlugin
from signals.service import SignalDashboardAssembler


def test_dashboard_assembler_builds_generic_tabs() -> None:
    now = datetime.now(UTC)
    run = SignalRunStatusDTO(
        run_id="run-1",
        signal_key="liquidity_concentration",
        source_type=SignalSourceType.POSTGRES,
        status=SignalRunStatus.SUCCEEDED,
        requested_start_date=date(2026, 4, 1),
        requested_end_date=date(2026, 4, 20),
        created_at=now,
        updated_at=now,
        config={"top_pct": 0.05, "threshold": 0.45},
    )

    metrics = [
        SignalMetricPointDTO(metric_name="top_ratio", metric_date=date(2026, 4, 1), metric_value=0.4),
        SignalMetricPointDTO(metric_name="top_ratio", metric_date=date(2026, 4, 2), metric_value=0.45),
        SignalMetricPointDTO(metric_name="rolling_pct", metric_date=date(2026, 4, 1), metric_value=0.6),
        SignalMetricPointDTO(metric_name="rolling_pct", metric_date=date(2026, 4, 2), metric_value=0.7),
        SignalMetricPointDTO(metric_name="expanding_pct", metric_date=date(2026, 4, 1), metric_value=0.65),
        SignalMetricPointDTO(metric_name="expanding_pct", metric_date=date(2026, 4, 2), metric_value=0.8),
        SignalMetricPointDTO(metric_name="hhi", metric_date=date(2026, 4, 1), metric_value=0.02),
        SignalMetricPointDTO(metric_name="hhi", metric_date=date(2026, 4, 2), metric_value=0.03),
        SignalMetricPointDTO(metric_name="gini", metric_date=date(2026, 4, 1), metric_value=0.25),
        SignalMetricPointDTO(metric_name="gini", metric_date=date(2026, 4, 2), metric_value=0.28),
        SignalMetricPointDTO(metric_name="is_signal", metric_date=date(2026, 4, 2), metric_value=1.0),
        SignalMetricPointDTO(metric_name="is_signal_event", metric_date=date(2026, 4, 2), metric_value=1.0),
        SignalMetricPointDTO(metric_name="market_close_proxy", metric_date=date(2026, 4, 1), metric_value=1.0),
        SignalMetricPointDTO(metric_name="market_close_proxy", metric_date=date(2026, 4, 2), metric_value=1.01),
    ]
    events = [SignalEventDTO(event_id="e1", event_date=date(2026, 4, 2), payload={"top_ratio": 0.45})]
    stats = [
        SignalStatDTO(stat_group="summary", stat_name="trade_day_count", stat_value=20),
        SignalStatDTO(stat_group="summary", stat_name="signal_day_count", stat_value=3),
        SignalStatDTO(stat_group="summary", stat_name="event_count", stat_value=1),
        SignalStatDTO(stat_group="risk", stat_name="risk_score", stat_value=62),
        SignalStatDTO(stat_group="risk", stat_name="recent_20_signal_days", stat_value=3),
        SignalStatDTO(stat_group="horizon_10d", stat_name="alpha", stat_value=-0.01),
        SignalStatDTO(
            stat_group="event_study",
            stat_name="avg_path_post_10d",
            stat_value=-1.5,
            payload={
                "event_count": 1,
                "x_axis": [-1, 0, 1],
                "mean_path": [0.0, -0.5, -1.5],
                "event_paths": [{"event_date": "2026-04-02", "path": [0.0, -0.5, -1.5], "post_10d_return": -1.5}],
                "post_10d_returns": [-1.5],
                "horizon_returns": [{"horizon": 10, "values": [-1.5]}],
            },
        ),
        SignalStatDTO(
            stat_group="forward_returns",
            stat_name="distribution",
            stat_value=1,
            payload={
                "horizons": [
                    {
                        "horizon": 10,
                        "sig_values": [-0.02],
                        "nsig_values": [0.01],
                        "sig_mean": -0.02,
                        "nsig_mean": 0.01,
                        "sig_std": 0.0,
                        "nsig_std": 0.0,
                        "alpha": -0.03,
                        "sig_win_rate": 0.0,
                        "nsig_win_rate": 1.0,
                        "sig_count": 1,
                        "nsig_count": 1,
                    }
                ]
            },
        ),
    ]
    sweeps = [
        SignalParamSweepPointDTO(
            sweep_name="liquidity_sensitivity",
            x_key="top_pct",
            x_value=0.05,
            y_key="threshold",
            y_value=0.45,
            metric_name="alpha",
            metric_value=-0.02,
        )
    ]
    artifacts = [
        SignalArtifactDTO(
            artifact_type="json",
            artifact_key="report",
            uri="/tmp/report.json",
            content_type="application/json",
            size_bytes=1024,
        )
    ]

    payload = SignalDashboardAssembler().build(
        plugin=LiquidityConcentrationPlugin(),
        run=run,
        metrics=metrics,
        events=events,
        stats=stats,
        sweeps=sweeps,
        artifacts=artifacts,
    )

    assert payload.run.run_id == "run-1"
    assert payload.overview.signal_key == "liquidity_concentration"
    assert payload.config_summary["signal_key"] == "liquidity_concentration"
    assert {item.metric_key for item in payload.key_metrics} >= {"trade_day_count", "risk_score", "horizon_10d_alpha"}
    assert [tab.tab_key for tab in payload.tabs] == ["overview", "event-study", "forward-returns", "sensitivity", "current-regime"]
    assert payload.tabs[0].sections[0].section_type == "timeseries"
    assert any(section.section_type == "heatmap" for section in payload.tabs[3].sections)
    assert payload.artifacts[0].artifact_key == "report"
