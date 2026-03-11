"""Tests for observer.py — 100% coverage."""

import json

from observer import (
    Observation,
    Observer,
    _extract_traceback_summary,
    _first_user_message,
    _has_traceback,
    observe_session_inline,
)
from tape_helpers import create_test_db, insert_test_node
from tape_reader import TapeEntry, TapeSession, TokenUsage, ToolResult

# ── Observation dataclass ────────────────────────────────────────────


class TestObservation:
    def test_defaults(self):
        o = Observation()
        assert o.timestamp == ""
        assert o.referenced_time == ""
        assert o.priority == "informational"
        assert o.content == ""
        assert o.source_session == ""


# ── Helper functions ─────────────────────────────────────────────────


class TestFirstUserMessage:
    def test_finds_first_user(self):
        session = TapeSession(
            session_id="s1",
            entries=[
                TapeEntry(type="assistant", text_content="init"),
                TapeEntry(type="user", text_content="build a feature"),
                TapeEntry(type="user", text_content="second msg"),
            ],
        )
        assert _first_user_message(session) == "build a feature"

    def test_no_user_messages(self):
        session = TapeSession(session_id="s1", entries=[])
        assert _first_user_message(session) == ""

    def test_user_with_empty_text(self):
        session = TapeSession(
            session_id="s1",
            entries=[
                TapeEntry(type="user", text_content=""),
                TapeEntry(type="user", text_content="actual message"),
            ],
        )
        assert _first_user_message(session) == "actual message"

    def test_skips_system_reminder(self):
        session = TapeSession(
            session_id="s1",
            entries=[
                TapeEntry(type="user", text_content="<system-reminder>\nsome hook output\n</system-reminder>"),
                TapeEntry(type="user", text_content="fix the bug"),
            ],
        )
        assert _first_user_message(session) == "fix the bug"

    def test_all_system_reminders(self):
        session = TapeSession(
            session_id="s1",
            entries=[
                TapeEntry(type="user", text_content="<system-reminder>hook</system-reminder>"),
            ],
        )
        assert _first_user_message(session) == ""


class TestHasTraceback:
    def test_python_traceback(self):
        assert _has_traceback("Traceback (most recent call last):\n  File...")

    def test_error_at_line_start(self):
        assert _has_traceback("ValueError: bad value")

    def test_exception_at_line_start(self):
        assert _has_traceback("RuntimeException: oops")

    def test_error_midline_no_match(self):
        """Casual mention of 'error' should not match."""
        assert not _has_traceback("I see the error in the code")

    def test_error_in_sentence(self):
        assert not _has_traceback("Error handling is important")

    def test_no_traceback(self):
        assert not _has_traceback("everything is fine")

    def test_multiline_with_error_on_own_line(self):
        text = "Some context\nModuleNotFoundError: No module named 'foo'\nmore"
        assert _has_traceback(text)

    def test_lowercase_prefix_no_match(self):
        """Lowercase-starting names like 'myCustomError:' should not match."""
        assert not _has_traceback("myCustomError: something went wrong")


class TestExtractTracebackSummary:
    def test_extracts_last_error_line(self):
        text = "Some context\nValueError: bad input\nmore stuff"
        assert _extract_traceback_summary(text) == "ValueError: bad input"

    def test_exception_line(self):
        text = "RuntimeException: oops"
        assert _extract_traceback_summary(text) == "RuntimeException: oops"

    def test_no_error_line_falls_back(self):
        text = "just some output"
        assert _extract_traceback_summary(text) == "just some output"


# ── Observer ─────────────────────────────────────────────────────────


