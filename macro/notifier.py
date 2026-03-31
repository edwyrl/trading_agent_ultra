from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path
import re
from typing import Any

import httpx

from contracts.macro_contracts import MacroEventHistoryDTO, MacroEventViewDTO, MacroMasterCardDTO
from macro.repository import MacroRepository
from shared.logging import get_logger


class ResendEmailClient:
    def __init__(self, *, api_key: str, base_url: str, timeout_seconds: float = 15.0):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").strip().rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.logger = get_logger(__name__)

    def send(self, *, from_email: str, to_emails: list[str], subject: str, html: str, text: str) -> dict[str, Any]:
        if not self.api_key:
            raise ValueError("RESEND_API_KEY is empty.")
        if not from_email:
            raise ValueError("RESEND_FROM_EMAIL is empty.")
        if not to_emails:
            raise ValueError("No recipients provided.")

        payload = {
            "from": from_email,
            "to": to_emails,
            "subject": subject,
            "html": html,
            "text": text,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = self.base_url if self.base_url.endswith("/emails") else f"{self.base_url}/emails"
        resp = httpx.post(url, json=payload, headers=headers, timeout=self.timeout_seconds)
        resp.raise_for_status()
        body = resp.json() if resp.content else {}
        return body if isinstance(body, dict) else {"raw": body}


class MacroDigestNotifier:
    def __init__(
        self,
        *,
        repository: MacroRepository,
        email_client: ResendEmailClient,
        from_email: str,
        recipients_doc_path: str,
        subject_prefix: str = "[Macro Digest]",
    ):
        self.repository = repository
        self.email_client = email_client
        self.from_email = (from_email or "").strip()
        self.recipients_doc_path = recipients_doc_path
        self.subject_prefix = subject_prefix
        self.logger = get_logger(__name__)

    def send_recent_digest(self, *, hours: int = 24, dry_run: bool = False) -> dict[str, Any]:
        now = datetime.now(UTC)
        since_at = now - timedelta(hours=hours)

        histories = self.repository.list_event_history_since(since_at)
        if not histories:
            return {
                "sent": False,
                "reason": "no_recent_events",
                "hours": hours,
                "history_count": 0,
                "view_count": 0,
            }

        history_ids = [h.history_id for h in histories]
        views = self.repository.list_event_views(history_ids=history_ids, created_since=since_at)
        latest_master = self.repository.get_latest_master(as_of_date=now.date())
        recipients = self.load_recipients_from_doc(self.recipients_doc_path)
        if not recipients:
            return {
                "sent": False,
                "reason": "no_recipients",
                "hours": hours,
                "history_count": len(histories),
                "view_count": len(views),
            }

        subject = self._build_subject(hours=hours, now=now, history_count=len(histories))
        html_body = self._build_html(
            now=now,
            hours=hours,
            histories=histories,
            views=views,
            latest_master=latest_master,
        )
        text_body = self._build_text(
            now=now,
            hours=hours,
            histories=histories,
            views=views,
            latest_master=latest_master,
        )

        if dry_run:
            return {
                "sent": False,
                "reason": "dry_run",
                "hours": hours,
                "history_count": len(histories),
                "view_count": len(views),
                "recipients": recipients,
                "subject": subject,
            }

        resp = self.email_client.send(
            from_email=self.from_email,
            to_emails=recipients,
            subject=subject,
            html=html_body,
            text=text_body,
        )
        return {
            "sent": True,
            "hours": hours,
            "history_count": len(histories),
            "view_count": len(views),
            "recipients": recipients,
            "subject": subject,
            "provider_response": resp,
        }

    @staticmethod
    def load_recipients_from_doc(path: str) -> list[str]:
        file_path = Path(path)
        if not file_path.exists():
            return []
        text = file_path.read_text(encoding="utf-8")
        pattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
        seen: set[str] = set()
        recipients: list[str] = []
        for email in pattern.findall(text):
            lowered = email.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            recipients.append(lowered)
        return recipients

    def _build_subject(self, *, hours: int, now: datetime, history_count: int) -> str:
        ts = now.astimezone().strftime("%Y-%m-%d %H:%M")
        return f"{self.subject_prefix} {hours}h 宏观事件观点摘要 ({history_count}条, {ts})"

    def _build_html(
        self,
        *,
        now: datetime,
        hours: int,
        histories: list[MacroEventHistoryDTO],
        views: list[MacroEventViewDTO],
        latest_master: MacroMasterCardDTO | None,
    ) -> str:
        theme_counter = Counter(h.theme_type.value for h in histories)
        views_by_history: dict[str, list[MacroEventViewDTO]] = defaultdict(list)
        for view in views:
            views_by_history[view.history_id].append(view)

        rows: list[str] = []
        for idx, h in enumerate(histories[:30], start=1):
            related = views_by_history.get(h.history_id, [])
            view_line = " / ".join(
                f"{v.view_type.value}:{v.stance.value}({v.score:.2f})" for v in sorted(related, key=lambda x: -x.score)[:3]
            )
            if not view_line:
                view_line = "无观点记录"
            rows.append(
                "<li>"
                f"<b>{idx}. [{escape(h.theme_type.value)}] {escape(h.title)}</b><br/>"
                f"状态: {escape(h.event_status.value)} | 时间: {escape(h.created_at.isoformat())}<br/>"
                f"观点: {escape(view_line)}<br/>"
                f"事实: {escape((h.fact_summary or '')[:240])}"
                "</li>"
            )

        theme_summary = " / ".join(f"{k}:{v}" for k, v in theme_counter.items())
        master_block = ""
        if latest_master:
            biases = ", ".join(b.value for b in latest_master.current_macro_bias)
            master_block = (
                "<p>"
                f"<b>最新 Macro Master:</b> {escape(latest_master.version)}<br/>"
                f"Bias: {escape(biases)}<br/>"
                f"Mainline: {escape(latest_master.macro_mainline[:220])}"
                "</p>"
            )

        return (
            "<html><body>"
            f"<h3>宏观近{hours}小时事件与观点摘要</h3>"
            f"<p>生成时间(UTC): {escape(now.isoformat())}</p>"
            f"<p>事件数: {len(histories)} | 观点数: {len(views)} | 主题分布: {escape(theme_summary)}</p>"
            f"{master_block}"
            "<ol>"
            f"{''.join(rows)}"
            "</ol>"
            "</body></html>"
        )

    def _build_text(
        self,
        *,
        now: datetime,
        hours: int,
        histories: list[MacroEventHistoryDTO],
        views: list[MacroEventViewDTO],
        latest_master: MacroMasterCardDTO | None,
    ) -> str:
        theme_counter = Counter(h.theme_type.value for h in histories)
        views_by_history: dict[str, list[MacroEventViewDTO]] = defaultdict(list)
        for view in views:
            views_by_history[view.history_id].append(view)

        lines = [
            f"宏观近{hours}小时事件与观点摘要",
            f"生成时间(UTC): {now.isoformat()}",
            f"事件数: {len(histories)}",
            f"观点数: {len(views)}",
            "主题分布: " + ", ".join(f"{k}:{v}" for k, v in theme_counter.items()),
        ]
        if latest_master:
            lines.extend(
                [
                    f"最新Master版本: {latest_master.version}",
                    "Bias: " + ", ".join(b.value for b in latest_master.current_macro_bias),
                    f"Mainline: {latest_master.macro_mainline}",
                ]
            )

        lines.append("")
        for idx, h in enumerate(histories[:30], start=1):
            related = views_by_history.get(h.history_id, [])
            view_line = " / ".join(
                f"{v.view_type.value}:{v.stance.value}({v.score:.2f})" for v in sorted(related, key=lambda x: -x.score)[:3]
            )
            if not view_line:
                view_line = "无观点记录"
            lines.extend(
                [
                    f"{idx}. [{h.theme_type.value}] {h.title}",
                    f"   状态: {h.event_status.value} | 时间: {h.created_at.isoformat()}",
                    f"   观点: {view_line}",
                    f"   事实: {(h.fact_summary or '')[:240]}",
                ]
            )
        return "\n".join(lines)
