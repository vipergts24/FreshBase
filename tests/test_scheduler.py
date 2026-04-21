"""
Unit tests for IntentScheduler dependency classification.
Tests the Union-Find grouping logic with mock Intent objects.
"""

import unittest
from unittest.mock import MagicMock, patch


class MockIntent:
    """Lightweight mock of the Intent ORM model."""

    def __init__(self, id, description=""):
        self.id = id
        self.description = description


class TestBuildGroups(unittest.TestCase):
    """Test the Union-Find grouping algorithm in isolation."""

    def setUp(self):
        from core.scheduler import IntentScheduler

        self.scheduler = IntentScheduler()

    def test_single_intent_returns_one_group(self):
        """A single intent should return [[intent]] with no classification."""
        intent = MockIntent(1, "Create cart.py")
        result = self.scheduler._build_groups([intent], {1: {"cart.py"}})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0].id, 1)

    def test_independent_intents_separate_groups(self):
        """Intents referencing different files should be in separate groups."""
        intents = [
            MockIntent(1, "Modify cart.py"),
            MockIntent(2, "Modify utils.py"),
            MockIntent(3, "Modify README.md"),
        ]
        intent_files = {
            1: {"cart.py"},
            2: {"utils.py"},
            3: {"README.md"},
        }
        result = self.scheduler._build_groups(intents, intent_files)
        self.assertEqual(len(result), 3)

    def test_shared_file_same_group(self):
        """Intents referencing the same file should be in the same group."""
        intents = [
            MockIntent(1, "Create cart.py"),
            MockIntent(2, "Add discount to cart.py"),
            MockIntent(3, "Add tests for cart.py"),
        ]
        intent_files = {
            1: {"cart.py"},
            2: {"cart.py"},
            3: {"cart.py"},
        }
        result = self.scheduler._build_groups(intents, intent_files)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 3)

    def test_mixed_groups(self):
        """Two intents share cart.py, one is independent."""
        intents = [
            MockIntent(1, "Create cart.py"),
            MockIntent(2, "Add discount to cart.py"),
            MockIntent(3, "Fix README typo"),
        ]
        intent_files = {
            1: {"cart.py"},
            2: {"cart.py"},
            3: {"README.md"},
        }
        result = self.scheduler._build_groups(intents, intent_files)
        self.assertEqual(len(result), 2)

        # Find the cart group and readme group
        group_sizes = sorted([len(g) for g in result])
        self.assertEqual(group_sizes, [1, 2])

    def test_transitive_dependency(self):
        """A shares file with B, B shares file with C, so all 3 group together."""
        intents = [
            MockIntent(1, "Modify cart.py"),
            MockIntent(2, "Modify cart.py and utils.py"),
            MockIntent(3, "Modify utils.py"),
        ]
        intent_files = {
            1: {"cart.py"},
            2: {"cart.py", "utils.py"},
            3: {"utils.py"},
        }
        result = self.scheduler._build_groups(intents, intent_files)
        # A→B via cart.py, B→C via utils.py, so all 3 are transitively linked
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 3)

    def test_preserves_queue_order_within_groups(self):
        """Intents within a group should maintain original queue order."""
        intents = [
            MockIntent(10, "First"),
            MockIntent(20, "Second"),
            MockIntent(30, "Third"),
        ]
        intent_files = {
            10: {"cart.py"},
            20: {"cart.py"},
            30: {"cart.py"},
        }
        result = self.scheduler._build_groups(intents, intent_files)
        ids = [i.id for i in result[0]]
        self.assertEqual(ids, [10, 20, 30])

    def test_no_file_mapping_treated_as_independent(self):
        """Intents with no file mappings should each be their own group."""
        intents = [
            MockIntent(1, "Do something"),
            MockIntent(2, "Do something else"),
        ]
        intent_files = {}
        result = self.scheduler._build_groups(intents, intent_files)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
