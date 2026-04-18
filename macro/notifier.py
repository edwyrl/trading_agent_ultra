from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from html import escape
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
        eval_google_form_url: str = "",
        eval_form_entry_date: str = "",
        eval_form_entry_sample_id: str = "",
        eval_form_entry_selected: str = "",
        eval_form_entry_topic: str = "",
        eval_form_entry_event_id: str = "",
        eval_form_selected_true_value: str = "True",
        eval_form_selected_false_value: str = "False",
    ):
        self.repository = repository
        self.email_client = email_client
        self.from_email = (from_email or "").strip()
        self.recipients_doc_path = recipients_doc_path
        self.subject_prefix = subject_prefix
        self.eval_google_form_url = (eval_google_form_url or "").strip()
        self.eval_form_entry_date = (eval_form_entry_date or "").strip()
        self.eval_form_entry_sample_id = (eval_form_entry_sample_id or "").strip()
        self.eval_form_entry_selected = (eval_form_entry_selected or "").strip()
        self.eval_form_entry_topic = (eval_form_entry_topic or "").strip()
        self.eval_form_entry_event_id = (eval_form_entry_event_id or "").strip()
        self.eval_form_selected_true_value = (eval_form_selected_true_value or "True").strip()
        self.eval_form_selected_false_value = (eval_form_selected_false_value or "False").strip()
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

    def send_eval_digest(self, *, eval_pack_path: str, dry_run: bool = False) -> dict[str, Any]:
        pack_file = Path(eval_pack_path)
        if not pack_file.exists():
            return {
                "sent": False,
                "reason": "eval_pack_missing",
                "eval_pack_path": str(pack_file),
            }

        try:
            payload = json.loads(pack_file.read_text(encoding="utf-8"))
        except Exception as exc:
            return {
                "sent": False,
                "reason": "eval_pack_invalid_json",
                "eval_pack_path": str(pack_file),
                "error": str(exc),
            }
        if not isinstance(payload, dict):
            return {
                "sent": False,
                "reason": "eval_pack_invalid_payload",
                "eval_pack_path": str(pack_file),
            }

        selected = payload.get("selected_samples") if isinstance(payload.get("selected_samples"), list) else []
        non_selected = payload.get("non_selected_samples") if isinstance(payload.get("non_selected_samples"), list) else []
        if not selected and not non_selected:
            return {
                "sent": False,
                "reason": "no_eval_samples",
                "eval_pack_path": str(pack_file),
            }

        recipients = self.load_recipients_from_doc(self.recipients_doc_path)
        if not recipients:
            return {
                "sent": False,
                "reason": "no_recipients",
                "selected_count": len(selected),
                "non_selected_count": len(non_selected),
            }

        now = datetime.now(UTC)
        as_of_date = str(payload.get("as_of_date") or now.date().isoformat())
        subject = self._build_eval_subject(
            now=now,
            as_of_date=as_of_date,
            selected_count=len(selected),
            non_selected_count=len(non_selected),
        )
        html_body = self._build_eval_html(
            now=now,
            as_of_date=as_of_date,
            selected_samples=selected,
            non_selected_samples=non_selected,
        )
        text_body = self._build_eval_text(
            now=now,
            as_of_date=as_of_date,
            selected_samples=selected,
            non_selected_samples=non_selected,
        )

        if dry_run:
            return {
                "sent": False,
                "reason": "dry_run",
                "eval_pack_path": str(pack_file),
                "selected_count": len(selected),
                "non_selected_count": len(non_selected),
                "recipients": recipients,
                "subject": subject,
                "text_preview": text_body[:1200],
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
            "eval_pack_path": str(pack_file),
            "selected_count": len(selected),
            "non_selected_count": len(non_selected),
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

    def _build_eval_subject(self, *, now: datetime, as_of_date: str, selected_count: int, non_selected_count: int) -> str:
        ts = now.astimezone().strftime("%Y-%m-%d %H:%M")
        total = selected_count + non_selected_count
        return f"{self.subject_prefix} [Eval] {as_of_date} 人工评审样本 ({total}条, {ts})"

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

    def _build_eval_html(
        self,
        *,
        now: datetime,
        as_of_date: str,
        selected_samples: list[dict[str, Any]],
        non_selected_samples: list[dict[str, Any]],
    ) -> str:
        form_block = ""
        if self.eval_google_form_url:
            form_block = (
                "<p>"
                f"<b>Google Form 填报入口：</b><a href=\"{escape(self.eval_google_form_url)}\">打开表单</a><br/>"
                "每条样本都提供了“预填链接”，点击后已自动填好 date/sample_id/selected/topic/event_id。<br/>"
                "建议最简字段：date / sample_id / selected / topic / "
                "should_report(Y|N) / importance(H|M|L) / is_duplicate(Y|N) / duplicate_of / missed_note / comment"
                "</p>"
            )

        def _sample_lines(sample: dict[str, Any]) -> str:
            sid = str(sample.get("sample_id") or "-")
            title = str(sample.get("title") or "")
            topic = str(sample.get("topic") or "")
            event_id = str(sample.get("event_id") or "")
            selected = str(sample.get("selected")).lower() if "selected" in sample else ""
            score = sample.get("score")
            url = str(sample.get("url") or "")
            domain = str(sample.get("source_domain") or "")
            reject_reason = str(sample.get("reject_reason") or "")
            low_pool_fill = bool(sample.get("low_pool_fill"))
            prefilled_url = self._build_eval_prefilled_form_url(as_of_date=as_of_date, sample=sample)
            meta = f"topic={topic} | score={score} | domain={domain}"
            if reject_reason:
                meta += f" | reject_reason={reject_reason}"
            if low_pool_fill:
                meta += " | low_pool_fill=true"
            prefill_line = ""
            if prefilled_url:
                prefill_line = f"预填表单: <a href=\"{escape(prefilled_url)}\">打开此样本预填链接</a><br/>"
            return (
                "<li>"
                f"<b>[{escape(sid)}] {escape(title)}</b><br/>"
                f"{escape(meta)}<br/>"
                f"event_id={escape(event_id)} | selected={escape(selected)}<br/>"
                f"URL: {escape(url)}<br/>"
                f"{prefill_line}"
                "该不该报(Y/N): ____<br/>"
                "重不重要(H/M/L): ____<br/>"
                "是否重复(Y/N; 若Y填重复sample_id): ____<br/>"
                "漏了什么(可空; title + url + 1行原因): ____"
                "</li>"
            )

        return (
            "<html><body>"
            f"<h3>Macro 人工评审样本（{escape(as_of_date)}）</h3>"
            f"<p>生成时间(UTC): {escape(now.isoformat())}</p>"
            "<p>请按每条样本填写四项判断：该不该报 / 重不重要 / 是否重复 / 漏了什么。</p>"
            f"{form_block}"
            f"<h4>入选样本（{len(selected_samples)}）</h4>"
            "<ol>"
            f"{''.join(_sample_lines(s) for s in selected_samples)}"
            "</ol>"
            f"<h4>未入选样本（{len(non_selected_samples)}）</h4>"
            "<ol>"
            f"{''.join(_sample_lines(s) for s in non_selected_samples)}"
            "</ol>"
            "</body></html>"
        )

    def _build_eval_text(
        self,
        *,
        now: datetime,
        as_of_date: str,
        selected_samples: list[dict[str, Any]],
        non_selected_samples: list[dict[str, Any]],
    ) -> str:
        lines = [
            f"Macro 人工评审样本（{as_of_date}）",
            f"生成时间(UTC): {now.isoformat()}",
            f"入选样本: {len(selected_samples)}",
            f"未入选样本: {len(non_selected_samples)}",
            "",
        ]
        if self.eval_google_form_url:
            lines.extend(
                [
                    f"Google Form 入口: {self.eval_google_form_url}",
                    "每条样本下方附“预填表单”链接，已自动填好 date/sample_id/selected/topic/event_id。",
                    "建议最简字段：date, sample_id, selected, topic, should_report(Y/N),",
                    "importance(H/M/L), is_duplicate(Y/N), duplicate_of, missed_note, comment",
                    "",
                ]
            )

        lines.extend(
            [
            "每条必填：",
            "1) 该不该报(Y/N)",
            "2) 重不重要(H/M/L)",
            "3) 是否重复(Y/N；若Y填重复sample_id)",
            "4) 漏了什么(可空；title + url + 1行原因)",
            "",
            "【入选样本】",
            ]
        )

        lines.extend(self._build_eval_sample_text_lines(samples=selected_samples, as_of_date=as_of_date))
        lines.append("")
        lines.append("【未入选样本】")
        lines.extend(self._build_eval_sample_text_lines(samples=non_selected_samples, as_of_date=as_of_date))
        return "\n".join(lines)

    def _build_eval_sample_text_lines(self, *, samples: list[dict[str, Any]], as_of_date: str) -> list[str]:
        lines: list[str] = []
        for sample in samples:
            sid = str(sample.get("sample_id") or "-")
            title = str(sample.get("title") or "")
            topic = str(sample.get("topic") or "")
            event_id = str(sample.get("event_id") or "")
            selected = str(sample.get("selected")).lower() if "selected" in sample else ""
            score = sample.get("score")
            url = str(sample.get("url") or "")
            domain = str(sample.get("source_domain") or "")
            reject_reason = str(sample.get("reject_reason") or "")
            low_pool_fill = bool(sample.get("low_pool_fill"))
            prefilled_url = self._build_eval_prefilled_form_url(as_of_date=as_of_date, sample=sample)

            meta = f"topic={topic} | score={score} | domain={domain}"
            if reject_reason:
                meta += f" | reject_reason={reject_reason}"
            if low_pool_fill:
                meta += " | low_pool_fill=true"

            lines.extend(
                [
                    f"[{sid}] {title}",
                    f"  {meta}",
                    f"  event_id={event_id} | selected={selected}",
                    f"  URL: {url}",
                ]
            )
            if prefilled_url:
                lines.append(f"  预填表单: {prefilled_url}")
            lines.extend(
                [
                    "  该不该报(Y/N):",
                    "  重不重要(H/M/L):",
                    "  是否重复(Y/N; 若Y填重复sample_id):",
                    "  漏了什么(title + url + 1行原因):",
                    "",
                ]
            )
        return lines

    def _build_eval_prefilled_form_url(self, *, as_of_date: str, sample: dict[str, Any]) -> str:
        if not self.eval_google_form_url:
            return ""

        parsed = urlsplit(self.eval_google_form_url)
        static_pairs = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if not k.startswith("entry.")
        ]
        if not any(k == "usp" for k, _ in static_pairs):
            static_pairs.append(("usp", "pp_url"))

        entry_pairs: list[tuple[str, str]] = []

        def add_entry(entry_id: str, value: str) -> None:
            token = entry_id.strip()
            if not token:
                return
            key = token if token.startswith("entry.") else f"entry.{token}"
            entry_pairs.append((key, value))

        add_entry(self.eval_form_entry_date, as_of_date)
        add_entry(self.eval_form_entry_sample_id, str(sample.get("sample_id") or ""))
        add_entry(self.eval_form_entry_selected, self._selected_prefill_value(sample.get("selected")))
        add_entry(self.eval_form_entry_topic, str(sample.get("topic") or ""))
        add_entry(self.eval_form_entry_event_id, str(sample.get("event_id") or ""))

        if not entry_pairs:
            return self.eval_google_form_url

        query = urlencode(static_pairs + entry_pairs, doseq=True)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, query, parsed.fragment))

    def _selected_prefill_value(self, raw: Any) -> str:
        if raw is None:
            return ""
        if isinstance(raw, bool):
            return self.eval_form_selected_true_value if raw else self.eval_form_selected_false_value
        token = str(raw).strip().lower()
        if token in {"1", "y", "yes", "t", "true"}:
            return self.eval_form_selected_true_value
        if token in {"0", "n", "no", "f", "false"}:
            return self.eval_form_selected_false_value
        return str(raw)
