from __future__ import annotations

import argparse
import json

from app.container import Container
from macro.notifier import MacroDigestNotifier, ResendEmailClient
from shared.config import settings
from shared.db.session import SessionLocal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send macro event/view digest email via Resend.")
    parser.add_argument("--hours", type=int, default=24, help="Lookback window in hours.")
    parser.add_argument(
        "--eval-mode",
        action="store_true",
        help="Send daily human-eval sample email based on eval pack JSON.",
    )
    parser.add_argument(
        "--eval-pack-path",
        default=None,
        help="Optional eval pack JSON path. Defaults to MACRO_INTEL_EVAL_PACK_PATH.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Build digest but do not send email.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if (not settings.email.api_key.strip() or not settings.email.from_email.strip()) and not args.dry_run:
        print(
            json.dumps(
                {
                    "sent": False,
                    "reason": "email_config_missing",
                    "missing": [
                        key
                        for key, value in {
                            "RESEND_API_KEY": settings.email.api_key,
                            "RESEND_FROM_EMAIL": settings.email.from_email,
                        }.items()
                        if not (value or "").strip()
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    with SessionLocal() as session:
        container = Container(session=session)
        macro_service = container.macro_service()
        repository = macro_service.repository

        client = ResendEmailClient(
            api_key=settings.email.api_key,
            base_url=settings.email.base_url,
            timeout_seconds=settings.macro_intel.timeout_seconds,
        )
        notifier = MacroDigestNotifier(
            repository=repository,
            email_client=client,
            from_email=settings.email.from_email,
            recipients_doc_path=settings.email.digest_recipients_doc_path,
            subject_prefix=settings.email.digest_subject_prefix,
            eval_google_form_url=settings.email.eval_google_form_url,
            eval_form_entry_date=settings.email.eval_form_entry_date,
            eval_form_entry_sample_id=settings.email.eval_form_entry_sample_id,
            eval_form_entry_selected=settings.email.eval_form_entry_selected,
            eval_form_entry_topic=settings.email.eval_form_entry_topic,
            eval_form_entry_event_id=settings.email.eval_form_entry_event_id,
            eval_form_selected_true_value=settings.email.eval_form_selected_true_value,
            eval_form_selected_false_value=settings.email.eval_form_selected_false_value,
        )
        if args.eval_mode:
            result = notifier.send_eval_digest(
                eval_pack_path=args.eval_pack_path or settings.macro_intel.eval_pack_path,
                dry_run=args.dry_run,
            )
        else:
            result = notifier.send_recent_digest(hours=args.hours, dry_run=args.dry_run)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
