"""Comprehensive unit tests for Denver's WhatsApp Voice Dispatcher subsystem."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from denver.automation.whatsapp import WhatsAppDispatcher
from denver.commands.router import IntentRouter
from denver.commands.service import CommandEngineService
from denver.memory.contacts import Contact, ContactBook
from denver.memory.memory_service import MemoryService
from denver.runtime.event_bus import DenverEventBus
from denver.runtime.events import WhatsAppMessageDispatched


class TestWhatsAppRouterPatterns(unittest.TestCase):
    """Test suite for IntentRouter WhatsApp regex and phrase parsing."""

    def setUp(self) -> None:
        self.router = IntentRouter()

    def test_send_whatsapp_to_saying(self) -> None:
        cmd = "send WhatsApp to Alex saying I will join the meeting in 5 minutes"
        intent = self.router.route(cmd)
        self.assertEqual(intent.intent_name, "send_whatsapp_message")
        self.assertEqual(intent.params.get("contact"), "Alex")
        self.assertEqual(intent.params.get("message"), "I will join the meeting in 5 minutes")

    def test_send_a_whatsapp_to_that(self) -> None:
        cmd = "send a WhatsApp to Mom that I arrived safely"
        intent = self.router.route(cmd)
        self.assertEqual(intent.intent_name, "send_whatsapp_message")
        self.assertEqual(intent.params.get("contact"), "Mom")
        self.assertEqual(intent.params.get("message"), "I arrived safely")

    def test_whatsapp_recipient_saying(self) -> None:
        cmd = "WhatsApp Dad saying please call me back"
        intent = self.router.route(cmd)
        self.assertEqual(intent.intent_name, "send_whatsapp_message")
        self.assertEqual(intent.params.get("contact"), "Dad")
        self.assertEqual(intent.params.get("message"), "please call me back")

    def test_message_recipient_on_whatsapp_saying(self) -> None:
        cmd = "message Prajwal on WhatsApp saying see you tomorrow"
        intent = self.router.route(cmd)
        self.assertEqual(intent.intent_name, "send_whatsapp_message")
        self.assertEqual(intent.params.get("contact"), "Prajwal")
        self.assertEqual(intent.params.get("message"), "see you tomorrow")

    def test_tell_recipient_on_whatsapp_that(self) -> None:
        cmd = "tell Alex on WhatsApp that I will be late"
        intent = self.router.route(cmd)
        self.assertEqual(intent.intent_name, "send_whatsapp_message")
        self.assertEqual(intent.params.get("contact"), "Alex")
        self.assertEqual(intent.params.get("message"), "I will be late")

    def test_tell_recipient_on_whatsapp_to(self) -> None:
        cmd = "tell Mom on WhatsApp to call me back"
        intent = self.router.route(cmd)
        self.assertEqual(intent.intent_name, "send_whatsapp_message")
        self.assertEqual(intent.params.get("contact"), "Mom")
        self.assertEqual(intent.params.get("message"), "call me back")

    def test_send_whatsapp_message_to_phone(self) -> None:
        cmd = "send WhatsApp message to +919876543210 saying Hello"
        intent = self.router.route(cmd)
        self.assertEqual(intent.intent_name, "send_whatsapp_message")
        self.assertEqual(intent.params.get("contact"), "+919876543210")
        self.assertEqual(intent.params.get("message"), "Hello")

    def test_colon_syntax(self) -> None:
        cmd = "message Mom on WhatsApp: please call me"
        intent = self.router.route(cmd)
        self.assertEqual(intent.intent_name, "send_whatsapp_message")
        self.assertEqual(intent.params.get("contact"), "Mom")
        self.assertEqual(intent.params.get("message"), "please call me")

    def test_open_whatsapp_and_send(self) -> None:
        cmd = "open whatsapp and send a message to Prajwal saying test message"
        intent = self.router.route(cmd)
        self.assertEqual(intent.intent_name, "send_whatsapp_message")
        self.assertEqual(intent.params.get("contact"), "Prajwal")
        self.assertEqual(intent.params.get("message"), "test message")

    def test_quoted_message_cleaned(self) -> None:
        cmd = 'send WhatsApp to Alex saying "I will be there soon"'
        intent = self.router.route(cmd)
        self.assertEqual(intent.params.get("message"), "I will be there soon")


class TestContactBookFuzzyAndResolution(unittest.TestCase):
    """Test suite for ContactBook search, fuzzy resolution, and direct phone handling."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_path = Path(self.temp_dir.name) / "contacts.json"
        self.cb = ContactBook(file_path=self.file_path)
        self.cb.add_or_update(
            Contact(
                name="Prajwal Sindhanur",
                phone="+919876543210",
                aliases=["prajwal", "prajju"],
                relationship="friend",
            )
        )
        self.cb.add_or_update(
            Contact(
                name="Diwakar Reddy",
                phone="+919123456789",
                aliases=["diwakar", "me"],
                relationship="self",
            )
        )
        self.cb.add_or_update(
            Contact(
                name="Appa",
                phone="+919988776655",
                aliases=["dad", "father"],
                relationship="father",
            )
        )

        self.cb.add_or_update(
            Contact(
                name="Amma",
                phone="+917975004633",
                aliases=["amma", "mom", "mother"],
                relationship="mother",
            )
        )
        self.cb.add_or_update(
            Contact(
                name="Boss John",
                phone="+918888888888",
                aliases=["boss", "manager"],
                relationship="boss",
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_exact_name_match(self) -> None:
        c = self.cb.find_contact("Prajwal Sindhanur")
        self.assertIsNotNone(c)
        self.assertEqual(c.clean_phone(), "919876543210")

    def test_alias_match(self) -> None:
        c = self.cb.find_contact("prajju")
        self.assertIsNotNone(c)
        self.assertEqual(c.name, "Prajwal Sindhanur")

    def test_relationship_synonym_match(self) -> None:
        c_dad = self.cb.find_contact("dad")
        self.assertIsNotNone(c_dad)
        self.assertEqual(c_dad.name, "Appa")

        c_father = self.cb.find_contact("father")
        self.assertIsNotNone(c_father)
        self.assertEqual(c_father.name, "Appa")

        c_mom = self.cb.find_contact("mom")
        self.assertIsNotNone(c_mom)
        self.assertEqual(c_mom.name, "Amma")

        c_mother = self.cb.find_contact("mother")
        self.assertIsNotNone(c_mother)
        self.assertEqual(c_mother.name, "Amma")

        c_boss = self.cb.find_contact("boss")
        self.assertIsNotNone(c_boss)
        self.assertEqual(c_boss.name, "Boss John")

    def test_token_prefix_match(self) -> None:
        c = self.cb.find_contact("Prajwal")
        self.assertIsNotNone(c)
        self.assertEqual(c.name, "Prajwal Sindhanur")

    def test_fuzzy_matching_slight_typo(self) -> None:
        # Phonetic or speech-to-text typo: "Prajwel" -> "Prajwal"
        c = self.cb.find_contact("Prajwel")
        self.assertIsNotNone(c)
        self.assertEqual(c.name, "Prajwal Sindhanur")

        # "Diwaker" -> "Diwakar Reddy"
        c2 = self.cb.find_contact("Diwaker")
        self.assertIsNotNone(c2)
        self.assertEqual(c2.name, "Diwakar Reddy")

    def test_direct_raw_phone_detection(self) -> None:
        c = self.cb.find_contact("+919998887776")
        self.assertIsNotNone(c)
        self.assertEqual(c.clean_phone(), "919998887776")
        self.assertEqual(c.relationship, "direct_phone")

    def test_stored_contact_by_phone_number(self) -> None:
        # Looking up stored phone +919876543210 resolves to Prajwal Sindhanur
        c = self.cb.find_contact("+919876543210")
        self.assertIsNotNone(c)
        self.assertEqual(c.name, "Prajwal Sindhanur")


    def test_ambiguous_contact_resolution(self) -> None:
        self.cb.add_or_update(
            Contact(
                name="Alex Kumar",
                phone="+919876543211",
                aliases=["alex"],
                relationship="colleague",
            )
        )
        self.cb.add_or_update(
            Contact(
                name="Alex Sharma",
                phone="+919876543212",
                aliases=["alex"],
                relationship="client",
            )
        )
        res = self.cb.find_contact_matches("Alex")
        self.assertTrue(res.is_ambiguous)
        self.assertIsNone(res.best_match)
        self.assertEqual(len(res.candidates), 2)
        names = [c.name for c, _ in res.candidates]
        self.assertIn("Alex Kumar", names)
        self.assertIn("Alex Sharma", names)

        # ContactBook.find_contact should return None for ambiguous query
        self.assertIsNone(self.cb.find_contact("Alex"))


class TestWhatsAppDispatcher(unittest.TestCase):
    """Test suite for WhatsAppDispatcher URI formatting, encoding, and execution."""

    def setUp(self) -> None:
        self.dispatcher = WhatsAppDispatcher()

    def test_clean_phone_number(self) -> None:
        self.assertEqual(self.dispatcher.clean_phone_number("+91 98765-43210"), "919876543210")
        self.assertEqual(self.dispatcher.clean_phone_number("9876543210"), "9876543210")
        self.assertEqual(self.dispatcher.clean_phone_number(""), "")

    def test_encode_message_with_emojis(self) -> None:
        msg = "Hello 🚀 and & welcome!"
        encoded = self.dispatcher.encode_message(msg)
        self.assertIn("%F0%9F%9A%80", encoded)
        self.assertIn("%26", encoded)

    def test_build_desktop_uri(self) -> None:
        uri_with_phone = self.dispatcher.build_desktop_uri("test msg", "+919876543210")
        self.assertTrue(uri_with_phone.startswith("whatsapp://send?phone=919876543210&text=test%20msg"))

        uri_no_phone = self.dispatcher.build_desktop_uri("test msg")
        self.assertTrue(uri_no_phone.startswith("whatsapp://send?text=test%20msg"))

    def test_build_web_url(self) -> None:
        web_url = self.dispatcher.build_web_url("test msg", "+919876543210")
        self.assertTrue(web_url.startswith("https://web.whatsapp.com/send?phone=919876543210&text=test%20msg"))

    def test_dispatch_mock_mode(self) -> None:
        res = self.dispatcher.dispatch_message(
            message="Meeting starts in 5 minutes",
            phone="919876543210",
            contact_name="Alex",
            is_mock=True,
        )
        self.assertTrue(res.success)
        self.assertEqual(res.action, "send_whatsapp_message")
        self.assertIn("Alex", res.message)
        self.assertTrue(res.data.get("mock"))


class TestWhatsAppLoggingPIIRedaction(unittest.TestCase):
    """Test suite ensuring full phone numbers and message content never appear in logs."""

    def test_mask_phone_utility(self) -> None:
        from denver.utils.logging_helpers import mask_phone

        self.assertEqual(mask_phone("+919876543210"), "+91******3210")
        self.assertEqual(mask_phone("9876543210"), "******3210")
        self.assertEqual(mask_phone(""), "")
        self.assertEqual(mask_phone("123"), "****")
        self.assertEqual(mask_phone("+1234567"), "+12****4567")

    def test_dispatcher_logs_redact_phone_and_message_body(self) -> None:
        import logging

        raw_phone = "+919876543210"
        secret_message = "Confidential OTP Code 987654"

        dispatcher = WhatsAppDispatcher()
        log_records: list[logging.LogRecord] = []

        class ListHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(record)

        handler = ListHandler()
        logger = logging.getLogger("denver.automation.whatsapp")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)

        try:
            dispatcher.dispatch_message(
                message=secret_message,
                phone=raw_phone,
                contact_name="TestContact",
                is_mock=True,
            )

            all_log_text = " ".join(r.getMessage() for r in log_records)

            # Assert raw full phone never appears
            self.assertNotIn("+919876543210", all_log_text)
            self.assertNotIn("919876543210", all_log_text)

            # Assert raw message body never appears
            self.assertNotIn(secret_message, all_log_text)

            # Assert masked phone and message length are logged
            self.assertIn("message_length=", all_log_text)
            self.assertIn("3210", all_log_text)
        finally:
            logger.removeHandler(handler)


class TestCommandServiceWhatsAppIntegration(unittest.TestCase):
    """Test suite for CommandEngineService WhatsApp action execution and event bus integration."""

    def setUp(self) -> None:
        os.environ["DENVER_MOCK_AUTOMATION"] = "true"
        self.event_bus = DenverEventBus()
        self.memory_service = MagicMock(spec=MemoryService)

        self.service = CommandEngineService(
            memory_service=self.memory_service,
            event_bus=self.event_bus,
        )

    def tearDown(self) -> None:
        os.environ.pop("DENVER_MOCK_AUTOMATION", None)

    def test_handle_send_whatsapp_message(self) -> None:
        events_received: list[WhatsAppMessageDispatched] = []

        async def handler(event: WhatsAppMessageDispatched) -> None:
            events_received.append(event)

        self.event_bus.subscribe(WhatsAppMessageDispatched, handler)

        async def run_test() -> None:
            result = await self.service.process_command(
                "Denver, send WhatsApp message to +919876543210 saying I am on my way"
            )
            self.assertTrue(result.success)
            self.assertEqual(result.action_name, "send_whatsapp_message")
            await asyncio.sleep(0.05)

        asyncio.run(run_test())

        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0].phone, "919876543210")
        self.assertEqual(events_received[0].message.lower(), "i am on my way")
        self.assertTrue(events_received[0].success)

    def test_ambiguous_contacts_clarification_no_dispatch_no_event(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        file_path = Path(temp_dir.name) / "contacts.json"
        cb = ContactBook(file_path=file_path)
        cb.add_or_update(
            Contact(
                name="Alex Kumar",
                phone="+919876543211",
                aliases=["alex"],
                relationship="colleague",
            )
        )
        cb.add_or_update(
            Contact(
                name="Alex Sharma",
                phone="+919876543212",
                aliases=["alex"],
                relationship="client",
            )
        )

        events_received: list[WhatsAppMessageDispatched] = []

        async def handler(event: WhatsAppMessageDispatched) -> None:
            events_received.append(event)

        self.event_bus.subscribe(WhatsAppMessageDispatched, handler)

        with patch("denver.memory.contacts.get_contact_book", return_value=cb), \
             patch.object(self.service.automation, "execute", new_callable=AsyncMock) as mock_auto_exec, \
             patch("denver.automation.whatsapp.WhatsAppDispatcher.dispatch_message") as mock_dispatch:
            async def run_test() -> None:
                result = await self.service.process_command(
                    "Denver, send WhatsApp to Alex saying Let us meet tomorrow"
                )
                # 1. Ambiguous match returns clarification prompt and success=False
                self.assertFalse(result.success)
                self.assertIn("multiple contacts matching", result.message.lower())
                self.assertIn("Alex Kumar", result.message)
                self.assertIn("Alex Sharma", result.message)
                self.assertEqual(result.error, "AmbiguousContactMatch")
                await asyncio.sleep(0.05)

            asyncio.run(run_test())

            # 2. Assert WhatsApp dispatcher and automation executor were NOT called
            mock_auto_exec.assert_not_called()
            mock_dispatch.assert_not_called()

        # 3. Assert Event Bus emit was NOT called
        self.assertEqual(len(events_received), 0)
        temp_dir.cleanup()

    def test_unambiguous_contact_dispatches_and_emits_event(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        file_path = Path(temp_dir.name) / "contacts.json"
        cb = ContactBook(file_path=file_path)
        cb.add_or_update(
            Contact(
                name="Unique Contact",
                phone="+919112233445",
                aliases=["unique"],
                relationship="friend",
            )
        )

        events_received: list[WhatsAppMessageDispatched] = []

        async def handler(event: WhatsAppMessageDispatched) -> None:
            events_received.append(event)

        self.event_bus.subscribe(WhatsAppMessageDispatched, handler)

        with patch("denver.memory.contacts.get_contact_book", return_value=cb):
            async def run_test() -> None:
                result = await self.service.process_command(
                    "Denver, send WhatsApp to Unique saying Hello there"
                )
                self.assertTrue(result.success)
                self.assertEqual(result.action_name, "send_whatsapp_message")
                await asyncio.sleep(0.05)

            asyncio.run(run_test())

        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0].phone, "919112233445")
        self.assertTrue(events_received[0].success)
        temp_dir.cleanup()


