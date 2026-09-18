"""Unit tests for ActionRegistry."""

from __future__ import annotations

import unittest
from denver.commands.models import ActionResult, CommandCategory, CommandRiskLevel
from denver.commands.registry import ActionDefinition, ActionRegistry


class TestActionRegistry(unittest.TestCase):
    """Test suite for ActionRegistry lifecycle and lookups."""

    def setUp(self) -> None:
        self.registry = ActionRegistry()

    def test_register_and_get_action(self) -> None:
        """Verify registering an action enables lookup by name."""
        def _dummy_handler(params):
            return ActionResult(success=True, message="OK", action_name="test_action")

        action = ActionDefinition(
            name="test_action",
            description="A test action",
            category=CommandCategory.UTILITY,
            risk_level=CommandRiskLevel.SAFE,
            handler=_dummy_handler,
        )
        self.registry.register(action)

        retrieved = self.registry.get("test_action")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.description, "A test action")
        self.assertTrue(self.registry.has_action("test_action"))

    def test_duplicate_registration_rejected(self) -> None:
        """Verify registering duplicate action name raises ValueError."""
        def _dummy(params):
            pass

        action1 = ActionDefinition(
            name="dup_action",
            description="First",
            category=CommandCategory.UTILITY,
            risk_level=CommandRiskLevel.SAFE,
            handler=_dummy,
        )
        action2 = ActionDefinition(
            name="dup_action",
            description="Second",
            category=CommandCategory.UTILITY,
            risk_level=CommandRiskLevel.SAFE,
            handler=_dummy,
        )
        self.registry.register(action1)
        with self.assertRaises(ValueError):
            self.registry.register(action2)

    def test_list_and_filter_actions(self) -> None:
        """Verify filtering actions by category."""
        def _dummy(params):
            pass

        self.registry.register(ActionDefinition("act1", "d1", CommandCategory.SYSTEM, CommandRiskLevel.SAFE, _dummy))
        self.registry.register(ActionDefinition("act2", "d2", CommandCategory.NOTE, CommandRiskLevel.SAFE, _dummy))

        all_actions = self.registry.list_actions()
        self.assertEqual(len(all_actions), 2)

        sys_actions = self.registry.list_actions(category=CommandCategory.SYSTEM)
        self.assertEqual(len(sys_actions), 1)
        self.assertEqual(sys_actions[0].name, "act1")

    def test_enable_and_disable_action(self) -> None:
        """Verify enabling and disabling actions."""
        def _dummy(params):
            pass

        self.registry.register(ActionDefinition("toggle_act", "desc", CommandCategory.UTILITY, CommandRiskLevel.SAFE, _dummy))
        self.assertTrue(self.registry.get("toggle_act").enabled)

        self.registry.disable_action("toggle_act")
        self.assertFalse(self.registry.get("toggle_act").enabled)

        self.registry.enable_action("toggle_act")
        self.assertTrue(self.registry.get("toggle_act").enabled)


if __name__ == "__main__":
    unittest.main()
