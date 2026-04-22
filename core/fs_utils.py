import os


class ProjectContext:
    """
    Provides a safe filesystem context for an agent working within a specific root.
    Ensures that all file operations are anchored and prevents path traversal.
    """

    def __init__(self, root: str = None):
        self.root = os.path.abspath(root or os.getcwd())

    def resolve(self, path: str) -> str:
        """
        Resolves a relative path within the project root to an absolute path.
        Raises ValueError if the path attempts to escape the root.
        """
        if os.path.isabs(path):
            # For absolute paths, we still want to ensure they start with our root
            # (This happens if an agent produces an absolute path it shouldn't have)
            resolved = os.path.abspath(path)
        else:
            resolved = os.path.abspath(os.path.join(self.root, path))

        if not resolved.startswith(self.root + os.sep) and resolved != self.root:
            raise ValueError(f"Path escapes project root: {path} -> {resolved}")

        return resolved

    def makedirs(self, path: str, exist_ok: bool = True):
        """Safely create directories within the root."""
        resolved = self.resolve(path)
        os.makedirs(os.path.dirname(resolved) or ".", exist_ok=exist_ok)

    def write_text(self, path: str, content: str, encoding: str = "utf-8"):
        """Safely write text to a file within the root."""
        resolved = self.resolve(path)
        self.makedirs(path)
        with open(resolved, "w", encoding=encoding) as f:
            f.write(content)

    def read_text(self, path: str, encoding: str = "utf-8") -> str:
        """Safely read text from a file within the root."""
        resolved = self.resolve(path)
        with open(resolved, "r", encoding=encoding) as f:
            return f.read()

    def exists(self, path: str) -> bool:
        """Check if a path exists within the root."""
        try:
            resolved = self.resolve(path)
            return os.path.exists(resolved)
        except ValueError:
            return False
