from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from macro.eval.weekly_report import build_weekly_report, load_feedback_rows, render_weekly_markdown


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build weekly macro eval report from feedback CSV.")
    parser.add_argument("--input-csv", required=True, help="Path to weekly feedback CSV.")
    parser.add_argument(
        "--week-label",
        default=date.today().isoformat(),
        help="Week label shown in report (e.g. 2026-W15).",
    )
    parser.add_argument(
        "--output-md",
        default="logs/macro_eval_weekly_report.md",
        help="Markdown output path.",
    )
    parser.add_argument(
        "--output-json",
        default="logs/macro_eval_weekly_report.json",
        help="JSON output path.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    rows = load_feedback_rows(args.input_csv)
    report = build_weekly_report(rows, week_label=args.week_label)
    markdown = render_weekly_markdown(report)

    output_md = Path(args.output_md)
    output_json = Path(args.output_json)
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_json.parent.mkdir(parents=True, exist_ok=True)

    output_md.write_text(markdown, encoding="utf-8")
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "input_csv": args.input_csv,
                "week_label": args.week_label,
                "row_count": len(rows),
                "output_md": str(output_md),
                "output_json": str(output_json),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
