"""Tests for DuckDB telemetry query script."""

import json
import sys
from pathlib import Path

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
