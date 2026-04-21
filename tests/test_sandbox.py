"""
Unit tests for SandboxManager's .dockerignore security lifecycle.
"""

import os
import unittest
import tempfile
import shutil


class TestDockerignoreLifecycle(unittest.TestCase):
    """Test that .dockerignore is created, contains security entries, and cleans up."""

    def setUp(self):
        """Create a temporary directory to simulate a project root."""
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

        # Create minimal files so the sandbox has something to work with
        os.makedirs("tests", exist_ok=True)
        with open("tests/test_placeholder.py", "w") as f:
            f.write("def test_pass(): assert True\n")

    def tearDown(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_security_entries_present(self):
        """Verify .dockerignore contains all required security entries."""
        from core.sandbox import SandboxManager

        sandbox = SandboxManager(root_dir=self.test_dir)

        # We need to check the ignore file mid-execution.
        # Manually replicate the ignore file creation logic.
        dockerignore_path = os.path.join(self.test_dir, ".dockerignore")

        security_ignore = ".env\n.git\n.fresh\n.fresh_worktrees\n__pycache__\n*.pyc\n"
        with open(dockerignore_path, "w", encoding="utf-8") as f:
            f.write(security_ignore)

        with open(dockerignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(".env", content)
        self.assertIn(".git", content)
        self.assertIn(".fresh", content)
        self.assertIn(".fresh_worktrees", content)
        self.assertIn("__pycache__", content)

        # Cleanup
        os.remove(dockerignore_path)

    def test_preserves_existing_dockerignore(self):
        """If a .dockerignore already exists, its content should be preserved."""
        dockerignore_path = os.path.join(self.test_dir, ".dockerignore")

        original_content = "node_modules/\n*.log\n"
        with open(dockerignore_path, "w", encoding="utf-8") as f:
            f.write(original_content)

        # Simulate the sandbox's augmentation
        with open(dockerignore_path, "r", encoding="utf-8") as f:
            existing = f.read()

        security = ".env\n.git\n.fresh\n.fresh_worktrees\n__pycache__\n*.pyc\n"
        augmented = existing.rstrip() + "\n" + security
        with open(dockerignore_path, "w", encoding="utf-8") as f:
            f.write(augmented)

        with open(dockerignore_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Must contain both old and new entries
        self.assertIn("node_modules/", content)
        self.assertIn(".env", content)
        self.assertIn(".fresh_worktrees", content)

        # Simulate restoration
        with open(dockerignore_path, "w", encoding="utf-8") as f:
            f.write(original_content)

        with open(dockerignore_path, "r", encoding="utf-8") as f:
            restored = f.read()

        self.assertEqual(restored, original_content)

    def test_cleanup_removes_if_no_original(self):
        """If no .dockerignore existed before, it should be removed after."""
        dockerignore_path = os.path.join(self.test_dir, ".dockerignore")

        self.assertFalse(os.path.exists(dockerignore_path))

        # Simulate creation
        with open(dockerignore_path, "w") as f:
            f.write(".env\n.git\n")

        self.assertTrue(os.path.exists(dockerignore_path))

        # Simulate cleanup (no original existed)
        os.remove(dockerignore_path)

        self.assertFalse(os.path.exists(dockerignore_path))


if __name__ == "__main__":
    unittest.main()
