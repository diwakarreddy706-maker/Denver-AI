"""IMAP Email Client with robust MIME parsing, SSL security, and async executor support."""

from __future__ import annotations

import asyncio
import email
import email.header
import email.utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import html
import imaplib
import re
import smtplib
import time
from typing import Any

from denver.automation.email.models import (
    EmailDraft,
    EmailMessage,
    EmailMonitorConfig,
    EmailSendResult,
)
from denver.logging.logger import get_logger

logger = get_logger("automation.email.client")


def _decode_header_str(header_val: str | None) -> str:
    """Safely decode RFC 2047 encoded email headers to unicode."""
    if not header_val:
        return ""
    try:
        decoded_chunks = email.header.decode_header(header_val)
        result_parts = []
        for content, encoding in decoded_chunks:
            if isinstance(content, bytes):
                encoding = encoding or "utf-8"
                try:
                    result_parts.append(content.decode(encoding, errors="replace"))
                except (LookupError, UnicodeDecodeError):
                    result_parts.append(content.decode("latin-1", errors="replace"))
            else:
                result_parts.append(str(content))
        return "".join(result_parts).strip()
    except Exception as exc:
        logger.debug("Header decode fallback for '%s': %s", header_val, exc)
        return str(header_val).strip()


def _strip_html(html_content: str) -> str:
    """Convert HTML email body into clean, readable plain text."""
    if not html_content:
        return ""
    # Strip script and style blocks
    cleaned = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html_content, flags=re.DOTALL | re.IGNORECASE)
    # Convert line breaks and paragraph breaks
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</p>", "\n\n", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"</div>", "\n", cleaned, flags=re.IGNORECASE)
    # Strip remaining HTML tags
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    # Unescape HTML entities
    cleaned = html.unescape(cleaned)
    # Normalize multiple newlines and spaces
    lines = [line.strip() for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line)


