"""AI-Powered and Heuristic Email Content Analyzer and Summarizer for Denver."""

from __future__ import annotations

import json
import re
from typing import Any

from denver.automation.email.models import EmailCategory, EmailMessage, EmailPriority, EmailSummary
from denver.logging.logger import get_logger
from denver.providers.models import ProviderRequest

logger = get_logger("automation.email.analyzer")


def _heuristic_classify_and_summarize(msg: EmailMessage) -> EmailSummary:
    """Fast, offline rule-based classification and summarization when AI provider is unavailable."""
    text_corpus = f"{msg.subject} {msg.body_text}".lower()

    # 1. Determine priority and category
    priority = EmailPriority.MEDIUM
    category = EmailCategory.GENERAL

    high_priority_signals = [
        "urgent", "action required", "immediate attention", "critical",
        "security alert", "unauthorized", "suspicious sign-in", "deadline",
        "overdue", "payment failed", "verification code", "one-time password", "otp"
    ]
    newsletter_signals = [
        "unsubscribe", "weekly digest", "newsletter", "edition", "promotions", "view in browser"
    ]
    financial_signals = [
        "invoice", "receipt", "billing", "payment", "statement", "subscription", "charge"
    ]
    alert_signals = [
        "alert", "warning", "notification", "security", "sign-in", "login", "password"
    ]

    if any(sig in text_corpus for sig in high_priority_signals):
        priority = EmailPriority.HIGH
    elif any(sig in text_corpus for sig in newsletter_signals):
        priority = EmailPriority.LOW
        category = EmailCategory.NEWSLETTER

    if category == EmailCategory.GENERAL:
        if any(sig in text_corpus for sig in alert_signals):
            category = EmailCategory.ALERT
        elif any(sig in text_corpus for sig in financial_signals):
            category = EmailCategory.FINANCIAL
        elif any(sig in text_corpus for sig in ["project", "roadmap", "sync", "meeting", "deliverable", "client", "sprint"]):
            category = EmailCategory.WORK

    # 2. Extract action items
    action_items = []
    lines = msg.body_text.splitlines()
    for line in lines:
        stripped = line.strip()
        if re.search(r"\b(please|kindly|need your|by \d{1,2}|action required|confirm|review)\b", stripped, re.IGNORECASE):
            clean_item = re.sub(r"^[-*•\s]+", "", stripped)
            if len(clean_item) > 10 and clean_item not in action_items:
                action_items.append(clean_item)
                if len(action_items) >= 3:
                    break

    # 3. Formulate summary
    if msg.body_text:
        # Grab first 1 or 2 clean sentences
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", msg.body_text) if s.strip()]
        summary_text = " ".join(sentences[:2])
        if len(summary_text) > 220:
            summary_text = summary_text[:217].rstrip() + "..."
    else:
        summary_text = f"Email received from {msg.sender_name or msg.sender} regarding '{msg.subject}'."

    # 4. Generate suggested reply if applicable
    suggested_reply = None
    if action_items or priority == EmailPriority.HIGH:
        name_part = f" {msg.sender_name}" if msg.sender_name else ""
        suggested_reply = f"Thanks{name_part}, I'm reviewing this now and will follow up shortly."

    return EmailSummary(
        uid=msg.uid,
        subject=msg.subject,
        sender=msg.sender,
        sender_name=msg.sender_name,
        priority=priority,
        category=category,
        summary=summary_text,
        action_items=tuple(action_items),
        suggested_reply=suggested_reply,
        confidence=0.85,
    )


class EmailAnalyzer:
    """Analyzes email contents using Denver AI Providers or robust heuristic fallbacks."""

    def __init__(self, provider_router: Any | None = None) -> None:
        self.provider_router = provider_router

    async def analyze_message(self, msg: EmailMessage) -> EmailSummary:
        """Analyze a single email message, returning structured summary and actionable insights."""
        if not self.provider_router:
            return _heuristic_classify_and_summarize(msg)

        system_instruction = (
            "You are Denver's Email Intelligence Agent. Analyze the following incoming email.\n"
            "Return ONLY a valid JSON object with the following exact keys:\n"
            "{\n"
            '  "priority": "HIGH" | "MEDIUM" | "LOW",\n'
            '  "category": "WORK" | "PERSONAL" | "ALERT" | "FINANCIAL" | "NEWSLETTER" | "SPAM" | "GENERAL",\n'
            '  "summary": "Concise 1-2 sentence overview of what this email is about",\n'
            '  "action_items": ["List of direct actions, deadlines or requests for the user, if any"],\n'
            '  "suggested_reply": "A brief, polite suggested reply if a response is warranted, or null"\n'
            "}"
        )

        user_content = (
            f"Sender: {msg.sender_name} <{msg.sender}>\n"
            f"Date: {msg.date}\n"
            f"Subject: {msg.subject}\n"
            f"Attachments: {', '.join(msg.attachment_names) if msg.has_attachments else 'None'}\n\n"
            f"Body:\n{msg.body_text[:2000]}"
        )

        req = ProviderRequest(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
            max_tokens=400,
        )

        try:
            resp = await self.provider_router.generate(req)
            if resp and resp.text:
                raw_text = resp.text.strip()
                # Strip markdown code blocks if wrapped
                if "```json" in raw_text:
                    raw_text = raw_text.split("```json")[1].split("```")[0].strip()
                elif "```" in raw_text:
                    raw_text = raw_text.split("```")[1].split("```")[0].strip()

                parsed = json.loads(raw_text)

                p_str = str(parsed.get("priority", "MEDIUM")).upper()
                priority = EmailPriority[p_str] if p_str in EmailPriority.__members__ else EmailPriority.MEDIUM

                c_str = str(parsed.get("category", "GENERAL")).upper()
                category = EmailCategory[c_str] if c_str in EmailCategory.__members__ else EmailCategory.GENERAL

                summary = str(parsed.get("summary", "")).strip() or msg.snippet()
                action_items = [str(item).strip() for item in parsed.get("action_items", []) if str(item).strip()]
                suggested_reply = parsed.get("suggested_reply")
                if suggested_reply is not None:
                    suggested_reply = str(suggested_reply).strip() or None

                return EmailSummary(
                    uid=msg.uid,
                    subject=msg.subject,
                    sender=msg.sender,
                    sender_name=msg.sender_name,
                    priority=priority,
                    category=category,
                    summary=summary,
                    action_items=tuple(action_items),
                    suggested_reply=suggested_reply,
                    confidence=0.95,
                )
        except Exception as exc:
            logger.warning("AI Email analysis failed: %s. Falling back to heuristic summarizer.", exc)

        return _heuristic_classify_and_summarize(msg)

    async def analyze_batch(self, messages: list[EmailMessage]) -> list[EmailSummary]:
        """Analyze a collection of email messages in sequence."""
        summaries: list[EmailSummary] = []
        for msg in messages:
            summary = await self.analyze_message(msg)
            summaries.append(summary)
        return summaries
