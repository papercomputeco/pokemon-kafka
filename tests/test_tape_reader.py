"""Tests for tape_reader.py — 100% coverage."""

import json

import pytest
from tape_helpers import create_test_db, insert_test_node
from tape_reader import (
    TapeEntry,
    TapeReader,
    TapeSession,
    TokenUsage,
    ToolResult,
    ToolUse,
    _parse_content_blob,
    _summarize_tool_input,
)

# ── Dataclass defaults ──────────────────────────────────────────────


class TestTapeEntry:
    def test_defaults(self):
        e = TapeEntry()
        assert e.type == ""
        assert e.timestamp == ""
        assert e.session_id == ""
        assert e.text_content == ""
        assert e.tool_uses == []
        assert e.tool_results == []
        assert e.token_usage == TokenUsage()
        assert e.raw == {}

    def test_mutable_defaults_independent(self):
        a = TapeEntry()
        b = TapeEntry()
        a.tool_uses.append(ToolUse(id="x"))
        assert b.tool_uses == []


class TestToolUse:
    def test_defaults(self):
        t = ToolUse()
        assert t.id == ""
        assert t.name == ""
        assert t.input_summary == ""


class TestToolResult:
    def test_defaults(self):
        r = ToolResult()
        assert r.tool_use_id == ""
        assert r.content_summary == ""
        assert r.is_error is False


class TestTokenUsage:
    def test_defaults(self):
        u = TokenUsage()
        assert u.input_tokens == 0
        assert u.output_tokens == 0
        assert u.cache_creation == 0
        assert u.cache_read == 0


class TestTapeSession:
    def test_defaults(self):
        s = TapeSession()
        assert s.session_id == ""
        assert s.entries == []
        assert s.start_time == ""
        assert s.end_time == ""


# ── _parse_content_blob ──────────────────────────────────────────────


class TestParseContentBlob:
    def test_none(self):
        assert _parse_content_blob(None) == []

    def test_valid_json_list(self):
        blob = json.dumps([{"type": "text", "text": "hi"}])
        result = _parse_content_blob(blob)
        assert len(result) == 1
        assert result[0]["text"] == "hi"

    def test_filters_non_dicts(self):
        blob = json.dumps(["string", {"type": "text"}, 42])
        result = _parse_content_blob(blob)
        assert len(result) == 1

    def test_invalid_json(self):
        assert _parse_content_blob("not json{") == []

    def test_non_list_json(self):
        blob = json.dumps({"key": "value"})
        assert _parse_content_blob(blob) == []

    def test_bytes_input(self):
        blob = json.dumps([{"type": "text"}]).encode()
        result = _parse_content_blob(blob)
        assert len(result) == 1


# ── _row_to_entry ────────────────────────────────────────────────────


