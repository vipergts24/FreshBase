"""
Unit tests for TokenTracker budget tiers, hot context trimming,
and session tracking.
"""

import unittest
from unittest.mock import MagicMock


class TestTokenTracker(unittest.TestCase):
    """Test the TokenTracker module."""

    def setUp(self):
        from core.token_tracker import TokenTracker

        self.tracker = TokenTracker(session_id="test-session")

    def test_session_id_assigned(self):
        """Tracker should have the assigned session ID."""
        self.assertEqual(self.tracker.session_id, "test-session")

    def test_record_llm_accumulates(self):
        """LLM usage should accumulate across calls."""
        mock_response = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50

        # Mock completion_cost to return a fixed value
        import core.token_tracker as tt

        original_cost = tt.completion_cost
        tt.completion_cost = lambda completion_response: 0.005

        try:
            self.tracker.record_llm("gpt-4o", mock_response)
            self.tracker.record_llm("gpt-4o", mock_response)

            self.assertEqual(self.tracker.prompt_tokens, 200)
            self.assertEqual(self.tracker.completion_tokens, 100)
            self.assertEqual(self.tracker.llm_calls, 2)
            self.assertAlmostEqual(self.tracker.total_cost, 0.01)
        finally:
            tt.completion_cost = original_cost

    def test_record_embedding_accumulates(self):
        """Embedding usage should accumulate."""
        self.tracker.record_embedding("text-embedding-ada-002", 100)
        self.tracker.record_embedding("text-embedding-ada-002", 200)

        self.assertEqual(self.tracker.embedding_tokens, 300)
        self.assertEqual(self.tracker.embedding_calls, 2)

    def test_record_resource(self):
        """Resource counts should increment."""
        self.tracker.record_resource("docker")
        self.tracker.record_resource("docker")
        self.tracker.record_resource("branch")
        self.tracker.record_resource("worktree")

        self.assertEqual(self.tracker.docker_builds, 2)
        self.assertEqual(self.tracker.git_branches, 1)
        self.assertEqual(self.tracker.worktrees, 1)

    def test_check_intent_budget_green(self):
        """Small messages should be green tier."""
        messages = [{"role": "user", "content": "Fix the typo in README.md"}]
        tier, count = self.tracker.check_intent_budget("gpt-4o", messages)
        self.assertEqual(tier, "green")
        self.assertLess(count, 4000)

    def test_check_intent_budget_red(self):
        """Enormous messages should be red tier (hard block)."""
        # Create a message with >50K estimated tokens (~200K chars)
        huge_content = "x " * 100_000
        messages = [{"role": "user", "content": huge_content}]
        tier, count = self.tracker.check_intent_budget("gpt-4o", messages)
        self.assertEqual(tier, "red")

    def test_trim_hot_context_no_op_when_small(self):
        """Small hot context should not be trimmed."""
        ctx = {"a.py": "print('hello')", "b.py": "print('world')"}
        result = self.tracker.trim_hot_context(ctx, "gpt-4o")
        self.assertEqual(len(result), 2)

    def test_trim_hot_context_evicts_oldest(self):
        """Large hot context should evict oldest entries first."""
        # Create context that would exceed budget
        # Use a model with small context window for testing
        import core.token_tracker as tt

        original = tt.TokenTracker.get_model_context_window
        tt.TokenTracker.get_model_context_window = lambda self, m: 1000

        try:
            # Create 3 entries, each ~150 tokens (600 chars)
            ctx = {
                "old.py": "x" * 600,
                "mid.py": "y" * 600,
                "new.py": "z" * 600,
            }
            # Budget = 1000 * 0.4 = 400 tokens, only fits 1 entry
            result = self.tracker.trim_hot_context(ctx, "test-model")
            self.assertLess(len(result), 3)
            # Newest should be preserved
            self.assertIn("new.py", result)
        finally:
            tt.TokenTracker.get_model_context_window = original

    def test_record_intent_result(self):
        """Intent results should track resolved vs reverted."""
        self.tracker.record_intent_result(resolved=True)
        self.tracker.record_intent_result(resolved=True)
        self.tracker.record_intent_result(resolved=False)

        self.assertEqual(self.tracker.intents_processed, 3)
        self.assertEqual(self.tracker.intents_resolved, 2)
        self.assertEqual(self.tracker.intents_reverted, 1)

    def test_get_total_cost(self):
        """Total cost should include both LLM and embedding costs."""
        self.tracker.total_cost = 0.05
        self.tracker.embedding_cost = 0.001
        self.assertAlmostEqual(self.tracker.get_total_cost(), 0.051)

    def test_thread_safety(self):
        """Multiple threads recording should not corrupt state."""
        import threading

        def record_many():
            for _ in range(100):
                self.tracker.record_embedding("ada-002", 10)

        threads = [threading.Thread(target=record_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(self.tracker.embedding_calls, 500)
        self.assertEqual(self.tracker.embedding_tokens, 5000)


if __name__ == "__main__":
    unittest.main()
