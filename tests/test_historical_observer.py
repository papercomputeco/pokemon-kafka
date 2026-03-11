# tests/test_historical_observer.py
"""Tests for Historical Observer -- cross-session pattern extraction via DuckDB."""

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
    sys.path.insert(0, str(SCRIPTS_PATH))
    yield
    sys.path.remove(str(SCRIPTS_PATH))
    sys.modules.pop("historical_observer", None)


@pytest.fixture
def telemetry_dir(tmp_path):
    """Create sample JSONL with multiple fitness events (simulating multiple runs)."""
    events = [
        {
            "schema": "tapes.node.v1",
            "type": "fitness",
            "root_hash": "run-001",
            "occurred_at": "2026-03-09T10:00:00Z",
            "fitness": {
                "turns": 200,
                "battles_won": 1,
                "maps_visited": 2,
                "final_map_id": 1,
                "badges": 0,
                "party_size": 1,
                "stuck_count": 15,
                "backtrack_restores": 2,
            },
            "params": {"stuck_threshold": 8},
        },
        {
            "schema": "tapes.node.v1",
            "type": "fitness",
            "root_hash": "run-002",
            "occurred_at": "2026-03-09T14:00:00Z",
            "fitness": {
                "turns": 180,
                "battles_won": 2,
                "maps_visited": 3,
                "final_map_id": 1,
                "badges": 0,
                "party_size": 2,
                "stuck_count": 8,
                "backtrack_restores": 1,
            },
            "params": {"stuck_threshold": 6},
        },
        {
            "schema": "tapes.node.v1",
            "type": "fitness",
            "root_hash": "run-003",
            "occurred_at": "2026-03-10T09:00:00Z",
            "fitness": {
                "turns": 150,
                "battles_won": 3,
                "maps_visited": 4,
                "final_map_id": 2,
                "badges": 1,
                "party_size": 3,
                "stuck_count": 3,
                "backtrack_restores": 0,
            },
            "params": {"stuck_threshold": 5},
        },
    ]
    for i, day in enumerate(["2026-03-09", "2026-03-09", "2026-03-10"]):
        path = tmp_path / f"{day}.jsonl"
        with open(path, "a") as f:
            f.write(json.dumps(events[i]) + "\n")
    return tmp_path


def test_observe_returns_insights(telemetry_dir):
    """observe() returns a list of insight dicts with priority and content."""
    from historical_observer import observe

    insights = observe(str(telemetry_dir))
    assert len(insights) > 0
    for insight in insights:
        assert "priority" in insight
        assert "content" in insight


def test_observe_detects_fitness_trend(telemetry_dir):
    """Detects improving fitness across sessions."""
    from historical_observer import observe

    insights = observe(str(telemetry_dir))
    contents = " ".join(i["content"] for i in insights)
    # Should mention improving trend (scores went up across 3 runs)
    assert "improv" in contents.lower() or "trend" in contents.lower()


def test_observe_reports_stuck_reduction(telemetry_dir):
    """Reports that stuck_count decreased over time."""
    from historical_observer import observe

    insights = observe(str(telemetry_dir))
    contents = " ".join(i["content"] for i in insights)
    assert "stuck" in contents.lower()


def test_observe_empty_dir(tmp_path):
    """Returns empty list when no JSONL files exist."""
    from historical_observer import observe

    insights = observe(str(tmp_path))
    assert insights == []


def test_write_insights(telemetry_dir, tmp_path):
    """write_insights writes markdown to the specified path."""
    from historical_observer import observe, write_insights

    insights = observe(str(telemetry_dir))
    output = tmp_path / "historical_insights.md"
    write_insights(insights, str(output))

    assert output.exists()
    text = output.read_text()
    assert "# Historical Insights" in text
    assert len(text.strip().split("\n")) > 1
