"""Tests for alerts-consumer — Tapes integration."""

import json
import sqlite3
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# The consumer imports confluent_kafka which isn't installed in the test env.
# Provide a stub module so the import succeeds.
CONSUMER_PATH = Path(__file__).resolve().parent.parent / "docker" / "alerts-consumer"


@pytest.fixture(autouse=True)
def _consumer_env():
    """Add consumer dir to sys.path and stub confluent_kafka."""
    # Stub confluent_kafka
    kafka_mod = types.ModuleType("confluent_kafka")
    kafka_mod.Consumer = MagicMock
    kafka_mod.KafkaError = type("KafkaError", (), {"_PARTITION_EOF": -191})
    sys.modules["confluent_kafka"] = kafka_mod

    sys.path.insert(0, str(CONSUMER_PATH))
    yield
    sys.path.remove(str(CONSUMER_PATH))

    # Clean up so other tests aren't affected
    for name in ("consumer", "confluent_kafka"):
        sys.modules.pop(name, None)


def _import_consumer(tapes_db=None):
    """Import consumer module with TAPES_DB_PATH env var set."""
    env_patch = {"TAPES_DB_PATH": tapes_db} if tapes_db else {"TAPES_DB_PATH": ""}
    # Remove stale module to pick up new env
    sys.modules.pop("consumer", None)
    with patch.dict("os.environ", env_patch, clear=False):
        # Reload to re-read module-level env vars
        import importlib

        import consumer

        importlib.reload(consumer)
        return consumer


class TestFormatAlert:
    def test_formats_alert(self):
        consumer = _import_consumer()
        data = {
            "alert_type": "STUCK_LOOP",
            "root_hash": "abcdef123456789",
            "detail": "Agent stuck for 50 turns",
            "window_start": "2026-03-09T10:00:00Z",
            "window_end": "2026-03-09T10:05:00Z",
            "event_count": 5,
        }
        result = consumer.format_alert(data)
        assert "STUCK_LOOP" in result
        assert "abcdef12" in result
        assert "Agent stuck" in result


class TestTapesIntegration:
    def test_writes_to_tapes_db(self, tmp_path):
        db = tmp_path / "tapes.sqlite"
        consumer = _import_consumer(str(db))

        data = {
            "alert_type": "STUCK_LOOP",
            "root_hash": "abc123",
            "detail": "Stuck for 50 turns",
            "event_count": 5,
        }

        # Simulate what main() does after polling a message
        alert_text = consumer.format_alert(data)

        from tape_writer import TapeWriter

        writer = TapeWriter(str(db))
        writer.write_node(
            role="assistant",
            content_blocks=[{"type": "text", "text": alert_text}],
            agent_name="flink",
        )

        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT role, agent_name, content FROM nodes").fetchall()
        conn.close()

        assert len(rows) == 1
        assert rows[0][0] == "assistant"
        assert rows[0][1] == "flink"
        content = json.loads(rows[0][2])
        assert "STUCK_LOOP" in content[0]["text"]

    def test_no_tapes_db_configured(self):
        consumer = _import_consumer(None)
        # When TAPES_DB_PATH is empty/unset, TAPES_DB should be falsy
        assert not consumer.TAPES_DB
