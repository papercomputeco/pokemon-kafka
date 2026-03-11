"""Tests for DuckDB telemetry query script."""

import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    import duckdb  # noqa: F401
except ImportError:
    pytest.skip("duckdb not installed", allow_module_level=True)

SCRIPTS_PATH = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture(autouse=True)
def _scripts_env():
    """Add scripts dir to sys.path for query_telemetry import."""
    sys.path.insert(0, str(SCRIPTS_PATH))
    yield
    sys.path.remove(str(SCRIPTS_PATH))
    sys.modules.pop("query_telemetry", None)


@pytest.fixture
def telemetry_dir(tmp_path):
    """Create a temp dir with sample JSONL files."""
    events = [
        {
            "schema": "tapes.node.v1",
            "root_hash": "conv-aaa",
            "occurred_at": "2026-03-10T12:00:00Z",
            "node": {
                "hash": "h1",
                "parent_hash": None,
                "bucket": {"role": "user", "model": None, "provider": None},
                "usage": {"input_tokens": 100, "output_tokens": 0},
                "stop_reason": None,
                "project": "pokemon-kafka",
            },
        },
        {
            "schema": "tapes.node.v1",
            "root_hash": "conv-aaa",
            "occurred_at": "2026-03-10T12:01:00Z",
            "node": {
                "hash": "h2",
                "parent_hash": "h1",
                "bucket": {"role": "assistant", "model": "claude-sonnet-4-20250514", "provider": "anthropic"},
                "usage": {"input_tokens": 100, "output_tokens": 250},
                "stop_reason": "end_turn",
                "project": "pokemon-kafka",
            },
        },
    ]
    f = tmp_path / "2026-03-10.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return tmp_path


def test_create_connection_and_query(telemetry_dir):
    """create_connection creates a queryable 'events' view."""
    from query_telemetry import create_connection

    conn = create_connection(telemetry_dir)
    result = conn.execute("SELECT count(*) FROM events").fetchone()
    assert result[0] == 2


def test_summary_query(telemetry_dir):
    """DuckDB can compute token summary via events view."""
    from query_telemetry import create_connection

    conn = create_connection(telemetry_dir)
    result = conn.execute(
        """
        SELECT
            count(*) as events,
            sum(node.usage.input_tokens) as total_in,
            sum(node.usage.output_tokens) as total_out
        FROM events
        """
    ).fetchone()
    assert result[0] == 2
    assert result[1] == 200
    assert result[2] == 250


def test_filter_by_role(telemetry_dir):
    """DuckDB can filter by nested role field."""
    from query_telemetry import create_connection

    conn = create_connection(telemetry_dir)
    result = conn.execute("SELECT count(*) FROM events WHERE node.bucket.role = 'assistant'").fetchone()
    assert result[0] == 1


