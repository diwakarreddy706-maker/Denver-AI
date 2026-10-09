"""Unit tests for Denver Email Automation, Continuous Monitoring, and AI Summarization."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock

from denver.automation.email.analyzer import EmailAnalyzer, _heuristic_classify_and_summarize
from denver.automation.email.client import EmailClient, _decode_header_str, _strip_html
from denver.automation.email.models import (
    EmailCategory,
    EmailDraft,
    EmailMessage,
    EmailMonitorConfig,
    EmailPriority,
    EmailSendResult,
    EmailSummary,
)
from denver.automation.email.monitor import EmailMonitor
from denver.commands.models import CommandCategory, CommandRequest
from denver.commands.router import IntentRouter
from denver.providers.models import ProviderResponse
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import EmailMonitoringStateChanged, EmailReceived, EmailSummarized


# -----------------------------------------------------------------------------
# 1. Models & Utilities Tests
# -----------------------------------------------------------------------------

def test_email_models_and_snippet():
    msg = EmailMessage(
        uid="101",
        sender="boss@corp.com",
        sender_name="Team Lead",
        subject="Urgent: System Deployment Update",
        date="2026-09-26 10:00:00",
        body_text="Hi team, please review the deployment plan immediately before 2 PM.",
        has_attachments=True,
        attachment_names=("plan.pdf",),
    )
    d = msg.to_dict()
    assert d["uid"] == "101"
    assert d["sender"] == "boss@corp.com"
    assert d["has_attachments"] is True
    assert "plan.pdf" in d["attachment_names"]
    assert "immediately" in msg.snippet()


def test_email_summary_format_display():
    summary = EmailSummary(
        uid="101",
        subject="Project Update",
        sender="alice@corp.com",
        sender_name="Alice",
        priority=EmailPriority.HIGH,
        category=EmailCategory.WORK,
        summary="Sprint milestones are due today.",
        action_items=("Submit pull request before 5 PM",),
        suggested_reply="On it, reviewing now.",
    )
    text = summary.format_display()
    assert "Project Update" in text
    assert "[HIGH]" in text
    assert "[WORK]" in text
    assert "Submit pull request" in text
    assert "On it, reviewing now." in text


def test_decode_header_and_strip_html():
    raw_html = "<html><body><p>Hello <b>World</b></p><br/>Please check this link.</body></html>"
    clean = _strip_html(raw_html)
    assert "Hello World" in clean
    assert "Please check this link." in clean
    assert "<html>" not in clean

    assert _decode_header_str("Simple ASCII") == "Simple ASCII"
    assert _decode_header_str("") == ""


# -----------------------------------------------------------------------------
# 2. Email Client Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_email_client_mock_offline_fallback():
    config = EmailMonitorConfig(is_mock=True)
    client = EmailClient(config)

    unread = await client.fetch_unread(limit=2)
    assert len(unread) == 2
    assert unread[0].subject != ""
    assert unread[0].sender != ""

    recent = await client.fetch_recent(limit=1)
    assert len(recent) == 1
    await client.disconnect()


# -----------------------------------------------------------------------------
# 3. Email Analyzer Tests (Heuristic & AI)
# -----------------------------------------------------------------------------

def test_heuristic_analyzer_high_priority_alert():
    msg = EmailMessage(
        uid="201",
        sender="security@service.com",
        subject="Security Alert: Unauthorized login detected",
        body_text="Action required: We detected suspicious sign-in from an unknown location. Please review your account immediately.",
    )
    summary = _heuristic_classify_and_summarize(msg)
    assert summary.priority == EmailPriority.HIGH
    assert summary.category == EmailCategory.ALERT
    assert len(summary.action_items) > 0
    assert summary.suggested_reply is not None


def test_heuristic_analyzer_newsletter():
    msg = EmailMessage(
        uid="202",
        sender="news@techdigest.io",
        subject="Weekly digest: Top Developer Tools",
        body_text="Check out the latest tools this week. Click here to unsubscribe.",
    )
    summary = _heuristic_classify_and_summarize(msg)
    assert summary.priority == EmailPriority.LOW
    assert summary.category == EmailCategory.NEWSLETTER


@pytest.mark.asyncio
async def test_email_analyzer_with_ai_provider():
    mock_router = MagicMock()
    mock_response = ProviderResponse(
        text='''```json
{
  "priority": "HIGH",
  "category": "WORK",
  "summary": "Urgent code review requested for release build.",
  "action_items": ["Review PR #42 by noon"],
  "suggested_reply": "I will inspect and approve the PR shortly."
}
```'''
    )
    mock_router.generate = AsyncMock(return_value=mock_response)

    analyzer = EmailAnalyzer(mock_router)
    msg = EmailMessage(uid="301", subject="PR Review", body_text="Can you review PR 42?")
    summary = await analyzer.analyze_message(msg)

    assert summary.priority == EmailPriority.HIGH
    assert summary.category == EmailCategory.WORK
    assert summary.summary == "Urgent code review requested for release build."
    assert "Review PR #42 by noon" in summary.action_items
    assert "approve the PR shortly" in summary.suggested_reply


# -----------------------------------------------------------------------------
# 4. Continuous Monitor & EventBus Tests
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_email_monitor_lifecycle_and_events():
    event_bus = DenverEventBus()
    received_events = []
    summarized_events = []
    state_events = []

    async def on_received(event):
        received_events.append(event)

    async def on_summarized(event):
        summarized_events.append(event)

    async def on_state(event):
        state_events.append(event)

    event_bus.subscribe(EmailReceived, on_received)
    event_bus.subscribe(EmailSummarized, on_summarized)
    event_bus.subscribe(EmailMonitoringStateChanged, on_state)

    config = EmailMonitorConfig(is_mock=True, poll_interval_seconds=100.0)
    monitor = EmailMonitor(config=config, event_bus=event_bus)

    # 1. Start monitor
    started = await monitor.start()
    assert started is True
    assert monitor.is_running is True
    assert len(state_events) == 1
    assert state_events[0].is_active is True

    # 2. Check emails and verify deduplication
    summaries1 = await monitor.check_now(limit=2)
    # The initial start() may have already checked them or summaries1 will get new ones
    status = monitor.get_status()
    assert status["is_running"] is True
    assert status["seen_emails_count"] >= 2

    # Polling again immediately should return empty due to deduplication
    summaries2 = await monitor.check_now(limit=2)
    assert len(summaries2) == 0

    # 3. Stop monitor
    stopped = await monitor.stop()
    assert stopped is True
    assert monitor.is_running is False
    assert len(state_events) == 2
    assert state_events[1].is_active is False


# -----------------------------------------------------------------------------
# 5. Command Router Intent Matching Tests
# -----------------------------------------------------------------------------

def test_command_router_email_intents():
    router = IntentRouter()

    # check_emails
    i1 = router.route("check my email")
    assert i1.action_name == "check_emails"
    assert i1.category == CommandCategory.UTILITY

    i2 = router.route("check inbox")
    assert i2.action_name == "check_emails"

    i3 = router.route("do i have any new emails")
    assert i3.action_name == "check_emails"

    # read_latest_email
    i4 = router.route("read my latest email")
    assert i4.action_name == "read_latest_email"

    i5 = router.route("what is inside my mail")
    assert i5.action_name == "read_latest_email"

    i6 = router.route("what's in my email")
    assert i6.action_name == "read_latest_email"

    # summarize_emails
    i7 = router.route("summarize my emails")
    assert i7.action_name == "summarize_emails"

    i8 = router.route("email summary")
    assert i8.action_name == "summarize_emails"

    # start_email_monitor / stop_email_monitor
    i9 = router.route("start email monitoring")
    assert i9.action_name == "start_email_monitor"

    i10 = router.route("stop email monitoring")
    assert i10.action_name == "stop_email_monitor"

    i11 = router.route("email status")
    assert i11.action_name == "get_email_monitor_status"


from denver.commands.service import CommandEngineService
from denver.automation.executor import AutomationExecutor
from denver.automation.models import AutomationRequest


@pytest.mark.asyncio
async def test_automation_and_command_service_email_actions():
    executor = AutomationExecutor()

    # 1. Check emails via AutomationExecutor
    res_check = await executor.execute(AutomationRequest(action_name="check_emails", params={"limit": 2}))
    assert res_check.success is True
    assert res_check.action == "check_emails"
    assert "count" in res_check.data

    # 2. Read latest email via AutomationExecutor
    res_latest = await executor.execute(AutomationRequest(action_name="read_latest_email"))
    assert res_latest.success is True
    assert res_latest.action == "read_latest_email"

    # 3. Start and stop email monitor via AutomationExecutor
    res_start = await executor.execute(AutomationRequest(action_name="start_email_monitor"))
    assert res_start.success is True

    res_stop = await executor.execute(AutomationRequest(action_name="stop_email_monitor"))
    assert res_stop.success is True

    # 4. CommandEngineService integration
    memory_mock = MagicMock()
    memory_mock.record_habit = AsyncMock()
    memory_mock.log_audit = AsyncMock()
    service = CommandEngineService(memory_service=memory_mock, automation_executor=executor)

    res_cmd1 = await service.process_command(CommandRequest(raw_text="check my email"))
    assert res_cmd1.success is True
    assert res_cmd1.action_name == "check_emails"

    res_cmd2 = await service.process_command(CommandRequest(raw_text="what is inside my mail"))
    assert res_cmd2.success is True
    assert res_cmd2.action_name == "read_latest_email"

    res_cmd3 = await service.process_command(CommandRequest(raw_text="summarize my emails"))
    assert res_cmd3.success is True
    assert res_cmd3.action_name == "summarize_emails"

    res_cmd4 = await service.process_command(CommandRequest(raw_text="email status"))
    assert res_cmd4.success is True
    assert res_cmd4.action_name == "get_email_monitor_status"


# -----------------------------------------------------------------------------
# 5. Two-Way Email: Drafts, Sending, and Replies Tests (Step 1)
# -----------------------------------------------------------------------------

def test_email_draft_and_send_result_models():
    draft = EmailDraft(
        to="colleague@domain.com",
        subject="Meeting Agenda",
        body="Here is our agenda for tomorrow.",
        cc="lead@domain.com",
    )
    d = draft.to_dict()
    assert d["to"] == "colleague@domain.com"
    assert d["subject"] == "Meeting Agenda"
    assert d["cc"] == "lead@domain.com"
    assert d["draft_id"].startswith("draft-")

    res = EmailSendResult(
        success=True,
        message="Email sent successfully.",
        recipient="colleague@domain.com",
        subject="Meeting Agenda",
        message_id="<msg-123@denver.local>",
    )
    r = res.to_dict()
    assert r["success"] is True
    assert r["recipient"] == "colleague@domain.com"
    assert r["message_id"] == "<msg-123@denver.local>"


@pytest.mark.asyncio
async def test_email_client_draft_and_send():
    config = EmailMonitorConfig(is_mock=True)
    client = EmailClient(config)

    # 1. Draft creation and retrieval
    draft = client.create_draft(to="dev@example.com", subject="Test Draft", body="Draft content")
    assert draft.to == "dev@example.com"
    assert client.get_draft(draft.draft_id) is not None
    assert len(client.list_drafts()) == 1

    # 2. Mock sending
    send_res = await client.send_email(
        to="dev@example.com",
        subject="Sprint Review",
        body="Sprint results are ready.",
        draft_id=draft.draft_id,
    )
    assert send_res.success is True
    assert "sent successfully" in send_res.message
    # Draft should be consumed/deleted after send
    assert client.get_draft(draft.draft_id) is None

    # 3. Mock reply
    reply_res = await client.reply_to_email(body="Thank you for the update!", recipient="alice@corp.com", original_subject="Roadmap")
    assert reply_res.success is True
    assert reply_res.recipient == "alice@corp.com"
    assert reply_res.subject.startswith("Re:")


def test_email_router_send_draft_reply():
    router = IntentRouter()

    # Draft
    i1 = router.route("draft email to alex@example.com saying let us meet at 3")
    assert i1.action_name == "draft_email"
    assert i1.params["to"] == "alex@example.com"
    assert "let us meet at 3" in i1.params["body"]

    i2 = router.route("draft an email to bob@corp.com about Project Kickoff saying please join at 10")
    assert i2.action_name == "draft_email"
    assert i2.params["to"] == "bob@corp.com"
    assert i2.params["subject"] == "Project Kickoff"

    # Send
    i3 = router.route("send email to team@company.com saying deployment is live")
    assert i3.action_name == "send_email"
    assert i3.params["to"] == "team@company.com"
    assert i3.risk_level.value == "MEDIUM"

    # Reply
    i4 = router.route("reply to email saying thank you for the feedback")
    assert i4.action_name == "reply_to_email"
    assert "thank you for the feedback" in i4.params["body"]
    assert i4.risk_level.value == "MEDIUM"


@pytest.mark.asyncio
async def test_email_service_draft_and_send_with_confirmation():
    executor = AutomationExecutor()
    memory_mock = MagicMock()
    memory_mock.record_habit = AsyncMock()
    memory_mock.log_audit = AsyncMock()
    from dataclasses import replace
    from denver.config.settings import DenverSettings
    test_settings = replace(DenverSettings(), allow_high_risk_actions=False, email_mock_mode=True)
    service = CommandEngineService(memory_service=memory_mock, automation_executor=executor, settings=test_settings)

    # 1. Draft email action executes safely without confirmation
    res_draft = await service.process_command(CommandRequest(raw_text="draft email to partner@venture.com saying proposal ready"))
    assert res_draft.success is True
    assert res_draft.action_name == "draft_email"
    assert "draft" in res_draft.message.lower()

    # 2. Send email stages confirmation token when not explicitly confirmed
    res_send = await service.process_command(CommandRequest(raw_text="send email to partner@venture.com saying proposal ready"))
    assert res_send.success is True
    assert res_send.action_name == "send_email"
    assert res_send.data.get("requires_confirmation") is True
    assert "token" in res_send.data

    # 3. Confirming the token completes the send
    token = res_send.data["token"]
    res_confirm = await service.process_command(CommandRequest(raw_text=f"confirm {token}"))
    assert res_confirm.success is True
    assert "sent successfully" in res_confirm.message.lower()


