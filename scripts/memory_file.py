"""MemoryFile — persistent agent notes for self-healing behavior."""

from pathlib import Path

DEFAULT_TEMPLATE = "# Agent Notes"


class MemoryFile:
    """Single markdown file the agent reads/writes for self-healing notes."""

    def __init__(self, path: str, max_tokens: int = 32_000):
        self.path = Path(path)
        self.max_tokens = max_tokens
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(DEFAULT_TEMPLATE)

    def read(self) -> str:
        """Read the full notes file."""
        return self.path.read_text()

    def replace(self, old: str, new: str) -> bool:
        """Replace a string in the notes file. Returns False if old not found."""
        content = self.read()
        if old not in content:
            return False
        content = content.replace(old, new, 1)
        char_limit = self.max_tokens * 4
        if len(content) > char_limit:
            content = content[:char_limit]
        self.path.write_text(content)
        return True

    def token_count(self) -> int:
        """Rough token count (1 token ~ 4 chars)."""
        return max(1, len(self.read()) // 4)

    def reset(self) -> None:
        """Reset notes to default template."""
        self.path.write_text(DEFAULT_TEMPLATE)