def test_main_help(telemetry_dir):
    """--help prints docstring and exits 0."""
    from query_telemetry import main

    with patch("sys.argv", ["query_telemetry.py", "--help"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0


def test_main_h_flag(telemetry_dir):
    """-h also prints help and exits 0."""
    from query_telemetry import main

    with patch("sys.argv", ["query_telemetry.py", "-h"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 0


def _mock_fetchdf():
    """Return a mock fetchdf that returns a mock DataFrame with to_string."""
    from unittest.mock import MagicMock

    mock_df = MagicMock()
    mock_df.to_string.return_value = "mocked output"
    return mock_df


def test_main_default_summary(telemetry_dir):
    """main() with data dir runs default summary query."""
    from query_telemetry import main

    with (
        patch("sys.argv", ["query_telemetry.py", str(telemetry_dir)]),
        patch("duckdb.DuckDBPyConnection.execute") as mock_exec,
    ):
        mock_exec.return_value.fetchdf = _mock_fetchdf
        main()


def test_main_custom_query(telemetry_dir):
    """main() with custom query arg."""
    from query_telemetry import main

    with (
        patch("sys.argv", ["query_telemetry.py", str(telemetry_dir), "SELECT count(*) FROM events"]),
        patch("duckdb.DuckDBPyConnection.execute") as mock_exec,
    ):
        mock_exec.return_value.fetchdf = _mock_fetchdf
        main()


def test_main_sessions_flag(telemetry_dir):
    """--sessions uses SESSIONS_QUERY."""
    from query_telemetry import main

    with (
        patch("sys.argv", ["query_telemetry.py", "--sessions", str(telemetry_dir)]),
        patch("duckdb.DuckDBPyConnection.execute") as mock_exec,
    ):
        mock_exec.return_value.fetchdf = _mock_fetchdf
        main()


def test_main_missing_dir():
    """main() with nonexistent dir exits 1."""
    from query_telemetry import main

    with patch("sys.argv", ["query_telemetry.py", "/nonexistent/path"]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1


def test_main_no_jsonl_files(tmp_path):
    """main() with dir but no .jsonl files exits 1."""
    from query_telemetry import main

    with patch("sys.argv", ["query_telemetry.py", str(tmp_path)]):
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1


def test_main_interactive_eof(telemetry_dir):
    """Interactive mode exits on EOFError."""
    from query_telemetry import main

    with (
        patch("sys.argv", ["query_telemetry.py", "--interactive", str(telemetry_dir)]),
        patch("builtins.input", side_effect=EOFError),
    ):
        main()


def test_main_interactive_empty_line(telemetry_dir):
    """Interactive mode exits on empty line."""
    from query_telemetry import main

    with (
        patch("sys.argv", ["query_telemetry.py", "--interactive", str(telemetry_dir)]),
        patch("builtins.input", return_value=""),
    ):
        main()


def test_main_interactive_query_and_exit(telemetry_dir):
    """Interactive mode executes query then exits on empty."""
    from query_telemetry import main

    inputs = iter(["SELECT count(*) FROM events", ""])
    with (
        patch("sys.argv", ["query_telemetry.py", "--interactive", str(telemetry_dir)]),
        patch("builtins.input", side_effect=inputs),
        patch("duckdb.DuckDBPyConnection.execute") as mock_exec,
    ):
        mock_exec.return_value.fetchdf = _mock_fetchdf
        main()


def test_main_interactive_bad_query(telemetry_dir):
    """Interactive mode prints error on bad SQL."""
    from query_telemetry import main

    inputs = iter(["INVALID SQL QUERY", ""])

    call_count = {"n": 0}

    def mock_execute(self_or_sql, *args, **kwargs):
        from unittest.mock import MagicMock

        call_count["n"] += 1
        # First call is CREATE VIEW (from create_connection), let it work
        # Second call is the bad user query, raise
        if call_count["n"] <= 1:
            result = MagicMock()
            result.fetchdf = _mock_fetchdf
            return result
        raise Exception("Parser Error")

    with (
        patch("sys.argv", ["query_telemetry.py", "--interactive", str(telemetry_dir)]),
        patch("builtins.input", side_effect=inputs),
        patch("duckdb.DuckDBPyConnection.execute", mock_execute),
    ):
        main()  # should not raise


def test_main_interactive_keyboard_interrupt(telemetry_dir):
    """Interactive mode exits on KeyboardInterrupt."""
    from query_telemetry import main

    with (
        patch("sys.argv", ["query_telemetry.py", "--interactive", str(telemetry_dir)]),
        patch("builtins.input", side_effect=KeyboardInterrupt),
    ):
        main()


def test_dunder_main_guard(telemetry_dir):
    """if __name__ == '__main__': main()"""
    import query_telemetry as qt_mod

    with (
        patch("sys.argv", ["query_telemetry.py", str(telemetry_dir)]),
        patch("duckdb.DuckDBPyConnection.execute") as mock_exec,
    ):
        mock_exec.return_value.fetchdf = _mock_fetchdf
        runpy.run_path(str(Path(qt_mod.__file__).resolve()), run_name="__main__")
