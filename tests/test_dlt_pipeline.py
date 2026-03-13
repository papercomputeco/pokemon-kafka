"""Tests for dlt telemetry pipeline."""

import json
import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

dlt = pytest.importorskip("dlt")

SCRIPTS_PATH = Path(__file__).resolve().parent.parent / "scripts"


@pytest.fixture(autouse=True)
def _scripts_env():
    sys.path.insert(0, str(SCRIPTS_PATH))
    yield
    sys.path.remove(str(SCRIPTS_PATH))
    sys.modules.pop("dlt_pipeline", None)


@pytest.fixture
def sample_events():
    return [
        {
            "schema": "tapes.node.v1",
            "root_hash": "conv-aaa",
            "occurred_at": "2026-03-10T12:00:00Z",
            "node": {
                "hash": "h1",
                "parent_hash": None,
                "bucket": {"role": "user", "model": None, "provider": None},
                "usage": {"input_tokens": 100, "output_tokens": 0},
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
            },
        },
    ]


@pytest.fixture
def telemetry_dir(tmp_path, sample_events):
    f = tmp_path / "2026-03-10.jsonl"
    f.write_text("\n".join(json.dumps(e) for e in sample_events) + "\n")
    return tmp_path


def test_resource_yields_events(telemetry_dir, sample_events):
    """telemetry_events resource yields event dicts from JSONL files."""
    from dlt_pipeline import telemetry_events

    events = list(telemetry_events(data_dir=telemetry_dir))
    assert len(events) == len(sample_events)
    assert events[0]["root_hash"] == "conv-aaa"


def test_resource_empty_dir(tmp_path):
    """telemetry_events yields nothing for an empty directory."""
    from dlt_pipeline import telemetry_events

    events = list(telemetry_events(data_dir=tmp_path))
    assert events == []


def test_resource_missing_dir(tmp_path):
    """telemetry_events yields nothing when directory does not exist."""
    from dlt_pipeline import telemetry_events

    events = list(telemetry_events(data_dir=tmp_path / "nonexistent"))
    assert events == []


def test_resource_skips_blank_lines(tmp_path):
    """Blank lines in JSONL files are skipped."""
    from dlt_pipeline import telemetry_events

    event = {"schema": "tapes.node.v1", "occurred_at": "2026-03-10T12:00:00Z", "root_hash": "x"}
    f = tmp_path / "data.jsonl"
    f.write_text(json.dumps(event) + "\n\n\n")

    events = list(telemetry_events(data_dir=tmp_path))
    assert len(events) == 1


def test_create_pipeline_duckdb(tmp_path):
    """create_pipeline returns a dlt Pipeline for duckdb destination."""
    from dlt_pipeline import create_pipeline

    db_path = tmp_path / "test.duckdb"
    pipeline = create_pipeline(destination="duckdb", db_path=db_path)
    assert pipeline.pipeline_name == "pokemon_telemetry"
    assert pipeline.dataset_name == "telemetry"


def test_create_pipeline_non_duckdb(tmp_path):
    """create_pipeline with non-duckdb destination passes destination string through."""
    from dlt_pipeline import create_pipeline

    pipeline = create_pipeline(destination="snowflake", db_path=tmp_path / "unused.duckdb")
    assert pipeline.pipeline_name == "pokemon_telemetry"


def test_full_pipeline_loads_into_duckdb(telemetry_dir, tmp_path):
    """End-to-end: JSONL -> dlt -> DuckDB, then query the warehouse."""
    import duckdb as ddb
    from dlt_pipeline import create_pipeline, telemetry_events

    db_path = tmp_path / "test.duckdb"
    pipeline = create_pipeline(destination="duckdb", db_path=db_path)
    pipeline.run(telemetry_events(data_dir=telemetry_dir), table_name="events")

    conn = ddb.connect(str(db_path), read_only=True)
    count = conn.execute("SELECT count(*) FROM telemetry.events").fetchone()[0]
    assert count == 2
    conn.close()


def test_incremental_skips_duplicates(telemetry_dir, tmp_path):
    """Running the pipeline twice does not duplicate rows (merge on occurred_at)."""
    import duckdb as ddb
    from dlt_pipeline import create_pipeline, telemetry_events

    db_path = tmp_path / "test.duckdb"
    pipeline = create_pipeline(destination="duckdb", db_path=db_path)

    pipeline.run(telemetry_events(data_dir=telemetry_dir), table_name="events")
    pipeline.run(telemetry_events(data_dir=telemetry_dir), table_name="events")

    conn = ddb.connect(str(db_path), read_only=True)
    count = conn.execute("SELECT count(*) FROM telemetry.events").fetchone()[0]
    assert count == 2
    conn.close()


def test_main_cli(telemetry_dir, tmp_path):
    """CLI entry point runs without error."""
    from dlt_pipeline import main

    db_path = tmp_path / "cli.duckdb"
    with patch("sys.argv", ["dlt_pipeline.py", str(telemetry_dir), "--db-path", str(db_path)]):
        main()

    assert db_path.exists()


def test_dunder_main_guard(telemetry_dir, tmp_path):
    """if __name__ == '__main__': main()"""
    import dlt_pipeline as dp_mod

    db_path = tmp_path / "guard.duckdb"
    with patch("sys.argv", ["dlt_pipeline.py", str(telemetry_dir), "--db-path", str(db_path)]):
        runpy.run_path(str(Path(dp_mod.__file__).resolve()), run_name="__main__")


def test_import_error_handling():
    """When dlt is not importable, the script prints instructions and exits."""
    with patch.dict(sys.modules, {"dlt": None}):
        with pytest.raises(SystemExit) as exc:
            # Force reimport
            sys.modules.pop("dlt_pipeline", None)
            import importlib

            mod = importlib.import_module("dlt_pipeline")
            importlib.reload(mod)
        assert exc.value.code == 1