def test_whatsapp_dispatch_logs_redact_phone_with_caplog(caplog) -> None:
    """Caplog test asserting full phone number never appears in captured log output."""
    import logging

    caplog.set_level(logging.DEBUG, logger="denver.automation.whatsapp")
    dispatcher = WhatsAppDispatcher()
    raw_phone = "+919876543210"

    dispatcher.dispatch_message(
        message="Test message",
        phone=raw_phone,
        contact_name="TestContact",
        is_mock=True,
    )

    # Full phone string must not be present in captured logs
    assert "+919876543210" not in caplog.text
    assert "919876543210" not in caplog.text
    assert "+91******3210" in caplog.text


def test_whatsapp_dispatch_logs_redact_message_body_with_caplog(caplog) -> None:
    """Caplog test asserting message body text never appears in captured log output."""
    import logging

    caplog.set_level(logging.DEBUG, logger="denver.automation.whatsapp")
    dispatcher = WhatsAppDispatcher()
    secret_body = "Confidential Top Secret OTP 482910"

    dispatcher.dispatch_message(
        message=secret_body,
        phone="+919876543210",
        contact_name="TestContact",
        is_mock=True,
    )

    # Message text must not be present in captured logs
    assert secret_body not in caplog.text
    assert f"message_length={len(secret_body)}" in caplog.text


if __name__ == "__main__":
    unittest.main()


