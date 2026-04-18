from __future__ import annotations

import json
from datetime import UTC, date, datetime

from contracts.confidence import ConfidenceDTO
from contracts.enums import (
    ConfidenceLevel,
    MacroBiasTag,
    MacroEventStatus,
    MacroEventViewType,
    MacroThemeType,
    MappingDirection,
    MaterialChangeLevel,
    SourceType,
)
from contracts.macro_contracts import MacroEventHistoryDTO, MacroEventViewDTO, MacroMasterCardDTO
from contracts.material_change import MaterialChangeDTO
from contracts.source_refs import SourceRefDTO
from macro.notifier import MacroDigestNotifier, ResendEmailClient


class FakeRepository:
    def __init__(self, histories: list[MacroEventHistoryDTO], views: list[MacroEventViewDTO], master: MacroMasterCardDTO):
        self.histories = histories
        self.views = views
        self.master = master

    def list_event_history_since(self, since_at: datetime) -> list[MacroEventHistoryDTO]:
        _ = since_at
        return self.histories

    def list_event_views(self, **kwargs) -> list[MacroEventViewDTO]:
        _ = kwargs
        return self.views

    def get_latest_master(self, as_of_date: date | None = None) -> MacroMasterCardDTO | None:
        _ = as_of_date
        return self.master


def _sample_master() -> MacroMasterCardDTO:
    now = datetime.now(UTC)
    return MacroMasterCardDTO(
        version="macro-master:20260326:01",
        as_of_date=date(2026, 3, 26),
        created_at=now,
        current_macro_bias=[MacroBiasTag.POLICY_EXPECTATION_DOMINANT],
        macro_mainline="政策预期博弈继续",
        key_changes=["变化A"],
        risk_opportunity_flags=["机会:变化A"],
        a_share_style_impact="成长风格边际修复",
        sw_l1_positive=["801750"],
        sw_l1_negative=["801780"],
        sw_l1_neutral=["801790"],
        reasoning="test",
        source_refs=[
            SourceRefDTO(
                source_type=SourceType.NEWS,
                title="t",
                retrieved_at=now,
            )
        ],
        confidence=ConfidenceDTO(score=0.7, level=ConfidenceLevel.MEDIUM),
        material_change=MaterialChangeDTO(material_change=False, level=MaterialChangeLevel.NONE, reasons=[]),
    )


def test_load_recipients_and_dry_run(tmp_path) -> None:
    recipients_doc = tmp_path / "recipients.md"
    recipients_doc.write_text(
        "# list\n- A@example.com\n- b@example.com  # comment\n- a@example.com\n",
        encoding="utf-8",
    )

    now = datetime.now(UTC)
    histories = [
        MacroEventHistoryDTO(
            history_id="h1",
            event_id="e1",
            event_seq=1,
            as_of_date=date(2026, 3, 26),
            event_status=MacroEventStatus.NEW,
            title="事件A",
            fact_summary="事实A",
            theme_type=MacroThemeType.POLICY_ENVIRONMENT,
            source_refs=[
                SourceRefDTO(source_type=SourceType.NEWS, title="s1", retrieved_at=now),
            ],
            created_at=now,
        )
    ]
    views = [
        MacroEventViewDTO(
            view_id="v1",
            event_id="e1",
            history_id="h1",
            as_of_date=date(2026, 3, 26),
            view_type=MacroEventViewType.SOURCE,
            stance=MappingDirection.POSITIVE,
            view_text="观点A",
            score=0.7,
            created_at=now,
        )
    ]
    repo = FakeRepository(histories=histories, views=views, master=_sample_master())
    client = ResendEmailClient(api_key="sk_test", base_url="https://api.resend.com/emails")
    notifier = MacroDigestNotifier(
        repository=repo,
        email_client=client,
        from_email="macro@example.com",
        recipients_doc_path=str(recipients_doc),
    )

    result = notifier.send_recent_digest(hours=24, dry_run=True)
    assert result["reason"] == "dry_run"
    assert result["history_count"] == 1
    assert result["view_count"] == 1
    assert result["recipients"] == ["a@example.com", "b@example.com"]


def test_no_recent_events_skip(tmp_path) -> None:
    recipients_doc = tmp_path / "recipients.md"
    recipients_doc.write_text("- x@example.com\n", encoding="utf-8")

    repo = FakeRepository(histories=[], views=[], master=_sample_master())
    client = ResendEmailClient(api_key="sk_test", base_url="https://api.resend.com/emails")
    notifier = MacroDigestNotifier(
        repository=repo,
        email_client=client,
        from_email="macro@example.com",
        recipients_doc_path=str(recipients_doc),
    )
    result = notifier.send_recent_digest(hours=24, dry_run=True)
    assert result["sent"] is False
    assert result["reason"] == "no_recent_events"


def test_eval_digest_dry_run_renders_review_template(tmp_path) -> None:
    recipients_doc = tmp_path / "recipients.md"
    recipients_doc.write_text("- reviewer@example.com\n", encoding="utf-8")
    eval_pack = tmp_path / "macro_eval_pack_latest.json"
    eval_pack.write_text(
        json.dumps(
            {
                "as_of_date": "2026-04-09",
                "selected_samples": [
                    {
                        "sample_id": "sel-01",
                        "event_id": "intel:monetary_policy:abc",
                        "topic": "monetary_policy",
                        "title": "央行操作维持流动性",
                        "url": "https://www.pbc.gov.cn/a1",
                        "score": 67.5,
                        "source_domain": "pbc.gov.cn",
                        "selected": True,
                    }
                ],
                "non_selected_samples": [
                    {
                        "sample_id": "rej-01",
                        "event_id": "intel:fx:def",
                        "topic": "fx",
                        "title": "汇率市场短评",
                        "url": "https://example.com/fx",
                        "score": 53.0,
                        "source_domain": "example.com",
                        "selected": False,
                        "reject_reason": "quota_topic",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    repo = FakeRepository(histories=[], views=[], master=_sample_master())
    client = ResendEmailClient(api_key="sk_test", base_url="https://api.resend.com/emails")
    notifier = MacroDigestNotifier(
        repository=repo,
        email_client=client,
        from_email="macro@example.com",
        recipients_doc_path=str(recipients_doc),
        eval_google_form_url="https://docs.google.com/forms/d/e/demo/viewform",
        eval_form_entry_date="entry.92686352",
        eval_form_entry_sample_id="entry.1723622274",
        eval_form_entry_selected="entry.273883245",
        eval_form_entry_topic="entry.301707955",
        eval_form_entry_event_id="entry.1009229059",
    )

    result = notifier.send_eval_digest(eval_pack_path=str(eval_pack), dry_run=True)
    assert result["reason"] == "dry_run"
    assert result["selected_count"] == 1
    assert result["non_selected_count"] == 1
    assert "Google Form 入口:" in result["text_preview"]
    assert "entry.92686352=2026-04-09" in result["text_preview"]
    assert "entry.1723622274=sel-01" in result["text_preview"]
    assert "entry.273883245=True" in result["text_preview"]
    assert "该不该报(Y/N)" in result["text_preview"]
    assert "是否重复(Y/N" in result["text_preview"]
