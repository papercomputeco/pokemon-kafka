"""Tests for observe_cli.py."""

import json

from tape_helpers import create_test_db, insert_test_node
from observe_cli import main, detect_db_path, detect_memory_dir


class TestDetectPaths:
    def test_detect_db_path(self):
        path = detect_db_path()
        assert path.endswith(".tapes/tapes.sqlite")

    def test_detect_memory_dir(self):
        path = detect_memory_dir()
        assert path.endswith(".tapes/memory")


class TestMainDryRun:
    def test_dry_run_prints_observations(self, tmp_path, capsys):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "root1", role="user",
                         content=[{"type": "text", "text": "fix the bug"}],
                         created_at="2026-03-09T10:00:00Z")
        mem = tmp_path / "memory"

        main(["--db", str(db_path), "--memory-dir", str(mem), "--dry-run"])

        captured = capsys.readouterr()
        assert "fix the bug" in captured.out
        assert "observation(s) found" in captured.out
        # Dry run should not write files
        assert not (mem / "observations.md").exists()

    def test_dry_run_empty_db(self, tmp_path, capsys):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "memory"

        main(["--db", str(db_path), "--memory-dir", str(mem), "--dry-run"])

        captured = capsys.readouterr()
        assert "0 observation(s) found" in captured.out


class TestMainSession:
    def test_single_session(self, tmp_path, capsys):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "root1", role="user",
                         content=[{"type": "text", "text": "add tests"}],
                         created_at="2026-03-09T10:00:00Z")
        mem = tmp_path / "memory"

        main(["--db", str(db_path), "--memory-dir", str(mem), "--session", "root1"])

        captured = capsys.readouterr()
        assert "add tests" in captured.out
        assert "observation(s) found" in captured.out


class TestMainRun:
    def test_full_run(self, tmp_path, capsys):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "root1", role="user",
                         content=[{"type": "text", "text": "deploy the app"}],
                         created_at="2026-03-09T10:00:00Z")
        mem = tmp_path / "memory"

        main(["--db", str(db_path), "--memory-dir", str(mem)])

        captured = capsys.readouterr()
        assert "Wrote" in captured.out
        assert (mem / "observations.md").exists()
        assert (mem / "observer_state.json").exists()


class TestMainReset:
    def test_reset_clears_watermark(self, tmp_path, capsys):
        db_path = tmp_path / "tapes.sqlite"
        conn = create_test_db(db_path)
        insert_test_node(conn, "root1", role="user",
                         content=[{"type": "text", "text": "hello"}],
                         created_at="2026-03-09T10:00:00Z")
        mem = tmp_path / "memory"
        mem.mkdir()
        (mem / "observer_state.json").write_text(
            json.dumps({"processed_sessions": ["root1"]})
        )

        main(["--db", str(db_path), "--memory-dir", str(mem), "--reset"])

        captured = capsys.readouterr()
        assert "Watermark cleared" in captured.out
        # After reset, should reprocess
        assert "Wrote" in captured.out

    def test_reset_no_existing_state(self, tmp_path, capsys):
        db_path = tmp_path / "tapes.sqlite"
        create_test_db(db_path)
        mem = tmp_path / "memory"

        main(["--db", str(db_path), "--memory-dir", str(mem), "--reset"])

        captured = capsys.readouterr()
        # No state file to clear, but should not error
        assert "0 observation(s)" in captured.out or "Wrote" in captured.out