class TestObserverInit:
    def test_constructor(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        obs = Observer(
            db_path=str(db_path),
            memory_dir=str(tmp_path / "memory"),
        )
        assert obs.db_path == db_path
        assert obs.memory_dir == tmp_path / "memory"


class TestGetUnprocessedSessions:
    def test_all_unprocessed(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "aaa", created_at="2026-01-01T00:00:00Z")
        insert_test_node(conn, "bbb", created_at="2026-01-02T00:00:00Z")

        obs = Observer(str(db_path), str(tmp_path / "memory"))
        assert obs.get_unprocessed_sessions() == ["aaa", "bbb"]

    def test_some_processed(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "aaa", created_at="2026-01-01T00:00:00Z")
        insert_test_node(conn, "bbb", created_at="2026-01-02T00:00:00Z")

        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "observer_state.json").write_text(json.dumps({"processed_sessions": ["aaa"]}))

        obs = Observer(str(db_path), str(mem))
        assert obs.get_unprocessed_sessions() == ["bbb"]

    def test_all_processed(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "aaa", created_at="2026-01-01T00:00:00Z")

        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "observer_state.json").write_text(json.dumps({"processed_sessions": ["aaa"]}))

        obs = Observer(str(db_path), str(mem))
        assert obs.get_unprocessed_sessions() == []

    def test_empty_db(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        obs = Observer(str(db_path), str(tmp_path / "memory"))
        assert obs.get_unprocessed_sessions() == []


class TestObserveSession:
    def _make_session(self, entries=None):
        return TapeSession(
            session_id="test-sess",
            entries=entries or [],
            start_time="2026-03-09T10:00:00Z",
            end_time="2026-03-09T10:30:00Z",
        )

    def test_extracts_session_goal(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        session = self._make_session(entries=[TapeEntry(type="user", text_content="fix the login bug")])
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        results = obs.observe_session(session)
        goals = [o for o in results if "Session goal" in o.content]
        assert len(goals) == 1
        assert "fix the login bug" in goals[0].content

    def test_extracts_tool_errors(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        session = self._make_session(
            entries=[
                TapeEntry(
                    type="user",
                    timestamp="2026-03-09T10:05:00Z",
                    tool_results=[
                        ToolResult(
                            tool_use_id="tu-1",
                            content_summary="command not found",
                            is_error=True,
                        )
                    ],
                )
            ]
        )
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        results = obs.observe_session(session)
        errors = [o for o in results if "Tool error" in o.content]
        assert len(errors) == 1
        assert errors[0].priority == "important"

    def test_extracts_tracebacks(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        session = self._make_session(
            entries=[
                TapeEntry(
                    type="assistant",
                    timestamp="2026-03-09T10:05:00Z",
                    text_content="I see an error:\nValueError: bad input\nLet me fix it.",
                )
            ]
        )
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        results = obs.observe_session(session)
        tracebacks = [o for o in results if "Exception discussed" in o.content]
        assert len(tracebacks) == 1

    def test_extracts_file_creations(self, tmp_path):
        from tape_reader import ToolUse

        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        session = self._make_session(
            entries=[
                TapeEntry(
                    type="assistant",
                    timestamp="2026-03-09T10:05:00Z",
                    tool_uses=[ToolUse(id="tu-1", name="Write", input_summary="/new_file.py")],
                )
            ]
        )
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        results = obs.observe_session(session)
        files = [o for o in results if "File created" in o.content]
        assert len(files) == 1
        assert "/new_file.py" in files[0].content

    def test_extracts_token_usage(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        session = self._make_session(
            entries=[
                TapeEntry(
                    type="assistant",
                    token_usage=TokenUsage(
                        input_tokens=1000,
                        output_tokens=200,
                        cache_read=800,
                    ),
                )
            ]
        )
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        results = obs.observe_session(session)
        usage = [o for o in results if "Token usage" in o.content]
        assert len(usage) == 1
        assert "800 cache read" in usage[0].content

    def test_no_token_usage_when_zero(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        session = self._make_session(entries=[TapeEntry(type="assistant")])
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        results = obs.observe_session(session)
        usage = [o for o in results if "Token usage" in o.content]
        assert len(usage) == 0

    def test_empty_session(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        session = self._make_session()
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        results = obs.observe_session(session)
        assert len(results) == 0

    def test_write_tool_with_empty_summary_skipped(self, tmp_path):
        from tape_reader import ToolUse

        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        session = self._make_session(
            entries=[
                TapeEntry(
                    type="assistant",
                    tool_uses=[ToolUse(id="tu-1", name="Write", input_summary="")],
                )
            ]
        )
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        results = obs.observe_session(session)
        files = [o for o in results if "File created" in o.content]
        assert len(files) == 0

    def test_non_write_tools_not_tracked(self, tmp_path):
        from tape_reader import ToolUse

        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        session = self._make_session(
            entries=[
                TapeEntry(
                    type="assistant",
                    tool_uses=[ToolUse(id="tu-1", name="Read", input_summary="/some.py")],
                )
            ]
        )
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        results = obs.observe_session(session)
        files = [o for o in results if "File created" in o.content]
        assert len(files) == 0


class TestClassifyPriority:
    def test_important_keywords(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        assert obs.classify_priority("Fixed a bug in login") == "important"
        assert obs.classify_priority("Error: connection failed") == "important"
        assert obs.classify_priority("crash on startup") == "important"
        assert obs.classify_priority("security vulnerability found") == "important"

    def test_possible_keywords(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        assert obs.classify_priority("test coverage added") == "possible"
        assert obs.classify_priority("refactor the module") == "possible"
        assert obs.classify_priority("update dependencies") == "possible"

    def test_informational_default(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        assert obs.classify_priority("Session started") == "informational"

    def test_custom_default(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        assert obs.classify_priority("nothing special", "possible") == "possible"

    def test_important_beats_possible(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        assert obs.classify_priority("fix the test") == "important"


class TestWriteObservations:
    def test_writes_markdown_file(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "memory"
        obs = Observer(str(db_path), str(mem))
        observations = [
            Observation(
                referenced_time="2026-03-09T10:00:00Z",
                priority="important",
                content="Found a bug",
                source_session="abcdef12-3456",
            ),
            Observation(
                referenced_time="2026-03-09T11:00:00Z",
                priority="informational",
                content="Session started",
                source_session="abcdef12-3456",
            ),
        ]
        obs.write_observations(observations)

        content = (mem / "observations.md").read_text()
        assert "## 2026-03-09" in content
        assert "[important]" in content
        assert "[informational]" in content
        assert "Found a bug" in content
        assert "(session: abcdef12)" in content

    def test_appends_to_existing(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "observations.md").write_text("# Existing\n\n## 2026-03-08\n- old\n")

        obs = Observer(str(db_path), str(mem))
        obs.write_observations(
            [
                Observation(
                    referenced_time="2026-03-09T10:00:00Z",
                    priority="possible",
                    content="New thing",
                    source_session="sess1234-5678",
                ),
            ]
        )

        content = (mem / "observations.md").read_text()
        assert "# Existing" in content
        assert "## 2026-03-09" in content
        assert "New thing" in content

    def test_no_duplicate_date_headers(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "observations.md").write_text("## 2026-03-09\n- existing\n")

        obs = Observer(str(db_path), str(mem))
        obs.write_observations(
            [
                Observation(
                    referenced_time="2026-03-09T12:00:00Z",
                    priority="informational",
                    content="More stuff",
                    source_session="sess1234-5678",
                ),
            ]
        )

        content = (mem / "observations.md").read_text()
        assert content.count("## 2026-03-09") == 1

    def test_unknown_date(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "memory"
        obs = Observer(str(db_path), str(mem))
        obs.write_observations(
            [
                Observation(
                    referenced_time="",
                    priority="informational",
                    content="No date",
                    source_session="sess1234-5678",
                ),
            ]
        )

        content = (mem / "observations.md").read_text()
        assert "## unknown" in content

    def test_multiple_dates_sorted(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "memory"
        obs = Observer(str(db_path), str(mem))
        obs.write_observations(
            [
                Observation(
                    referenced_time="2026-03-10T10:00:00Z",
                    content="later",
                    source_session="sess1234-5678",
                ),
                Observation(
                    referenced_time="2026-03-08T10:00:00Z",
                    content="earlier",
                    source_session="sess1234-5678",
                ),
            ]
        )

        content = (mem / "observations.md").read_text()
        pos_08 = content.index("2026-03-08")
        pos_10 = content.index("2026-03-10")
        assert pos_08 < pos_10

    def test_creates_memory_dir(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "deep" / "nested" / "memory"
        obs = Observer(str(db_path), str(mem))
        obs.write_observations(
            [
                Observation(
                    referenced_time="2026-01-01T00:00:00Z",
                    content="test",
                    source_session="sess1234-5678",
                ),
            ]
        )
        assert (mem / "observations.md").exists()


class TestLoadState:
    def test_missing_file_returns_empty(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        obs = Observer(str(db_path), str(tmp_path / "mem"))
        assert obs.load_state() == {}

    def test_reads_existing_state(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "mem"
        mem.mkdir()
        (mem / "observer_state.json").write_text(json.dumps({"processed_sessions": ["a", "b"]}))
        obs = Observer(str(db_path), str(mem))
        state = obs.load_state()
        assert state["processed_sessions"] == ["a", "b"]


class TestSaveState:
    def test_writes_json(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "mem"
        obs = Observer(str(db_path), str(mem))
        obs.save_state({"processed_sessions": ["x"]})

        data = json.loads((mem / "observer_state.json").read_text())
        assert data["processed_sessions"] == ["x"]

    def test_creates_dir(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "new" / "dir"
        obs = Observer(str(db_path), str(mem))
        obs.save_state({"key": "val"})
        assert (mem / "observer_state.json").exists()


class TestRun:
    def test_end_to_end(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        mem = tmp_path / "memory"

        insert_test_node(
            conn,
            "root1",
            role="user",
            content=[{"type": "text", "text": "fix the crash"}],
            created_at="2026-03-09T10:00:00Z",
        )
        insert_test_node(
            conn,
            "reply1",
            role="assistant",
            content=[{"type": "text", "text": "I see the error"}],
            created_at="2026-03-09T10:01:00Z",
            parent_hash="root1",
            prompt_tokens=500,
            completion_tokens=100,
            cache_read=400,
        )

        obs = Observer(str(db_path), str(mem))
        results = obs.run()

        assert len(results) > 0
        assert (mem / "observations.md").exists()
        assert (mem / "observer_state.json").exists()

        # Running again should produce no new observations
        results2 = obs.run()
        assert len(results2) == 0

    def test_run_with_no_sessions(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "memory"

        obs = Observer(str(db_path), str(mem))
        results = obs.run()
        assert results == []

    def test_run_updates_watermark(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        mem = tmp_path / "memory"

        insert_test_node(
            conn, "root1", role="user", content=[{"type": "text", "text": "hello"}], created_at="2026-03-09T10:00:00Z"
        )

        obs = Observer(str(db_path), str(mem))
        obs.run()

        state = obs.load_state()
        assert "root1" in state["processed_sessions"]

    def test_run_rotates_stale_watermarks(self, tmp_path):
        """Processed sessions that no longer exist in the DB should be pruned."""
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        mem = tmp_path / "memory"
        mem.mkdir()

        insert_test_node(
            conn, "root1", role="user", content=[{"type": "text", "text": "hello"}], created_at="2026-03-09T10:00:00Z"
        )

        # Seed state with a session that no longer exists in DB
        (mem / "observer_state.json").write_text(json.dumps({"processed_sessions": ["deleted_session", "root1"]}))

        obs = Observer(str(db_path), str(mem))
        obs.run()

        state = obs.load_state()
        assert "root1" in state["processed_sessions"]
        assert "deleted_session" not in state["processed_sessions"]

    def test_run_no_observations_no_write(self, tmp_path):
        """When observe_session returns empty, observations.md shouldn't be created."""
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        mem = tmp_path / "memory"

        # Empty-role node produces no observations
        insert_test_node(conn, "root1", role="", content=[], created_at="2026-03-09T10:00:00Z")

        obs = Observer(str(db_path), str(mem))
        results = obs.run()
        assert results == []
        assert not (mem / "observations.md").exists()


# ── observe_session_inline() ──────────────────────────────────────────


class TestObserveSessionInline:
    def test_returns_dicts(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn,
            "root1",
            role="user",
            content=[{"type": "text", "text": "fix the crash"}],
            created_at="2026-03-09T10:00:00Z",
        )
        insert_test_node(
            conn,
            "reply1",
            role="assistant",
            content=[{"type": "text", "text": "I see the error"}],
            created_at="2026-03-09T10:01:00Z",
            parent_hash="root1",
            prompt_tokens=500,
            completion_tokens=100,
            cache_read=400,
        )

        results = observe_session_inline(str(db_path), "root1")
        assert isinstance(results, list)
        assert len(results) > 0
        assert all("priority" in r and "content" in r for r in results)
        goals = [r for r in results if "Session goal" in r["content"]]
        assert len(goals) == 1

    def test_latest_session_when_no_id(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn, "aaa", role="user", content=[{"type": "text", "text": "hello"}], created_at="2026-03-09T10:00:00Z"
        )
        insert_test_node(
            conn, "bbb", role="user", content=[{"type": "text", "text": "world"}], created_at="2026-03-09T11:00:00Z"
        )

        results = observe_session_inline(str(db_path))
        # Should use the latest session (bbb)
        assert isinstance(results, list)
        assert len(results) > 0

    def test_empty_db_returns_empty(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        results = observe_session_inline(str(db_path))
        assert results == []

    def test_includes_error_observations(self, tmp_path):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(
            conn,
            "root1",
            role="user",
            content=[{"type": "text", "text": "do something"}],
            created_at="2026-03-09T10:00:00Z",
        )
        insert_test_node(
            conn,
            "reply1",
            role="assistant",
            content=[{"type": "text", "text": "ValueError: bad"}],
            created_at="2026-03-09T10:01:00Z",
            parent_hash="root1",
        )

        results = observe_session_inline(str(db_path), "root1")
        errors = [r for r in results if "Exception" in r["content"]]
        assert len(errors) >= 1
