# tests/test_historical_observer.py
"""Tests for Historical Observer -- cross-session pattern extraction via DuckDB."""

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


def test_observe_declining_fitness(tmp_path):
    """Detects declining fitness when scores drop over runs."""
    events = [
        {
            "schema": "tapes.node.v1",
            "type": "fitness",
            "root_hash": "run-001",
            "occurred_at": "2026-03-09T10:00:00Z",
            "fitness": {
                "turns": 100,
                "battles_won": 5,
                "maps_visited": 4,
                "final_map_id": 2,
                "badges": 1,
                "party_size": 3,
                "stuck_count": 3,
                "backtrack_restores": 0,
            },
            "params": {"stuck_threshold": 8},
        },
        {
            "schema": "tapes.node.v1",
            "type": "fitness",
            "root_hash": "run-002",
            "occurred_at": "2026-03-09T14:00:00Z",
            "fitness": {
                "turns": 200,
                "battles_won": 0,
                "maps_visited": 1,
                "final_map_id": 0,
                "badges": 0,
                "party_size": 1,
                "stuck_count": 20,
                "backtrack_restores": 5,
            },
            "params": {"stuck_threshold": 8},
        },
    ]
    f = tmp_path / "2026-03-09.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    from historical_observer import observe

    insights = observe(str(tmp_path))
    contents = " ".join(i["content"] for i in insights)
    assert "declining" in contents.lower()


def test_observe_increasing_stuck(tmp_path):
    """Detects increasing stuck count regression."""
    events = [
        {
            "schema": "tapes.node.v1",
            "type": "fitness",
            "root_hash": "run-001",
            "occurred_at": "2026-03-09T10:00:00Z",
            "fitness": {
                "turns": 100,
                "battles_won": 1,
                "maps_visited": 2,
                "final_map_id": 1,
                "badges": 0,
                "party_size": 1,
                "stuck_count": 2,
                "backtrack_restores": 0,
            },
        },
        {
            "schema": "tapes.node.v1",
            "type": "fitness",
            "root_hash": "run-002",
            "occurred_at": "2026-03-09T14:00:00Z",
            "fitness": {
                "turns": 100,
                "battles_won": 1,
                "maps_visited": 2,
                "final_map_id": 1,
                "badges": 0,
                "party_size": 1,
                "stuck_count": 15,
                "backtrack_restores": 0,
            },
        },
    ]
    f = tmp_path / "2026-03-09.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    from historical_observer import observe

    insights = observe(str(tmp_path))
    contents = " ".join(i["content"] for i in insights)
    assert "increasing" in contents.lower()


def test_extract_insights_malformed_jsonl(tmp_path):
    """Exception during count query returns empty list."""
    f = tmp_path / "bad.jsonl"
    f.write_text("not valid json\n")

    from historical_observer import observe

    insights = observe(str(tmp_path))
    assert insights == []


def test_extract_insights_no_fitness_events(tmp_path):
    """JSONL with non-fitness events returns empty list."""
    event = {"schema": "tapes.node.v1", "type": "not_fitness", "root_hash": "x"}
    f = tmp_path / "2026-03-09.jsonl"
    f.write_text(json.dumps(event) + "\n")

    from historical_observer import observe

    insights = observe(str(tmp_path))
    assert insights == []


def test_extract_insights_no_params(tmp_path):
    """Fitness events without params.stuck_threshold don't crash."""
    events = [
        {
            "schema": "tapes.node.v1",
            "type": "fitness",
            "root_hash": f"run-{i}",
            "occurred_at": f"2026-03-09T{10 + i}:00:00Z",
            "fitness": {
                "turns": 100,
                "battles_won": 1,
                "maps_visited": 2,
                "final_map_id": 1,
                "badges": 0,
                "party_size": 1,
                "stuck_count": 5,
                "backtrack_restores": 0,
            },
        }
        for i in range(2)
    ]
    f = tmp_path / "2026-03-09.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in events) + "\n")

    from historical_observer import observe

    # Should not raise — the except block at line 188 handles missing params
    insights = observe(str(tmp_path))
    assert isinstance(insights, list)


def test_main_dry_run(telemetry_dir):
    """--dry-run prints insights but does not write file."""
    from historical_observer import main

    with patch("sys.argv", ["historical_observer.py", str(telemetry_dir), "--dry-run"]):
        main()

    # Default output should NOT exist
    default_output = Path(".tapes/memory/historical_insights.md")
    assert not default_output.exists()


def test_main_writes_output(telemetry_dir, tmp_path):
    """main() writes insights to --output path."""
    from historical_observer import main

    output = tmp_path / "insights.md"
    with patch("sys.argv", ["historical_observer.py", str(telemetry_dir), "--output", str(output)]):
        main()

    assert output.exists()
    assert "Historical Insights" in output.read_text()


def test_main_no_insights(tmp_path):
    """main() with empty dir prints message and returns."""
    from historical_observer import main

    with patch("sys.argv", ["historical_observer.py", str(tmp_path)]):
        main()  # should not raise


def test_dunder_main_guard(telemetry_dir, tmp_path):
    """if __name__ == '__main__': main()"""
    import historical_observer as ho_mod

    output = tmp_path / "out.md"
    with patch("sys.argv", ["historical_observer.py", str(telemetry_dir), "--output", str(output)]):
        runpy.run_path(str(Path(ho_mod.__file__).resolve()), run_name="__main__")