class TestRowToEntry:
    def _make_reader(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        return TapeReader(str(db_path))

    def test_user_text_message(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "h1", role="user", content=[{"type": "text", "text": "do something"}])

        reader = TapeReader(str(db_path))
        session = reader.read_session("h1")
        assert len(session.entries) == 1
        entry = session.entries[0]
        assert entry.type == "user"
        assert entry.text_content == "do something"

    def test_assistant_with_tool_use(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn,
            "h1",
            role="assistant",
            content=[
                {"type": "text", "text": "Let me read that."},
                {
                    "type": "tool_use",
                    "tool_use_id": "tu-1",
                    "tool_name": "Read",
                    "tool_input": {"file_path": "/foo.py"},
                },
            ],
            prompt_tokens=1000,
            completion_tokens=200,
            cache_creation=50,
            cache_read=800,
        )

        reader = TapeReader(str(db_path))
        session = reader.read_session("h1")
        entry = session.entries[0]
        assert entry.text_content == "Let me read that."
        assert len(entry.tool_uses) == 1
        assert entry.tool_uses[0].name == "Read"
        assert entry.tool_uses[0].input_summary == "/foo.py"
        assert entry.token_usage.input_tokens == 1000
        assert entry.token_usage.cache_read == 800

    def test_user_with_tool_result(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn,
            "h1",
            role="user",
            content=[
                {"type": "tool_result", "tool_use_id": "tu-1", "content": "file contents", "is_error": False},
            ],
        )

        reader = TapeReader(str(db_path))
        session = reader.read_session("h1")
        entry = session.entries[0]
        assert len(entry.tool_results) == 1
        assert entry.tool_results[0].content_summary == "file contents"
        assert entry.tool_results[0].is_error is False

    def test_user_with_error_tool_result(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn,
            "h1",
            role="user",
            content=[
                {"type": "tool_result", "tool_use_id": "tu-1", "content": "command failed", "is_error": True},
            ],
        )

        reader = TapeReader(str(db_path))
        entry = reader.read_session("h1").entries[0]
        assert entry.tool_results[0].is_error is True

    def test_tool_result_with_list_content(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn,
            "h1",
            role="user",
            content=[
                {
                    "type": "tool_result",
                    "tool_use_id": "tu-1",
                    "content": [
                        {"type": "text", "text": "line 1"},
                        {"type": "text", "text": "line 2"},
                    ],
                },
            ],
        )

        reader = TapeReader(str(db_path))
        entry = reader.read_session("h1").entries[0]
        assert entry.tool_results[0].content_summary == "line 1\nline 2"

    def test_empty_role_node(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "h1", role="", content=[])

        reader = TapeReader(str(db_path))
        entry = reader.read_session("h1").entries[0]
        assert entry.type == ""
        assert entry.text_content == ""

    def test_null_role_node(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "h1", role=None, content=None)

        reader = TapeReader(str(db_path))
        entry = reader.read_session("h1").entries[0]
        assert entry.type == ""

    def test_null_tokens(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "h1", role="assistant", content=[{"type": "text", "text": "hi"}])

        reader = TapeReader(str(db_path))
        entry = reader.read_session("h1").entries[0]
        assert entry.token_usage.input_tokens == 0
        assert entry.token_usage.output_tokens == 0

    def test_raw_dict_populated(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn, "h1", role="user", content=[], model="claude-opus-4-6", agent_name="claude", parent_hash="h0"
        )

        reader = TapeReader(str(db_path))
        entry = reader.read_session("h1").entries[0]
        assert entry.raw["hash"] == "h1"
        assert entry.raw["model"] == "claude-opus-4-6"
        assert entry.raw["agent_name"] == "claude"
        assert entry.raw["parent_hash"] == "h0"


# ── _summarize_tool_input ────────────────────────────────────────────


class TestSummarizeToolInput:
    def test_read(self):
        assert _summarize_tool_input("Read", {"file_path": "/a.py"}) == "/a.py"

    def test_write(self):
        assert _summarize_tool_input("Write", {"file_path": "/b.py"}) == "/b.py"

    def test_edit(self):
        assert _summarize_tool_input("Edit", {"file_path": "/c.py"}) == "/c.py"

    def test_bash(self):
        assert _summarize_tool_input("Bash", {"command": "ls -la"}) == "ls -la"

    def test_grep(self):
        assert _summarize_tool_input("Grep", {"pattern": "foo"}) == "pattern=foo"

    def test_glob(self):
        assert _summarize_tool_input("Glob", {"pattern": "*.py"}) == "pattern=*.py"

    def test_agent(self):
        assert _summarize_tool_input("Agent", {"description": "explore code"}) == "explore code"

    def test_generic_with_known_key(self):
        result = _summarize_tool_input("WebSearch", {"query": "python docs"})
        assert result == "query=python docs"

    def test_generic_fallback(self):
        result = _summarize_tool_input("Unknown", {"some_key": "val"})
        assert "some_key" in result

    def test_non_dict_input(self):
        result = _summarize_tool_input("Foo", "just a string")
        assert result == "just a string"

    def test_generic_key_priority(self):
        result = _summarize_tool_input("Custom", {"description": "desc", "prompt": "p"})
        assert result == "prompt=p"


# ── TapeReader ───────────────────────────────────────────────────────


class TestTapeReaderListSessions:
    def test_empty_db(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        reader = TapeReader(str(db_path))
        assert reader.list_sessions() == []

    def test_finds_root_nodes(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "root1", role="user", content=[], created_at="2026-01-01T00:00:00Z")
        insert_test_node(
            conn, "child1", role="assistant", content=[], parent_hash="root1", created_at="2026-01-01T00:01:00Z"
        )
        insert_test_node(conn, "root2", role="user", content=[], created_at="2026-01-02T00:00:00Z")

        reader = TapeReader(str(db_path))
        sessions = reader.list_sessions()
        assert sessions == ["root1", "root2"]

    def test_ordered_by_time(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "later", role="user", content=[], created_at="2026-01-02T00:00:00Z")
        insert_test_node(conn, "earlier", role="user", content=[], created_at="2026-01-01T00:00:00Z")

        reader = TapeReader(str(db_path))
        assert reader.list_sessions() == ["earlier", "later"]


class TestTapeReaderReadSession:
    def test_basic_chain(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn, "h1", role="user", content=[{"type": "text", "text": "hi"}], created_at="2026-01-01T00:00:00Z"
        )
        insert_test_node(
            conn,
            "h2",
            role="assistant",
            content=[{"type": "text", "text": "hello"}],
            created_at="2026-01-01T00:01:00Z",
            parent_hash="h1",
        )

        reader = TapeReader(str(db_path))
        session = reader.read_session("h1")
        assert session.session_id == "h1"
        assert len(session.entries) == 2
        assert session.start_time == "2026-01-01T00:00:00Z"
        assert session.end_time == "2026-01-01T00:01:00Z"

    def test_single_node_session(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "h1", role="user", content=[{"type": "text", "text": "solo"}])

        reader = TapeReader(str(db_path))
        session = reader.read_session("h1")
        assert len(session.entries) == 1
        assert session.start_time == session.end_time

    def test_empty_session(self, tmp_path):
        """Reading a hash that doesn't exist returns empty session."""
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        reader = TapeReader(str(db_path))
        session = reader.read_session("nonexistent")
        assert session.entries == []
        assert session.start_time == ""
        assert session.end_time == ""


class TestTapeReaderIterEntries:
    def test_generator_behavior(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn, "h1", role="user", content=[{"type": "text", "text": "line1"}], created_at="2026-01-01T00:00:00Z"
        )
        insert_test_node(
            conn,
            "h2",
            role="assistant",
            content=[{"type": "text", "text": "line2"}],
            created_at="2026-01-01T00:01:00Z",
            parent_hash="h1",
        )

        reader = TapeReader(str(db_path))
        gen = reader.iter_entries("h1")
        first = next(gen)
        assert first.text_content == "line1"
        second = next(gen)
        assert second.text_content == "line2"
        with pytest.raises(StopIteration):
            next(gen)

    def test_empty_chain(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        reader = TapeReader(str(db_path))
        entries = list(reader.iter_entries("nonexistent"))
        assert entries == []


# ── Context manager ─────────────────────────────────────────────────


class TestTapeReaderContextManager:
    def test_context_manager_reuses_connection(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn, "h1", role="user", content=[{"type": "text", "text": "hi"}], created_at="2026-01-01T00:00:00Z"
        )
        insert_test_node(
            conn, "h2", role="user", content=[{"type": "text", "text": "bye"}], created_at="2026-01-02T00:00:00Z"
        )

        with TapeReader(str(db_path)) as reader:
            sessions = reader.list_sessions()
            assert sessions == ["h1", "h2"]
            session = reader.read_session("h1")
            assert session.entries[0].text_content == "hi"
            # Connection should be the same object across calls
            assert reader._conn is not None

        # After exiting, connection should be closed
        assert reader._conn is None

    def test_works_without_context_manager(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "h1", role="user", content=[{"type": "text", "text": "hi"}])

        reader = TapeReader(str(db_path))
        assert reader._conn is None
        sessions = reader.list_sessions()
        assert sessions == ["h1"]
        # No managed connection — should still be None
        assert reader._conn is None
