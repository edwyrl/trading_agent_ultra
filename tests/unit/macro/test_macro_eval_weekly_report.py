from __future__ import annotations

from macro.eval.weekly_report import build_recommendations, build_weekly_report, compute_weekly_metrics


def test_weekly_metrics_computation() -> None:
    rows = [
        {
            "selected": "true",
            "topic": "monetary_policy",
            "should_report": "Y",
            "importance": "H",
            "is_duplicate": "N",
            "missed_note": "",
        },
        {
            "selected": "true",
            "topic": "fx",
            "should_report": "N",
            "importance": "M",
            "is_duplicate": "Y",
            "missed_note": "",
        },
        {
            "selected": "false",
            "topic": "fx",
            "should_report": "Y",
            "importance": "L",
            "is_duplicate": "N",
            "missed_note": "遗漏事件 https://example.com/miss（应覆盖）",
        },
    ]
    metrics = compute_weekly_metrics(rows)

    assert metrics["row_count"] == 3
    assert metrics["selected_precision"] == 0.5
    assert metrics["non_selected_fn_proxy"] == 1.0
    assert metrics["importance_hit_rate"] == 0.5
    assert metrics["duplicate_rate"] == (1 / 3)
    assert metrics["miss_count"] == 1


def test_weekly_recommendations_mapping_and_limit() -> None:
    rows = [
        {
            "selected": "false",
            "topic": "fx",
            "should_report": "Y",
            "importance": "L",
            "is_duplicate": "Y",
            "missed_note": "a",
        },
        {
            "selected": "false",
            "topic": "fx",
            "should_report": "Y",
            "importance": "L",
            "is_duplicate": "Y",
            "missed_note": "b",
        },
        {
            "selected": "true",
            "topic": "fx",
            "should_report": "N",
            "importance": "M",
            "is_duplicate": "Y",
            "missed_note": "c",
        },
        {
            "selected": "true",
            "topic": "monetary_policy",
            "should_report": "Y",
            "importance": "L",
            "is_duplicate": "N",
            "missed_note": "",
        },
    ]
    metrics = compute_weekly_metrics(rows)
    recs = build_recommendations(rows, metrics, max_actions=3)
    report = build_weekly_report(rows, week_label="2026-W15")

    assert len(recs) == 3
    assert recs[0].startswith("[FN/Miss]")
    assert any("[Precision]" in x for x in recs)
    assert any("[Duplicate]" in x for x in recs)
    assert report["week_label"] == "2026-W15"
    assert report["recommendations"] == recs
