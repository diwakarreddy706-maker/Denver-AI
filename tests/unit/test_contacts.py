"""Unit tests for ContactBook and contact alias resolution."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from denver.memory.contacts import Contact, ContactBook


class TestContactBook(unittest.TestCase):
    """Test suite for local contacts address book."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_path = Path(self.temp_dir.name) / "test_contacts.json"
        self.cb = ContactBook(file_path=self.file_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_default_contacts_loaded(self) -> None:
        """Verify default template contacts are initialized when file does not exist."""
        contacts = self.cb.list_all()
        self.assertGreater(len(contacts), 0)
        self.assertTrue(self.file_path.exists())

    def test_find_contact_by_alias(self) -> None:
        """Verify searching by alias resolves to the target contact."""
        c = Contact(
            name="Diwakar Reddy",
            phone="+919876543210",
            aliases=["diwakar", "me", "myself"],
            relationship="self",
        )
        self.cb.add_or_update(c)

        self.assertEqual(self.cb.find_contact("diwakar").phone, "+919876543210")
        self.assertEqual(self.cb.find_contact("myself").name, "Diwakar Reddy")
        self.assertEqual(self.cb.find_contact("self").phone, "+919876543210")

    def test_clean_phone(self) -> None:
        """Verify clean_phone strips country code + and formatting."""
        c = Contact(name="Test", phone="+91 98765-43210")
        self.assertEqual(c.clean_phone(), "919876543210")


if __name__ == "__main__":
    unittest.main()
