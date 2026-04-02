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
    parser.add_argument("--dry-run", action="store_true", help="Build digest but do not send email.")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if not settings.email.api_key.strip() or not settings.email.from_email.strip():
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
        )
        result = notifier.send_recent_digest(hours=args.hours, dry_run=args.dry_run)

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
