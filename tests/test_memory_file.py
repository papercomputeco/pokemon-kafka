"""Tests for MemoryFile — agent note-taking system."""

from memory_file import MemoryFile


class TestMemoryFile:
    def test_init_creates_empty_file(self, tmp_path):
        path = tmp_path / "notes.md"
        mf = MemoryFile(str(path))
        assert path.exists()
        assert "# Agent Notes" in mf.read()

    def test_read_returns_content(self, tmp_path):
        path = tmp_path / "notes.md"
        mf = MemoryFile(str(path))
        content = mf.read()
        assert isinstance(content, str)

    def test_replace_updates_content(self, tmp_path):
        path = tmp_path / "notes.md"
        mf = MemoryFile(str(path))
        mf.replace("# Agent Notes", "# Agent Notes\n\n## Current Objective\nBeat Brock")
        content = mf.read()
        assert "Beat Brock" in content

    def test_replace_no_match_returns_false(self, tmp_path):
        path = tmp_path / "notes.md"
        mf = MemoryFile(str(path))
        result = mf.replace("NONEXISTENT TEXT", "replacement")
        assert result is False

    def test_replace_returns_true_on_success(self, tmp_path):
        path = tmp_path / "notes.md"
        mf = MemoryFile(str(path))
        result = mf.replace("# Agent Notes", "# Agent Notes\n\n## Test")
        assert result is True

    def test_token_count(self, tmp_path):
        path = tmp_path / "notes.md"
        mf = MemoryFile(str(path))
        count = mf.token_count()
        assert isinstance(count, int)
        assert count > 0

    def test_token_limit_enforced(self, tmp_path):
        path = tmp_path / "notes.md"
        mf = MemoryFile(str(path), max_tokens=10)
        big_content = "word " * 1000
        mf.replace("# Agent Notes", big_content)
        assert mf.token_count() <= 10

    def test_reset(self, tmp_path):
        path = tmp_path / "notes.md"
        mf = MemoryFile(str(path))
        mf.replace("# Agent Notes", "# Agent Notes\n\nSome data")
        mf.reset()
        content = mf.read()
        assert content.strip() == "# Agent Notes"

    def test_existing_file_preserved(self, tmp_path):
        path = tmp_path / "notes.md"
        path.write_text("# Existing Notes\n\nKeep this")
        mf = MemoryFile(str(path))
        assert "Keep this" in mf.read()
