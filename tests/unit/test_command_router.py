"""Unit tests for IntentRouter."""

from __future__ import annotations

import unittest
from denver.commands.models import CommandCategory, CommandRiskLevel
from denver.commands.router import IntentRouter


class TestIntentRouter(unittest.TestCase):
    """Test suite for deterministic intent classification."""

    def setUp(self) -> None:
        self.router = IntentRouter()

    def test_utility_intents(self) -> None:
        """Verify time and date queries route accurately."""
        time_intent = self.router.route("what time is it")
        self.assertEqual(time_intent.intent_name, "get_time")
        self.assertEqual(time_intent.action_name, "get_time")
        self.assertEqual(time_intent.category, CommandCategory.UTILITY)

        date_intent = self.router.route("today's date")
        self.assertEqual(date_intent.intent_name, "get_date")
        self.assertEqual(date_intent.action_name, "get_date")

    def test_system_telemetry_intents(self) -> None:
        """Verify system status, cpu, ram, battery routes."""
        self.assertEqual(self.router.route("system status").action_name, "get_system_status")
        self.assertEqual(self.router.route("cpu usage").action_name, "get_cpu")
        self.assertEqual(self.router.route("memory usage").action_name, "get_ram")
        self.assertEqual(self.router.route("battery status").action_name, "get_battery")

    def test_application_intents(self) -> None:
        """Verify open and close application intent extraction."""
        open_intent = self.router.route("open google chrome")
        self.assertEqual(open_intent.action_name, "open_application")
        self.assertEqual(open_intent.params.get("application"), "google chrome")

        close_intent = self.router.route("close notepad")
        self.assertEqual(close_intent.action_name, "close_application")
        self.assertEqual(close_intent.params.get("application"), "notepad")

    def test_notes_intents(self) -> None:
        """Verify note creation, listing, and searching."""
        create_intent = self.router.route("create note meeting: discuss phase 2 roadmap")
        self.assertEqual(create_intent.action_name, "create_note")
        self.assertEqual(create_intent.params.get("title"), "meeting")
        self.assertEqual(create_intent.params.get("content"), "discuss phase 2 roadmap")

        list_intent = self.router.route("show notes")
        self.assertEqual(list_intent.action_name, "list_notes")

        search_intent = self.router.route("search notes for fake job detector")
        self.assertEqual(search_intent.action_name, "search_notes")
        self.assertEqual(search_intent.params.get("query"), "fake job detector")

    def test_task_intents(self) -> None:
        """Verify task creation, listing, and completion."""
        task_intent = self.router.route("create task study dbms indexing")
        self.assertEqual(task_intent.action_name, "create_task")
        self.assertEqual(task_intent.params.get("task_text"), "study dbms indexing")

        list_intent = self.router.route("list tasks")
        self.assertEqual(list_intent.action_name, "list_tasks")

        complete_intent = self.router.route("complete task 3")
        self.assertEqual(complete_intent.action_name, "complete_task")
        self.assertEqual(complete_intent.params.get("task_id"), 3)

    def test_memory_and_preferences_intents(self) -> None:
        """Verify memory recall, storage, and preference setting."""
        pref_intent = self.router.route("my favorite music is synthwave")
        self.assertEqual(pref_intent.action_name, "set_preference")
        self.assertEqual(pref_intent.params.get("key"), "favorite_music")
        self.assertEqual(pref_intent.params.get("value"), "synthwave")

        rem_intent = self.router.route("remember that the server port is 8080")
        self.assertEqual(rem_intent.action_name, "remember")
        self.assertEqual(rem_intent.params.get("content"), "the server port is 8080")

        recall_intent = self.router.route("what do you remember about server port")
        self.assertEqual(recall_intent.action_name, "recall_memory")

    def test_whatsapp_intents(self) -> None:
        """Verify natural language WhatsApp message commands route directly."""
        intent1 = self.router.route("open whatsapp and send a message to appa saying hi")
        self.assertEqual(intent1.action_name, "send_whatsapp_message")
        self.assertEqual(intent1.params.get("contact"), "appa")
        self.assertEqual(intent1.params.get("message"), "hi")

        intent2 = self.router.route("send message to john on whatsapp saying hello there")
        self.assertEqual(intent2.action_name, "send_whatsapp_message")
        self.assertEqual(intent2.params.get("contact"), "john")
        self.assertEqual(intent2.params.get("message"), "hello there")

        intent3 = self.router.route("message mom on whatsapp: please call me back")
        self.assertEqual(intent3.action_name, "send_whatsapp_message")
        self.assertEqual(intent3.params.get("contact"), "mom")
        self.assertEqual(intent3.params.get("message"), "please call me back")

        intent4 = self.router.route("send whatsapp to alex saying I will join the meeting in 5 minutes")
        self.assertEqual(intent4.action_name, "send_whatsapp_message")
        self.assertEqual(intent4.params.get("contact"), "alex")
        self.assertEqual(intent4.params.get("message"), "I will join the meeting in 5 minutes")

        intent5 = self.router.route("send a whatsapp to mom that I arrived safely")
        self.assertEqual(intent5.action_name, "send_whatsapp_message")
        self.assertEqual(intent5.params.get("contact"), "mom")
        self.assertEqual(intent5.params.get("message"), "I arrived safely")

        intent6 = self.router.route("whatsapp dad saying please call me back")
        self.assertEqual(intent6.action_name, "send_whatsapp_message")
        self.assertEqual(intent6.params.get("contact"), "dad")
        self.assertEqual(intent6.params.get("message"), "please call me back")

        intent7 = self.router.route("tell alex on whatsapp that I will be late")
        self.assertEqual(intent7.action_name, "send_whatsapp_message")
        self.assertEqual(intent7.params.get("contact"), "alex")
        self.assertEqual(intent7.params.get("message"), "I will be late")

        intent8 = self.router.route("send whatsapp message to +919876543210 saying Hello")
        self.assertEqual(intent8.action_name, "send_whatsapp_message")
        self.assertEqual(intent8.params.get("contact"), "+919876543210")
        self.assertEqual(intent8.params.get("message"), "Hello")

    def test_unknown_intent(self) -> None:
        """Verify unrecognized queries return unknown intent with 0.0 confidence."""
        unknown = self.router.route("fly me to mars tomorrow")
        self.assertEqual(unknown.intent_name, "unknown")
        self.assertEqual(unknown.action_name, "unknown")
        self.assertEqual(unknown.confidence, 0.0)


if __name__ == "__main__":
    unittest.main()