class EmailClient:
    """Asynchronous IMAP client for fetching and parsing mailbox messages."""

    def __init__(self, config: EmailMonitorConfig) -> None:
        self.config = config
        self._imap: imaplib.IMAP4 | None = None
        self._lock = asyncio.Lock()
        self._drafts: dict[str, EmailDraft] = {}

    def _sync_connect(self) -> imaplib.IMAP4:
        """Establish synchronous IMAP connection."""
        if self._imap is not None:
            try:
                self._imap.noop()
                return self._imap
            except Exception:
                try:
                    self._imap.logout()
                except Exception:
                    pass
                self._imap = None

        logger.info("Connecting to IMAP server %s:%d (SSL=%s)", self.config.imap_server, self.config.imap_port, self.config.use_ssl)
        if self.config.use_ssl:
            imap_conn = imaplib.IMAP4_SSL(self.config.imap_server, self.config.imap_port)
        else:
            imap_conn = imaplib.IMAP4(self.config.imap_server, self.config.imap_port)

        imap_conn.login(self.config.username, self.config.password)
        self._imap = imap_conn
        return self._imap

    def _sync_disconnect(self) -> None:
        """Close and logout synchronous IMAP connection."""
        if self._imap is not None:
            try:
                self._imap.close()
            except Exception:
                pass
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    def _parse_raw_message(self, uid: str, raw_bytes: bytes) -> EmailMessage:
        """Parse raw RFC 822 email bytes into structured EmailMessage."""
        msg = email.message_from_bytes(raw_bytes)

        subject = _decode_header_str(msg.get("Subject", ""))
        from_raw = _decode_header_str(msg.get("From", ""))
        to_raw = _decode_header_str(msg.get("To", ""))
        date_raw = msg.get("Date", "")
        message_id = msg.get("Message-ID", "")

        real_name, email_address = email.utils.parseaddr(from_raw)
        sender_name = real_name or email_address

        body_text_parts = []
        body_html_parts = []
        attachment_names = []

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))

                if "attachment" in content_disposition:
                    filename = _decode_header_str(part.get_filename() or "")
                    if filename:
                        attachment_names.append(filename)
                    continue

                if content_type == "text/plain":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body_text_parts.append(payload.decode(charset, errors="replace"))
                        except Exception:
                            body_text_parts.append(payload.decode("latin-1", errors="replace"))
                elif content_type == "text/html":
                    payload = part.get_payload(decode=True)
                    if payload:
                        charset = part.get_content_charset() or "utf-8"
                        try:
                            body_html_parts.append(payload.decode(charset, errors="replace"))
                        except Exception:
                            body_html_parts.append(payload.decode("latin-1", errors="replace"))
        else:
            content_type = msg.get_content_type()
            payload = msg.get_payload(decode=True)
            if payload:
                if content_type.startswith("text/"):
                    charset = msg.get_content_charset() or "utf-8"
                    try:
                        decoded = payload.decode(charset, errors="replace")
                    except Exception:
                        decoded = payload.decode("latin-1", errors="replace")
                    if content_type == "text/html":
                        body_html_parts.append(decoded)
                    else:
                        body_text_parts.append(decoded)
                else:
                    filename = _decode_header_str(msg.get_filename() or "")
                    if not filename:
                        filename = f"attachment.{content_type.split('/')[-1]}"
                    attachment_names.append(filename)

        body_text = "\n".join(body_text_parts).strip()
        body_html = "\n".join(body_html_parts).strip()

        # If no plain text was found, convert HTML to clean plain text
        if not body_text and body_html:
            body_text = _strip_html(body_html)

        return EmailMessage(
            uid=str(uid),
            message_id=str(message_id),
            sender=email_address or from_raw,
            sender_name=sender_name,
            recipient=to_raw,
            subject=subject,
            date=date_raw,
            body_text=body_text,
            body_html=body_html,
            has_attachments=bool(attachment_names),
            attachment_names=tuple(attachment_names),
        )

    def _sync_fetch_emails(self, criteria: str = "UNSEEN", limit: int = 10) -> list[EmailMessage]:
        """Synchronously query and fetch email messages matching criteria."""
        imap_conn = self._sync_connect()
        status, _ = imap_conn.select(self.config.mailbox)
        if status != "OK":
            raise RuntimeError(f"Failed to select mailbox '{self.config.mailbox}'")

        status, data = imap_conn.uid("search", None, criteria)
        if status != "OK" or not data or not data[0]:
            return []

        uids = data[0].split()
        # Fetch the most recent messages up to limit
        selected_uids = uids[-limit:] if limit > 0 else uids
        selected_uids.reverse()  # Newest first

        messages: list[EmailMessage] = []
        for uid_bytes in selected_uids:
            uid_str = uid_bytes.decode() if isinstance(uid_bytes, bytes) else str(uid_bytes)
            status, msg_data = imap_conn.uid("fetch", uid_str, "(BODY.PEEK[])")
            if status == "OK" and msg_data:
                for response_part in msg_data:
                    if isinstance(response_part, tuple):
                        raw_email = response_part[1]
                        parsed_msg = self._parse_raw_message(uid_str, raw_email)
                        messages.append(parsed_msg)
                        break

        return messages

    def _get_mock_emails(self, count: int = 3) -> list[EmailMessage]:
        """Generate realistic mock emails for offline mode, testing, and demonstrations."""
        samples = [
            EmailMessage(
                uid="mock-101",
                sender="alice.smith@techcorp.com",
                sender_name="Alice Smith",
                subject="Q3 Project Roadmap Review & Deliverables",
                date="Today, 09:30 AM",
                body_text="Hi team,\nPlease review the attached Q3 roadmap. We need your feedback on the sprint milestones by 4:00 PM today before the executive sync.\nBest,\nAlice",
                has_attachments=True,
                attachment_names=("Q3_Roadmap_Draft.pdf",),
            ),
            EmailMessage(
                uid="mock-102",
                sender="security-alert@service-auth.com",
                sender_name="Cloud Security System",
                subject="Security Alert: New Sign-in from Windows Desktop",
                date="Today, 08:45 AM",
                body_text="We noticed a login from an unrecognized device at IP 192.168.1.100. If this was you, you can safely ignore this message. Otherwise, review your security settings immediately.",
                has_attachments=False,
            ),
            EmailMessage(
                uid="mock-103",
                sender="newsletter@dailytechdigest.io",
                sender_name="Tech Weekly Digest",
                subject="Top AI & Engineering Breakthroughs This Week",
                date="Yesterday, 18:20 PM",
                body_text="Welcome to this week's edition covering local LLMs, agentic workflows, and the latest open-weights model releases.",
                has_attachments=False,
            ),
        ]
        return samples[:count]

    async def fetch_unread(self, limit: int = 10) -> list[EmailMessage]:
        """Fetch unread (UNSEEN) emails from the mailbox."""
        if self.config.is_mock or not self.config.is_configured():
            logger.info("Using mock/offline email client (credentials not configured or mock mode enabled).")
            return self._get_mock_emails(limit)

        async with self._lock:
            try:
                return await asyncio.to_thread(self._sync_fetch_emails, criteria="UNSEEN", limit=limit)
            except Exception as exc:
                logger.warning("Failed to fetch unread emails via IMAP: %s. Falling back to offline mock mode.", exc)
                return self._get_mock_emails(limit)

    async def fetch_recent(self, limit: int = 10) -> list[EmailMessage]:
        """Fetch recent (ALL) emails from the mailbox."""
        if self.config.is_mock or not self.config.is_configured():
            logger.info("Using mock/offline email client for recent emails.")
            return self._get_mock_emails(limit)

        async with self._lock:
            try:
                return await asyncio.to_thread(self._sync_fetch_emails, criteria="ALL", limit=limit)
            except Exception as exc:
                logger.warning("Failed to fetch recent emails via IMAP: %s. Falling back to mock data.", exc)
                return self._get_mock_emails(limit)

    async def disconnect(self) -> None:
        """Disconnect and cleanup IMAP session."""
        async with self._lock:
            await asyncio.to_thread(self._sync_disconnect)

    # -------------------------------------------------------------------------
    # Draft Management
    # -------------------------------------------------------------------------

    def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        bcc: str = "",
        in_reply_to: str = "",
        references: str = "",
    ) -> EmailDraft:
        """Create and stage a local email draft."""
        draft = EmailDraft(
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            in_reply_to=in_reply_to,
            references=references,
        )
        self._drafts[draft.draft_id] = draft
        logger.info("Created email draft '%s' to %s: '%s'", draft.draft_id, to, subject)
        return draft

    def get_draft(self, draft_id: str) -> EmailDraft | None:
        """Retrieve a stored draft by ID."""
        return self._drafts.get(draft_id)

    def list_drafts(self) -> list[EmailDraft]:
        """List all pending drafts."""
        return list(self._drafts.values())

    def delete_draft(self, draft_id: str) -> bool:
        """Remove a stored draft."""
        if draft_id in self._drafts:
            del self._drafts[draft_id]
            return True
        return False

    # -------------------------------------------------------------------------
    # SMTP Email Dispatch
    # -------------------------------------------------------------------------

    def _sync_send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        bcc: str = "",
        in_reply_to: str = "",
        references: str = "",
    ) -> EmailSendResult:
        """Synchronously dispatch email message via SMTP."""
        sender = self.config.username or "denver@localhost"
        msg = MIMEMultipart("alternative")
        msg["From"] = sender
        msg["To"] = to
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg_id = email.utils.make_msgid(domain=self.config.smtp_server or "denver.local")
        msg["Message-ID"] = msg_id

        if cc:
            msg["Cc"] = cc
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
        if references:
            msg["References"] = references

        part = MIMEText(body, "plain", "utf-8")
        msg.attach(part)

        recipients = [addr.strip() for addr in to.split(",") if addr.strip()]
        if cc:
            recipients.extend(addr.strip() for addr in cc.split(",") if addr.strip())
        if bcc:
            recipients.extend(addr.strip() for addr in bcc.split(",") if addr.strip())

        try:
            logger.info("Connecting to SMTP server %s:%d (TLS=%s)", self.config.smtp_server, self.config.smtp_port, self.config.smtp_use_tls)
            if self.config.smtp_port == 465:
                server: smtplib.SMTP = smtplib.SMTP_SSL(self.config.smtp_server, self.config.smtp_port, timeout=20)
            else:
                server = smtplib.SMTP(self.config.smtp_server, self.config.smtp_port, timeout=20)

            server.ehlo()
            if self.config.smtp_use_tls and self.config.smtp_port != 465:
                server.starttls()
                server.ehlo()

            if self.config.username and self.config.password:
                server.login(self.config.username, self.config.password)

            server.sendmail(sender, recipients, msg.as_string())
            server.quit()
            logger.info("Successfully sent email to %s with subject '%s'", to, subject)
            return EmailSendResult(
                success=True,
                message=f"Email sent successfully to {to}.",
                recipient=to,
                subject=subject,
                message_id=msg_id,
            )
        except Exception as exc:
            logger.error("Failed to send email via SMTP: %s", exc)
            return EmailSendResult(
                success=False,
                message=f"Failed to send email: {exc}",
                recipient=to,
                subject=subject,
                error=str(exc),
            )

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
        bcc: str = "",
        in_reply_to: str = "",
        references: str = "",
        draft_id: str | None = None,
    ) -> EmailSendResult:
        """Send an email asynchronously with mock/offline fallback support."""
        if self.config.is_mock or not self.config.is_configured():
            logger.info("Using mock/offline email dispatcher (credentials not configured or mock mode enabled).")
            if draft_id:
                self.delete_draft(draft_id)
            return EmailSendResult(
                success=True,
                message=f"[Offline/Mock] Email sent successfully to {to}.",
                recipient=to,
                subject=subject,
                message_id=f"<mock-{int(time.time() * 1000)}@denver.mock>",
            )

        async with self._lock:
            res = await asyncio.to_thread(
                self._sync_send_email,
                to=to,
                subject=subject,
                body=body,
                cc=cc,
                bcc=bcc,
                in_reply_to=in_reply_to,
                references=references,
            )
            if res.success and draft_id:
                self.delete_draft(draft_id)
            return res

    async def reply_to_email(
        self,
        body: str,
        uid: str | None = None,
        recipient: str | None = None,
        original_subject: str | None = None,
    ) -> EmailSendResult:
        """Reply to the most recent email or a specific email by UID."""
        target_msg: EmailMessage | None = None
        if uid:
            recents = await self.fetch_recent(limit=10)
            for m in recents:
                if m.uid == uid:
                    target_msg = m
                    break
        elif not recipient:
            recents = await self.fetch_recent(limit=1)
            if recents:
                target_msg = recents[0]

        if target_msg:
            to = target_msg.sender
            subj = target_msg.subject
            if not subj.lower().startswith("re:"):
                subj = f"Re: {subj}"
            in_reply_to = target_msg.message_id or target_msg.uid
            references = target_msg.message_id or target_msg.uid
        else:
            to = recipient or "unknown@domain.com"
            subj = original_subject or "Re: Message"
            if not subj.lower().startswith("re:"):
                subj = f"Re: {subj}"
            in_reply_to = ""
            references = ""

        return await self.send_email(
            to=to,
            subject=subj,
            body=body,
            in_reply_to=in_reply_to,
            references=references,
        )

