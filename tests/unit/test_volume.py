"""Unit tests for Master Audio Volume Controller."""

from __future__ import annotations

import unittest
from denver.automation.fake import FakeVolumeController
from denver.automation.volume import VolumeController


class TestVolumeController(unittest.TestCase):
    """Test suite for volume control actions and fake test double."""

    def setUp(self) -> None:
        self.fake = FakeVolumeController(initial_volume=50, initial_muted=False)

    def test_fake_set_volume(self) -> None:
        """Verify setting volume to specific level."""
        res = self.fake.set_volume(75)
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("volume"), 75)
        self.assertEqual(self.fake.state["volume"], 75)

    def test_fake_volume_clamping(self) -> None:
        """Verify volume levels outside 0-100 clamp safely."""
        self.fake.set_volume(150)
        self.assertEqual(self.fake.state["volume"], 100)

        self.fake.set_volume(-20)
        self.assertEqual(self.fake.state["volume"], 0)

    def test_fake_increase_and_decrease_volume(self) -> None:
        """Verify increasing and decreasing volume by step."""
        self.fake.set_volume(50)
        self.fake.increase_volume(15)
        self.assertEqual(self.fake.state["volume"], 65)

        self.fake.decrease_volume(20)
        self.assertEqual(self.fake.state["volume"], 45)

    def test_fake_mute_and_unmute(self) -> None:
        """Verify mute and unmute toggling."""
        res = self.fake.mute()
        self.assertTrue(res.success)
        self.assertTrue(self.fake.state["muted"])

        res = self.fake.unmute()
        self.assertTrue(res.success)
        self.assertFalse(self.fake.state["muted"])

    def test_fake_get_volume(self) -> None:
        """Verify get volume returns current status."""
        self.fake.set_volume(60)
        res = self.fake.get_volume()
        self.assertTrue(res.success)
        self.assertEqual(res.data.get("volume"), 60)
        self.assertFalse(res.data.get("is_muted"))


if __name__ == "__main__":
    unittest.main()
