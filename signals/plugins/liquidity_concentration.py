from __future__ import annotations

import base64
import json
import math
from datetime import date
from pathlib import Path
from typing import Any

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
from signals.plugins.common import (
    cooldown_events,
    expanding_percentile,
    make_metric_card,
    mean,
    metric_series,
    metric_values,
    risk_score,
    rolling_consecutive_true,
    rolling_percentile,
    section,
    stat_payload,
    stats_map,
    std,
    sweep_payload,
    yearly_event_counts,
)
from signals.services.market_data_provider import DailySnapshotRow, MarketDataProvider


class LiquidityConcentrationPlugin(BaseSignalPlugin):
    signal_key = "liquidity_concentration"

    def meta(self) -> SignalPluginMetaDTO:
        return SignalPluginMetaDTO(
            signal_key=self.signal_key,
            name="Liquidity Concentration",
            description="Top liquidity concentration timing signal on dynamic A-share universe.",
            version="v2",
            config_schema={
                "consecutive_days": {"type": "integer", "default": 3, "minimum": 1},
                "top_pct": {"type": "number", "default": 0.05, "minimum": 0.001, "maximum": 0.5},
                "threshold": {"type": "number", "default": 0.45, "minimum": 0.01, "maximum": 1.0},
                "use_money": {"type": "boolean", "default": True},
                "pct_lookback": {"type": "integer", "default": 1260, "minimum": 20},
                "signal_cooldown": {"type": "integer", "default": 5, "minimum": 0},
                "horizons": {"type": "array", "items_type": "integer", "default": [1, 3, 5, 10, 20, 30]},
                "sens_top_pcts": {"type": "array", "items_type": "number", "default": [0.03, 0.05, 0.08, 0.1, 0.15]},
                "sens_thresholds": {"type": "array", "items_type": "number", "default": [0.3, 0.35, 0.4, 0.45, 0.5, 0.55]},
                "sens_fwd_day": {"type": "integer", "default": 10, "minimum": 1},
                "event_pre": {"type": "integer", "default": 10, "minimum": 1},
                "event_post": {"type": "integer", "default": 30, "minimum": 1},
            },
            default_config=self.default_config(),
            evaluation_modes=[EvaluationMode.EVENT_STUDY, EvaluationMode.FACTOR_IC, EvaluationMode.PORTFOLIO_BACKTEST],
        )

    def evaluation_modes(self) -> list[EvaluationMode]:
        return [EvaluationMode.EVENT_STUDY, EvaluationMode.FACTOR_IC, EvaluationMode.PORTFOLIO_BACKTEST]

    def default_config(self) -> dict[str, Any]:
        return {
            "consecutive_days": 3,
            "top_pct": 0.05,
            "threshold": 0.45,
            "use_money": True,
            "pct_lookback": 252 * 5,
            "signal_cooldown": 5,
            "horizons": [1, 3, 5, 10, 20, 30],
            "sens_top_pcts": [0.03, 0.05, 0.08, 0.10, 0.15],
            "sens_thresholds": [0.30, 0.35, 0.40, 0.45, 0.50, 0.55],
            "sens_fwd_day": 10,
            "event_pre": 10,
            "event_post": 30,
            "artifact_dir": "logs/signals",
        }

    def validate_config(self, config: dict[str, Any]) -> dict[str, Any]:
        merged = {**self.default_config(), **config}
        if merged["top_pct"] <= 0 or merged["top_pct"] > 0.5:
            raise ValueError("top_pct must be in (0, 0.5]")
        if merged["threshold"] <= 0 or merged["threshold"] >= 1.5:
            raise ValueError("threshold must be in (0, 1.5)")
        if merged["consecutive_days"] < 1:
            raise ValueError("consecutive_days must be >= 1")
        if merged["pct_lookback"] < 20:
            raise ValueError("pct_lookback must be >= 20")
        merged["horizons"] = sorted({int(x) for x in merged.get("horizons", []) if int(x) > 0})
        if not merged["horizons"]:
            raise ValueError("horizons must not be empty")
        merged["sens_top_pcts"] = [float(x) for x in merged.get("sens_top_pcts", []) if float(x) > 0]
        merged["sens_thresholds"] = [float(x) for x in merged.get("sens_thresholds", []) if float(x) > 0]
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
        _ = run_id
        trade_days = provider.list_trade_days(start_date=start_date, end_date=end_date)
        top_pct = float(config["top_pct"])
        use_money = bool(config["use_money"])

        rows: list[dict[str, Any]] = []
        snapshots: dict[date, list[DailySnapshotRow]] = {}
        for day in trade_days:
            snapshot = provider.fetch_daily_snapshot(as_of_date=day)
            snapshots[day] = snapshot
            values = [
                float(item.amount if use_money else item.vol)
                for item in snapshot
                if float(item.amount if use_money else item.vol) > 0
            ]
            if len(values) < 10:
                continue
            total = float(sum(values))
            if total <= 0:
                continue
            top_ratio, top_n, top_sum = _compute_top_ratio(values=values, top_pct=top_pct)
            share = [value / total for value in values]
            hhi = float(sum(item * item for item in share))
            gini = _compute_gini(values)
            rows.append(
                {
                    "date": day,
                    "top_ratio": top_ratio,
                    "top_n": float(top_n),
                    "total": total,
                    "top_sum": top_sum,
                    "hhi": hhi,
                    "gini": gini,
                }
            )

        rows.sort(key=lambda item: item["date"])
        if not rows:
            state.summary = {
                "status": "empty",
                "message": "No eligible market data in selected date range.",
                "headline_metric_label": "Latest TopRatio",
                "headline_metric_display": "-",
            }
            state.transient = {"rows": [], "snapshots": snapshots}
            return

        top_ratios = [float(row["top_ratio"]) for row in rows]
        over_threshold = [value >= float(config["threshold"]) for value in top_ratios]
        is_signal = rolling_consecutive_true(over_threshold, int(config["consecutive_days"]))
        rolling_pct = rolling_percentile(top_ratios, int(config["pct_lookback"]))
        expanding_pct = expanding_percentile(top_ratios)
        is_signal_event = cooldown_events(is_signal, int(config["signal_cooldown"]))

        for index, row in enumerate(rows):
            day = row["date"]
            state.metrics.extend(
                [
                    SignalMetricPointDTO(metric_name="top_ratio", metric_date=day, metric_value=float(row["top_ratio"])),
                    SignalMetricPointDTO(metric_name="hhi", metric_date=day, metric_value=float(row["hhi"])),
                    SignalMetricPointDTO(metric_name="gini", metric_date=day, metric_value=float(row["gini"])),
                    SignalMetricPointDTO(metric_name="rolling_pct", metric_date=day, metric_value=float(rolling_pct[index])),
                    SignalMetricPointDTO(metric_name="expanding_pct", metric_date=day, metric_value=float(expanding_pct[index])),
                    SignalMetricPointDTO(
                        metric_name="is_signal",
                        metric_date=day,
                        metric_value=1.0 if is_signal[index] else 0.0,
                        payload={"bool_value": is_signal[index]},
                    ),
                    SignalMetricPointDTO(
                        metric_name="is_signal_event",
                        metric_date=day,
                        metric_value=1.0 if is_signal_event[index] else 0.0,
                        payload={"bool_value": is_signal_event[index]},
                    ),
                    SignalMetricPointDTO(metric_name="total_liquidity", metric_date=day, metric_value=float(row["total"])),
                ]
            )
            row["rolling_pct"] = rolling_pct[index]
            row["expanding_pct"] = expanding_pct[index]
            row["is_signal"] = is_signal[index]
            row["is_signal_event"] = is_signal_event[index]

        latest = rows[-1]
        state.summary = {
            "trade_day_count": len(rows),
            "signal_day_count": sum(1 for row in rows if row["is_signal"]),
            "event_count": sum(1 for row in rows if row["is_signal_event"]),
            "latest_date": latest["date"].isoformat(),
            "latest_top_ratio": latest["top_ratio"],
            "latest_expanding_pct": latest["expanding_pct"],
            "headline_metric_label": "Latest TopRatio",
            "headline_metric_value": latest["top_ratio"],
            "headline_metric_display": f"{latest['top_ratio']:.2%}",
        }
        state.transient = {
            "rows": rows,
            "snapshots": snapshots,
        }

    def detect_events(self, *, run_id: str, config: dict[str, Any], state: SignalPluginState) -> None:
        _ = config
        rows = list(state.transient.get("rows", []))
        state.events = []
        for row in rows:
            if not row.get("is_signal_event"):
                continue
            event_id = f"{run_id}:{row['date']:%Y%m%d}"
            state.events.append(
                SignalEventDTO(
                    event_id=event_id,
                    event_date=row["date"],
                    event_type="SIGNAL_EVENT",
                    score=float(row["top_ratio"]),
                    payload={
                        "top_ratio": row["top_ratio"],
                        "hhi": row["hhi"],
                        "gini": row["gini"],
                        "expanding_pct": row["expanding_pct"],
                        "rolling_pct": row["rolling_pct"],
                    },
                )
            )

    def evaluate(
        self,
        *,
        run: SignalRunRequestDTO,
        provider: MarketDataProvider,
        state: SignalPluginState,
    ) -> None:
        rows = list(state.transient.get("rows", []))
        if not rows:
            return

        config = self.validate_config(run.config)
        returns_map = provider.fetch_market_returns(
            start_date=run.date_range.start_date,
            end_date=run.date_range.end_date,
        )
        dates = [row["date"] for row in rows]

        close = 1.0
        close_series: list[float] = []
        for day in dates:
            close *= 1.0 + float(returns_map.get(day, 0.0))
            close_series.append(close)
            state.metrics.append(
                SignalMetricPointDTO(
                    metric_name="market_close_proxy",
                    metric_date=day,
                    metric_value=float(close),
                    payload={"label": "All A-share average return proxy"},
                )
            )

        horizons = [int(value) for value in config["horizons"]]
        forward_returns: dict[int, list[float | None]] = {horizon: [None for _ in dates] for horizon in horizons}
        for index in range(len(dates)):
            for horizon in horizons:
                if index + horizon >= len(close_series):
                    continue
                base = close_series[index]
                nxt = close_series[index + horizon]
                if base <= 0:
                    continue
                forward_returns[horizon][index] = (nxt / base) - 1.0

        forward_return_buckets: list[dict[str, Any]] = []
        for horizon in horizons:
            sig_values: list[float] = []
            nsig_values: list[float] = []
            for index, row in enumerate(rows):
                value = forward_returns[horizon][index]
                if value is None:
                    continue
                if row["is_signal"]:
                    sig_values.append(value)
                else:
                    nsig_values.append(value)
            if not sig_values or not nsig_values:
                continue

            sig_mean = mean(sig_values)
            nsig_mean = mean(nsig_values)
            alpha = sig_mean - nsig_mean
            sig_win_rate = mean([1.0 if value > 0 else 0.0 for value in sig_values])
            nsig_win_rate = mean([1.0 if value > 0 else 0.0 for value in nsig_values])
            sig_std = std(sig_values)
            nsig_std = std(nsig_values)
            forward_return_buckets.append(
                {
                    "horizon": horizon,
                    "sig_values": sig_values,
                    "nsig_values": nsig_values,
                    "sig_mean": sig_mean,
                    "nsig_mean": nsig_mean,
                    "sig_std": sig_std,
                    "nsig_std": nsig_std,
                    "alpha": alpha,
                    "sig_win_rate": sig_win_rate,
                    "nsig_win_rate": nsig_win_rate,
                    "sig_count": len(sig_values),
                    "nsig_count": len(nsig_values),
                }
            )
            state.stats.extend(
                [
                    SignalStatDTO(stat_group=f"horizon_{horizon}d", stat_name="sig_mean", stat_value=sig_mean),
                    SignalStatDTO(stat_group=f"horizon_{horizon}d", stat_name="nsig_mean", stat_value=nsig_mean),
                    SignalStatDTO(stat_group=f"horizon_{horizon}d", stat_name="sig_std", stat_value=sig_std),
                    SignalStatDTO(stat_group=f"horizon_{horizon}d", stat_name="nsig_std", stat_value=nsig_std),
                    SignalStatDTO(stat_group=f"horizon_{horizon}d", stat_name="alpha", stat_value=alpha),
                    SignalStatDTO(stat_group=f"horizon_{horizon}d", stat_name="sig_win_rate", stat_value=sig_win_rate),
                    SignalStatDTO(stat_group=f"horizon_{horizon}d", stat_name="nsig_win_rate", stat_value=nsig_win_rate),
                    SignalStatDTO(stat_group=f"horizon_{horizon}d", stat_name="sig_count", stat_value=float(len(sig_values))),
                    SignalStatDTO(stat_group=f"horizon_{horizon}d", stat_name="nsig_count", stat_value=float(len(nsig_values))),
                ]
            )
        state.stats.append(
            SignalStatDTO(
                stat_group="forward_returns",
                stat_name="distribution",
                stat_value=float(len(forward_return_buckets)),
                payload={"horizons": forward_return_buckets},
            )
        )

        recent_days = rows[-20:]
        recent_signal_days = sum(1 for row in recent_days if row["is_signal"])
        latest = rows[-1]
        score = risk_score(
            hist_pct=float(latest["expanding_pct"]),
            is_signal=bool(latest["is_signal"]),
            recent_days=recent_signal_days,
        )
        state.stats.extend(
            [
                SignalStatDTO(stat_group="summary", stat_name="trade_day_count", stat_value=float(len(rows))),
                SignalStatDTO(stat_group="summary", stat_name="signal_day_count", stat_value=float(sum(1 for row in rows if row["is_signal"]))),
                SignalStatDTO(stat_group="summary", stat_name="event_count", stat_value=float(sum(1 for row in rows if row["is_signal_event"]))),
                SignalStatDTO(stat_group="risk", stat_name="risk_score", stat_value=float(score)),
                SignalStatDTO(stat_group="risk", stat_name="recent_20_signal_days", stat_value=float(recent_signal_days)),
            ]
        )

        event_pre = int(config["event_pre"])
        event_post = int(config["event_post"])
        event_dates = {event.event_date for event in state.events}
        event_indices = [index for index, day in enumerate(dates) if day in event_dates]
        event_paths: list[list[float]] = []
        event_path_payload: list[dict[str, Any]] = []
        post_10d_returns: list[float] = []
        event_horizon_returns: dict[int, list[float]] = {horizon: [] for horizon in horizons}
        for index in event_indices:
            if index - event_pre < 0 or index + event_post >= len(close_series):
                continue
            window = close_series[index - event_pre : index + event_post + 1]
            base = window[event_pre]
            if base <= 0:
                continue
            path = [((value / base) - 1.0) * 100.0 for value in window]
            event_paths.append(path)
            post_10_index = min(event_pre + 10, len(path) - 1)
            post_10d_returns.append(float(path[post_10_index]))
            event_path_payload.append(
                {
                    "event_date": dates[index].isoformat(),
                    "path": path,
                    "post_10d_return": float(path[post_10_index]),
                }
            )
            for horizon in horizons:
                value = forward_returns[horizon][index]
                if value is not None:
                    event_horizon_returns[horizon].append(float(value) * 100.0)

        if event_paths:
            mean_path = [mean([path[index] for path in event_paths]) for index in range(len(event_paths[0]))]
            state.stats.append(
                SignalStatDTO(
                    stat_group="event_study",
                    stat_name="avg_path_post_10d",
                    stat_value=float(mean_path[min(event_pre + 10, len(mean_path) - 1)]),
                    payload={
                        "event_count": len(event_paths),
                        "x_axis": list(range(-event_pre, event_post + 1)),
                        "mean_path": mean_path,
                        "event_paths": event_path_payload,
                        "post_10d_returns": post_10d_returns,
                        "horizon_returns": [
                            {"horizon": horizon, "values": values}
                            for horizon, values in event_horizon_returns.items()
                            if values
                        ],
                    },
                )
            )

        state.param_sweeps = self._build_param_sweeps(
            rows=rows,
            close_series=close_series,
            config=config,
            snapshots=state.transient.get("snapshots", {}),
        )

    def build_artifacts(self, *, run_id: str, config: dict[str, Any], state: SignalPluginState) -> None:
        artifact_dir = Path(config.get("artifact_dir", "logs/signals")) / run_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        report_payload = {
            "summary": state.summary,
            "metrics": [point.model_dump(mode="json") for point in state.metrics],
            "events": [event.model_dump(mode="json") for event in state.events],
            "stats": [stat.model_dump(mode="json") for stat in state.stats],
            "param_sweeps": [point.model_dump(mode="json") for point in state.param_sweeps],
        }
        report_path = artifact_dir / "report.json"
        report_path.write_text(json.dumps(report_payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

        png_bytes = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wm5d8QAAAAASUVORK5CYII="
        )
        png_path = artifact_dir / "dashboard.png"
        png_path.write_bytes(png_bytes)

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
        return [
            make_metric_card(
                metric_key="trade_day_count",
                label="Trade Days",
                value=stat_values.get(("summary", "trade_day_count"), 0.0),
                display=f"{stat_values.get(('summary', 'trade_day_count'), 0.0):.0f}",
            ),
            make_metric_card(
                metric_key="signal_day_count",
                label="Signal Days",
                value=stat_values.get(("summary", "signal_day_count"), 0.0),
                display=f"{stat_values.get(('summary', 'signal_day_count'), 0.0):.0f}",
            ),
            make_metric_card(
                metric_key="event_count",
                label="Signal Events",
                value=stat_values.get(("summary", "event_count"), 0.0),
                display=f"{stat_values.get(('summary', 'event_count'), 0.0):.0f}",
            ),
            make_metric_card(
                metric_key="risk_score",
                label="Risk Score",
                value=stat_values.get(("risk", "risk_score"), 0.0),
                display=f"{stat_values.get(('risk', 'risk_score'), 0.0):.0f}",
            ),
            make_metric_card(
                metric_key="horizon_10d_alpha",
                label="10D Alpha",
                value=stat_values.get(("horizon_10d", "alpha"), 0.0),
                unit="pct",
                display=f"{stat_values.get(('horizon_10d', 'alpha'), 0.0):+.2%}",
            ),
        ]

    def build_dashboard_tabs(
        self,
        *,
        run: SignalRunStatusDTO,
        metrics: list[SignalMetricPointDTO],
        events: list[SignalEventDTO],
        stats: list[SignalStatDTO],
        sweeps: list[SignalParamSweepPointDTO],
    ) -> list[DashboardTabDTO]:
        _ = run
        event_study = stat_payload(stats, stat_group="event_study", stat_name="avg_path_post_10d")
        forward_returns = stat_payload(stats, stat_group="forward_returns", stat_name="distribution")
        risk_values = stats_map(stats)
        top_ratio_values = metric_values(metrics, metric_name="top_ratio")
        rows = _rows_from_metrics(metrics)

        overview_sections = [
            section(
                section_key="top-ratio-vs-market",
                title="TopRatio vs All A-share Return Proxy",
                section_type="timeseries",
                eyebrow="Overview",
                payload={
                    "series": [
                        _series_payload(metrics, metric_name="top_ratio", label="TopRatio"),
                        _series_payload(metrics, metric_name="market_close_proxy", label="All A-share Return Proxy"),
                    ],
                    "y_axis_label": "Value",
                },
            ),
            section(
                section_key="concentration-extended",
                title="Extended Concentration: HHI and Gini",
                section_type="timeseries",
                eyebrow="Overview",
                payload={
                    "series": [
                        _series_payload(metrics, metric_name="hhi", label="HHI"),
                        _series_payload(metrics, metric_name="gini", label="Gini"),
                    ],
                    "y_axis_label": "Value",
                },
            ),
            section(
                section_key="top-ratio-histogram",
                title="TopRatio Historical Distribution",
                section_type="histogram",
                eyebrow="Distribution",
                payload={
                    "values": top_ratio_values,
                    "x_label": "TopRatio",
                    "y_label": "Density",
                    "bins": 60,
                    "threshold": float(run.config.get("threshold", 0.0)),
                },
            ),
            section(
                section_key="yearly-events",
                title="Yearly Signal Event Count",
                section_type="bar",
                eyebrow="Events",
                payload={
                    "categories": [item["category"] for item in yearly_event_counts(rows)],
                    "series": [{"label": "Signal events", "values": [item["value"] for item in yearly_event_counts(rows)], "color": "#ff8a7a"}],
                    "x_label": "Year",
                    "y_label": "Events",
                    "mode": "group",
                },
            ),
            section(
                section_key="percentile-series",
                title="TopRatio Historical Percentile",
                section_type="timeseries",
                eyebrow="Percentile",
                payload={
                    "series": [
                        _series_payload(metrics, metric_name="rolling_pct", label="Rolling Percentile"),
                        _series_payload(metrics, metric_name="expanding_pct", label="Expanding Percentile"),
                    ],
                    "y_axis_label": "Percentile",
                    "y_tick_format": ".0%",
                },
            ),
        ]

        event_sections = [
            section(
                section_key="event-paths",
                title="Signal Event Paths",
                section_type="scatter",
                eyebrow="Event Study",
                payload={
                    "traces": [
                        *[
                            {
                                "label": item.get("event_date", "event"),
                                "x": event_study.get("x_axis", []),
                                "y": item.get("path", []),
                                "mode": "lines",
                                "color": "rgba(147, 162, 199, 0.18)",
                                "width": 1,
                                "show_legend": False,
                            }
                            for item in event_study.get("event_paths", [])[:80]
                        ],
                        {
                            "label": "Mean path",
                            "x": event_study.get("x_axis", []),
                            "y": event_study.get("mean_path", []),
                            "mode": "lines",
                            "color": "#ffd36d",
                            "width": 4,
                            "show_legend": True,
                        },
                    ],
                    "x_label": "Days around event",
                    "y_label": "Return from event day (%)",
                    "vertical_lines": [0],
                },
            ),
            section(
                section_key="post-10d-returns",
                title="Post-10D Event Returns",
                section_type="scatter",
                eyebrow="Post Event",
                payload={
                    "traces": [
                        {
                            "label": "Post 10D",
                            "x": list(range(1, len(event_study.get("post_10d_returns", [])) + 1)),
                            "y": event_study.get("post_10d_returns", []),
                            "mode": "markers",
                            "color": "#7ad0ff",
                        }
                    ],
                    "x_label": "Event #",
                    "y_label": "Post-10D return (%)",
                },
            ),
            section(
                section_key="event-horizon-boxplots",
                title="Event Return Boxplots",
                section_type="boxplot",
                eyebrow="Holding Windows",
                payload={
                    "series": [
                        {"label": f"{item.get('horizon', 0)}d", "values": item.get("values", []), "color": "#7ad0ff"}
                        for item in event_study.get("horizon_returns", [])
                    ],
                    "x_label": "Holding horizon",
                    "y_label": "Return (%)",
                },
            ),
        ]

        forward_buckets = list(forward_returns.get("horizons", []))
        categories = [f"{int(item.get('horizon', 0))}d" for item in forward_buckets]
        forward_sections = [
            section(
                section_key="forward-mean-returns",
                title="Signal vs Non-signal Mean Returns",
                section_type="bar",
                eyebrow="Forward Returns",
                payload={
                    "categories": categories,
                    "series": [
                        {
                            "label": "Signal days",
                            "values": [float(item.get("sig_mean", 0.0)) for item in forward_buckets],
                            "color": "#ff8a7a",
                            "error_values": [_standard_error(float(item.get("sig_std", 0.0)), int(item.get("sig_count", 0))) for item in forward_buckets],
                        },
                        {
                            "label": "Non-signal days",
                            "values": [float(item.get("nsig_mean", 0.0)) for item in forward_buckets],
                            "color": "#8be4a5",
                            "error_values": [_standard_error(float(item.get("nsig_std", 0.0)), int(item.get("nsig_count", 0))) for item in forward_buckets],
                        },
                    ],
                    "x_label": "Horizon",
                    "y_label": "Mean return",
                    "y_tick_format": ".1%",
                    "mode": "group",
                },
            ),
            section(
                section_key="forward-alpha",
                title="Signal Alpha by Horizon",
                section_type="bar",
                eyebrow="Alpha",
                payload={
                    "categories": categories,
                    "series": [
                        {
                            "label": "Alpha",
                            "values": [float(item.get("alpha", 0.0)) for item in forward_buckets],
                            "colors": ["#ff8a7a" if float(item.get("alpha", 0.0)) < 0 else "#8be4a5" for item in forward_buckets],
                        }
                    ],
                    "x_label": "Horizon",
                    "y_label": "Alpha",
                    "y_tick_format": ".1%",
                    "mode": "group",
                },
            ),
            section(
                section_key="forward-violin",
                title="Forward Return Violin Distribution",
                section_type="violin",
                eyebrow="Distribution",
                payload={
                    "series": [
                        {
                            "label": "Signal days",
                            "color": "rgba(255, 138, 122, 0.48)",
                            "line_color": "#ff8a7a",
                            "side": "negative",
                            "items": [
                                {"category": f"{int(item.get('horizon', 0))}d", "values": item.get("sig_values", [])}
                                for item in forward_buckets
                            ],
                        },
                        {
                            "label": "Non-signal days",
                            "color": "rgba(139, 228, 165, 0.42)",
                            "line_color": "#8be4a5",
                            "side": "positive",
                            "items": [
                                {"category": f"{int(item.get('horizon', 0))}d", "values": item.get("nsig_values", [])}
                                for item in forward_buckets
                            ],
                        },
                    ],
                    "x_label": "Horizon",
                    "y_label": "Forward return",
                    "y_tick_format": ".1%",
                },
            ),
        ]

        sensitivity_sections = [
            section(
                section_key="sensitivity-matrix",
                title="Parameter Sensitivity",
                section_type="heatmap",
                eyebrow="Sensitivity",
                payload=sweep_payload(sweeps),
            )
        ]

        current_sections = [
            section(
                section_key="current-risk",
                title="Current Risk Snapshot",
                section_type="stat_cards",
                eyebrow="Current Regime",
                payload={
                    "cards": [
                        make_metric_card(
                            metric_key="risk_score",
                            label="Risk Score",
                            value=risk_values.get(("risk", "risk_score"), 0.0),
                            display=f"{risk_values.get(('risk', 'risk_score'), 0.0):.0f}",
                        ).model_dump(mode="json"),
                        make_metric_card(
                            metric_key="recent_20_signal_days",
                            label="Recent 20D Signals",
                            value=risk_values.get(("risk", "recent_20_signal_days"), 0.0),
                            display=f"{risk_values.get(('risk', 'recent_20_signal_days'), 0.0):.0f}",
                        ).model_dump(mode="json"),
                        make_metric_card(
                            metric_key="latest_top_ratio",
                            label="Latest TopRatio",
                            value=top_ratio_values[-1] if top_ratio_values else 0.0,
                            display=f"{(top_ratio_values[-1] if top_ratio_values else 0.0):.2%}",
                        ).model_dump(mode="json"),
                    ]
                },
            ),
            section(
                section_key="recent-top-ratio",
                title="Recent 60D TopRatio",
                section_type="timeseries",
                eyebrow="Current Regime",
                payload={
                    "series": [
                        _tail_series(_series_payload(metrics, metric_name="top_ratio", label="TopRatio"), limit=60),
                        _tail_series(
                            _series_payload(metrics, metric_name="market_close_proxy", label="All A-share Return Proxy"),
                            limit=60,
                        ),
                    ],
                    "y_axis_label": "Value",
                },
            ),
            section(
                section_key="recent-percentile",
                title="Recent 60D Historical Percentile",
                section_type="timeseries",
                eyebrow="Current Regime",
                payload={
                    "series": [
                        _tail_series(_series_payload(metrics, metric_name="expanding_pct", label="Expanding Percentile"), limit=60)
                    ],
                    "y_axis_label": "Percentile",
                    "y_tick_format": ".0%",
                },
            ),
        ]

        return [
            DashboardTabDTO(tab_key="overview", label="Overview", sections=overview_sections),
            DashboardTabDTO(tab_key="event-study", label="Event Study", sections=event_sections),
            DashboardTabDTO(tab_key="forward-returns", label="Forward Returns", sections=forward_sections),
            DashboardTabDTO(tab_key="sensitivity", label="Sensitivity", sections=sensitivity_sections),
            DashboardTabDTO(tab_key="current-regime", label="Current Regime", sections=current_sections),
        ]

    def _build_param_sweeps(
        self,
        *,
        rows: list[dict[str, Any]],
        close_series: list[float],
        config: dict[str, Any],
        snapshots: dict[date, list[DailySnapshotRow]],
    ) -> list[SignalParamSweepPointDTO]:
        sens_top_pcts = [float(value) for value in config.get("sens_top_pcts", [])]
        sens_thresholds = [float(value) for value in config.get("sens_thresholds", [])]
        sens_fwd_day = int(config.get("sens_fwd_day", 10))
        use_money = bool(config.get("use_money", True))

        fallback_top_ratio = [float(row["top_ratio"]) for row in rows]
        forward_values: list[float | None] = [None for _ in rows]
        for index in range(len(rows)):
            if index + sens_fwd_day >= len(close_series):
                continue
            base = close_series[index]
            nxt = close_series[index + sens_fwd_day]
            if base <= 0:
                continue
            forward_values[index] = (nxt / base) - 1.0

        points: list[SignalParamSweepPointDTO] = []
        for top_pct in sens_top_pcts:
            if snapshots:
                top_ratios = []
                for row in rows:
                    snapshot = snapshots.get(row["date"], [])
                    values = [float(item.amount if use_money else item.vol) for item in snapshot if float(item.amount if use_money else item.vol) > 0]
                    if values:
                        top_ratio, _, _ = _compute_top_ratio(values=values, top_pct=top_pct)
                        top_ratios.append(top_ratio)
                    else:
                        top_ratios.append(float(row["top_ratio"]))
            else:
                top_ratios = fallback_top_ratio

            for threshold in sens_thresholds:
                signal_mask = [ratio > threshold for ratio in top_ratios]
                sig_values = [value for index, value in enumerate(forward_values) if value is not None and signal_mask[index]]
                nsig_values = [value for index, value in enumerate(forward_values) if value is not None and not signal_mask[index]]
                if not sig_values or not nsig_values:
                    continue
                alpha = mean(sig_values) - mean(nsig_values)
                win_rate = mean([1.0 if value > 0 else 0.0 for value in sig_values])
                freq = float(sum(1 for flag in signal_mask if flag)) / float(len(signal_mask))
                points.extend(
                    [
                        SignalParamSweepPointDTO(
                            sweep_name="liquidity_sensitivity",
                            x_key="top_pct",
                            x_value=top_pct,
                            y_key="threshold",
                            y_value=threshold,
                            metric_name="alpha",
                            metric_value=alpha,
                        ),
                        SignalParamSweepPointDTO(
                            sweep_name="liquidity_sensitivity",
                            x_key="top_pct",
                            x_value=top_pct,
                            y_key="threshold",
                            y_value=threshold,
                            metric_name="win_rate",
                            metric_value=win_rate,
                        ),
                        SignalParamSweepPointDTO(
                            sweep_name="liquidity_sensitivity",
                            x_key="top_pct",
                            x_value=top_pct,
                            y_key="threshold",
                            y_value=threshold,
                            metric_name="freq",
                            metric_value=freq,
                        ),
                    ]
                )
        return points


def _series_payload(metrics: list[SignalMetricPointDTO], *, metric_name: str, label: str) -> dict[str, Any]:
    return {
        "metric_name": metric_name,
        "label": label,
        "points": [{"date": item_date.isoformat(), "value": float(value)} for item_date, value in metric_series(metrics, metric_name=metric_name)],
    }


def _rows_from_metrics(metrics: list[SignalMetricPointDTO]) -> list[dict[str, Any]]:
    rows: dict[date, dict[str, Any]] = {}
    for item in metrics:
        bucket = rows.setdefault(item.metric_date, {"date": item.metric_date})
        bucket[item.metric_name] = float(item.metric_value)
    return [rows[key] for key in sorted(rows)]


def _tail_series(series_payload: dict[str, Any], *, limit: int) -> dict[str, Any]:
    return {**series_payload, "points": list(series_payload.get("points", []))[-limit:]}


def _compute_top_ratio(*, values: list[float], top_pct: float) -> tuple[float, int, float]:
    total = float(sum(values))
    if total <= 0:
        return 0.0, 0, 0.0
    count = len(values)
    top_n = max(1, min(int(math.ceil(count * top_pct)), count))
    top_values = sorted(values, reverse=True)[:top_n]
    top_sum = float(sum(top_values))
    return top_sum / total, top_n, top_sum


def _compute_gini(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    count = len(sorted_values)
    cumulative = 0.0
    cumulative_sum = 0.0
    for value in sorted_values:
        cumulative += value
        cumulative_sum += cumulative
    if cumulative <= 0:
        return 0.0
    return float((count + 1 - 2 * (cumulative_sum / cumulative)) / count)


def _standard_error(std_value: float, count: int) -> float:
    return std_value / math.sqrt(count) if count > 0 else 0.0
