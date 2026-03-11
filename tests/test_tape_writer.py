"""Tests for tape_writer.py — TapeWriter class."""

import sqlite3

from tape_reader import TapeReader
from tape_writer import TapeWriter


class TestEnsureSchema:
    def test_creates_table_if_missing(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        writer = TapeWriter(str(db))
        writer.ensure_schema()

        conn = sqlite3.connect(str(db))
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        conn.close()
        assert ("nodes",) in tables

    def test_idempotent(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        writer = TapeWriter(str(db))
        writer.ensure_schema()
        writer.ensure_schema()  # should not raise


class TestWriteNode:
    def test_inserts_node_returns_hash(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        writer = TapeWriter(str(db))

        h = writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "hello"}],
            agent_name="flink",
        )

        assert isinstance(h, str)
        assert len(h) == 64  # sha256 hex

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT * FROM nodes WHERE hash = ?", (h,)).fetchone()
        conn.close()
        assert row is not None
        assert row[1] == "assistant"  # role
        assert row[10] == "flink"  # agent_name

    def test_readable_by_tape_reader(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        writer = TapeWriter(str(db))

        h = writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "alert: STUCK_LOOP"}],
            agent_name="flink",
        )

        reader = TapeReader(str(db))
        sessions = reader.list_sessions()
        assert h in sessions

        session = reader.read_session(h)
        assert len(session.entries) == 1
        assert "STUCK_LOOP" in session.entries[0].text_content

    def test_with_parent(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        writer = TapeWriter(str(db))

        root = writer.write_node(
            role="user",
            content_blocks=[{"type": "text", "text": "start"}],
            agent_name="flink",
        )
        child = writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "response"}],
            parent_hash=root,
            agent_name="flink",
        )

        reader = TapeReader(str(db))
        session = reader.read_session(root)
        assert len(session.entries) == 2
        hashes = [e.session_id for e in session.entries]
        assert root in hashes
        assert child in hashes

    def test_content_addressable_hash(self, tmp_path):
        """Different timestamps produce different hashes even for same content."""
        db = tmp_path / "tapes.sqlite"
        writer = TapeWriter(str(db))

        h1 = writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "same"}],
        )
        h2 = writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "same"}],
        )
        # Hashes differ because timestamp differs
        assert h1 != h2

    def test_context_manager(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        with TapeWriter(str(db)) as writer:
            h = writer.write_node(
                role="assistant",
                content_blocks=[{"type": "text", "text": "ctx"}],
            )
            assert len(h) == 64

        # Connection closed after context exit
        assert writer._conn is None

        # Data persisted
        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT hash FROM nodes WHERE hash = ?", (h,)).fetchone()
        conn.close()
        assert row is not None

    def test_reuses_connection(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        writer = TapeWriter(str(db))

        writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "first"}],
        )
        conn1 = writer._conn

        writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "second"}],
        )
        conn2 = writer._conn

        assert conn1 is conn2
        writer.close()

    def test_close_and_reopen(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        writer = TapeWriter(str(db))

        writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "before close"}],
        )
        writer.close()
        assert writer._conn is None

        # Can write again after close (reopens connection)
        h = writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "after close"}],
        )
        assert len(h) == 64
        writer.close()

    def test_with_model(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        writer = TapeWriter(str(db))

        h = writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": "test"}],
            model="claude-sonnet-4-20250514",
        )

        conn = sqlite3.connect(str(db))
        row = conn.execute("SELECT model FROM nodes WHERE hash = ?", (h,)).fetchone()
        conn.close()
        assert row[0] == "claude-sonnet-4-20250514"
