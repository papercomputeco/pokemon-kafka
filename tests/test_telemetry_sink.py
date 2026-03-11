"""Tests for JSONL telemetry sink."""

import json
import sys
from pathlib import Path

import pytest

WRITER_PATH = Path(__file__).resolve().parent.parent / "docker" / "telemetry-consumer"


@pytest.fixture(autouse=True)
def _writer_env():
    """Add telemetry-consumer dir to sys.path for jsonl_writer import."""
    sys.path.insert(0, str(WRITER_PATH))
    yield
    sys.path.remove(str(WRITER_PATH))
    sys.modules.pop("jsonl_writer", None)


def test_write_creates_date_partitioned_file(tmp_path):
    """Writer creates YYYY-MM-DD.jsonl file and appends a valid JSON line."""
    import jsonl_writer

    writer = jsonl_writer.JSONLWriter(str(tmp_path))
    event = {
        "schema": "tapes.node.v1",
        "root_hash": "abc123",
        "occurred_at": "2026-03-10T12:00:00Z",
        "node": {"hash": "def456", "bucket": {"role": "assistant"}},
    }
    writer.write(event)
    writer.close()

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    assert files[0].suffix == ".jsonl"

    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 1
    assert json.loads(lines[0]) == event


def test_multiple_writes_append_to_same_file(tmp_path):
    import jsonl_writer

    writer = jsonl_writer.JSONLWriter(str(tmp_path))
    for i in range(3):
        writer.write({"index": i})
    writer.close()

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().strip().split("\n")
    assert len(lines) == 3
    for i, line in enumerate(lines):
        assert json.loads(line)["index"] == i


def test_close_is_idempotent(tmp_path):
    import jsonl_writer

    writer = jsonl_writer.JSONLWriter(str(tmp_path))
    writer.write({"x": 1})
    writer.close()
    writer.close()  # should not raise
