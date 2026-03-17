# tests/test_publisher.py
"""Tests for telemetry publisher."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SCRIPTS_PATH = Path(__file__).resolve().parent.parent / "scripts"
WRITER_PATH = Path(__file__).resolve().parent.parent / "docker" / "telemetry-consumer"


@pytest.fixture(autouse=True)
def _scripts_env():
    """Add scripts and telemetry-consumer dirs to sys.path."""
    sys.path.insert(0, str(SCRIPTS_PATH))
    sys.path.insert(0, str(WRITER_PATH))
    yield
    sys.path.remove(str(SCRIPTS_PATH))
    sys.path.remove(str(WRITER_PATH))
    for mod in ("publisher", "jsonl_writer"):
        sys.modules.pop(mod, None)


def test_jsonl_publisher_writes_event(tmp_path):
    """JSONLPublisher writes a fitness event as JSONL."""
    from publisher import JSONLPublisher

    pub = JSONLPublisher(str(tmp_path))
    event = {
        "type": "fitness",
        "key": "root-abc123",
        "node": {"fitness": {"turns": 100, "badges": 0}},
    }
    pub.publish(event)
    pub.close()

    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1
    line = json.loads(files[0].read_text().strip())
    assert line["type"] == "fitness"
    assert line["key"] == "root-abc123"


def test_jsonl_publisher_adds_timestamp(tmp_path):
    """Publisher adds occurred_at timestamp if not present."""
    from publisher import JSONLPublisher

    pub = JSONLPublisher(str(tmp_path))
    pub.publish({"type": "fitness", "key": "k1"})
    pub.close()

    line = json.loads(list(tmp_path.glob("*.jsonl"))[0].read_text().strip())
    assert "occurred_at" in line


def test_noop_publisher_does_nothing():
    """NoopPublisher accepts events without error."""
    from publisher import NoopPublisher

    pub = NoopPublisher()
    pub.publish({"type": "fitness"})
    pub.close()  # should not raise


def test_make_publisher_returns_jsonl_when_dir_set(tmp_path):
    """make_publisher returns JSONLPublisher when telemetry_dir is set."""
    from publisher import JSONLPublisher, make_publisher

    pub = make_publisher(telemetry_dir=str(tmp_path))
    assert isinstance(pub, JSONLPublisher)
    pub.close()


def test_make_publisher_returns_noop_when_no_dir():
    """make_publisher returns NoopPublisher when telemetry_dir is None."""
    from publisher import NoopPublisher, make_publisher

    pub = make_publisher(telemetry_dir=None)
    assert isinstance(pub, NoopPublisher)


def test_fanout_publisher_distributes_events():
    """FanoutPublisher sends each event to all inner publishers."""
    from publisher import FanoutPublisher

    events_a, events_b = [], []

    class RecorderA:
        def publish(self, event):
            events_a.append(event)

        def close(self):
            pass

    class RecorderB:
        def publish(self, event):
            events_b.append(event)

        def close(self):
            pass

    pub = FanoutPublisher([RecorderA(), RecorderB()])
    pub.publish({"type": "test", "n": 1})
    pub.publish({"type": "test", "n": 2})
    pub.close()

    assert len(events_a) == 2
    assert len(events_b) == 2
    assert events_a[0]["n"] == 1


def test_fanout_publisher_tolerates_failure():
    """One inner publisher failing does not stop others."""
    from publisher import FanoutPublisher

    received = []

    class Broken:
        def publish(self, event):
            raise RuntimeError("boom")

        def close(self):
            pass

    class Recorder:
        def publish(self, event):
            received.append(event)

        def close(self):
            pass

    pub = FanoutPublisher([Broken(), Recorder()])
    pub.publish({"type": "test"})
    pub.close()

    assert len(received) == 1


def test_fanout_publisher_close_propagates():
    """close() is called on all inner publishers."""
    from publisher import FanoutPublisher

    closed = []

    class Trackable:
        def __init__(self, name):
            self.name = name

        def publish(self, event):
            pass

        def close(self):
            closed.append(self.name)

    pub = FanoutPublisher([Trackable("a"), Trackable("b")])
    pub.close()

    assert closed == ["a", "b"]


def test_fanout_publisher_close_tolerates_failure():
    """close() continues to remaining publishers even if one raises."""
    from publisher import FanoutPublisher

    closed = []

    class BrokenClose:
        def publish(self, event):
            pass

        def close(self):
            raise RuntimeError("close boom")

    class Trackable:
        def __init__(self, name):
            self.name = name

        def publish(self, event):
            pass

        def close(self):
            closed.append(self.name)

    pub = FanoutPublisher([BrokenClose(), Trackable("a"), Trackable("b")])
    pub.close()

    assert closed == ["a", "b"]


def test_confluent_publisher_routes_by_schema():
    """ConfluentPublisher routes events to correct topics based on schema field."""
    mock_producer_cls = MagicMock()
    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=mock_producer_cls)}):
        # Re-import to pick up the mock
        import importlib

        import publisher

        importlib.reload(publisher)

        pub = publisher.ConfluentPublisher(
            bootstrap_servers="test:9092",
            api_key="key",
            api_secret="secret",
            topic_prefix="pokemon",
        )
        pub.publish({"schema": "tapes.node.v1", "type": "fitness"})
        pub.publish({"schema": "pokemon.game.v1", "event_type": "battle"})

        calls = mock_producer.produce.call_args_list
        assert calls[0].kwargs["topic"] == "pokemon.telemetry.raw"
        assert calls[1].kwargs["topic"] == "pokemon.game.events"

        pub.close()
        mock_producer.flush.assert_called_once_with(timeout=10)


def test_confluent_publisher_drops_unknown_schema(capsys):
    """ConfluentPublisher drops events with unknown schema and logs warning."""
    mock_producer_cls = MagicMock()
    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=mock_producer_cls)}):
        import importlib

        import publisher

        importlib.reload(publisher)

        pub = publisher.ConfluentPublisher(
            bootstrap_servers="test:9092",
            api_key="key",
            api_secret="secret",
            topic_prefix="pokemon",
        )
        pub.publish({"schema": "unknown.v1", "data": "test"})

        mock_producer.produce.assert_not_called()
        assert "unknown schema" in capsys.readouterr().out


def test_confluent_publisher_drops_missing_schema(capsys):
    """ConfluentPublisher drops events with no schema field."""
    mock_producer_cls = MagicMock()
    mock_producer = MagicMock()
    mock_producer_cls.return_value = mock_producer

    with patch.dict("sys.modules", {"confluent_kafka": MagicMock(Producer=mock_producer_cls)}):
        import importlib

        import publisher

        importlib.reload(publisher)

        pub = publisher.ConfluentPublisher(
            bootstrap_servers="test:9092",
            api_key="key",
            api_secret="secret",
            topic_prefix="pokemon",
        )
        pub.publish({"type": "fitness"})

        mock_producer.produce.assert_not_called()
        assert "unknown schema" in capsys.readouterr().out


def test_jsonl_publisher_writes_game_events(tmp_path):
    """JSONLPublisher writes game events to a separate directory."""
    from game_events import build_battle_event
    from publisher import JSONLPublisher

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    pub = JSONLPublisher(str(game_dir))

    event = build_battle_event(
        turn=1,
        player_hp=45,
        player_max_hp=50,
        enemy_hp=12,
        enemy_max_hp=35,
        action={"action": "fight", "move_index": 0},
    )
    pub.publish(event)
    pub.close()

    files = list(game_dir.glob("*.jsonl"))
    assert len(files) == 1
    line = json.loads(files[0].read_text().strip())
    assert line["schema"] == "pokemon.game.v1"
    assert line["event_type"] == "battle"
    assert line["data"]["player_hp"] == 45
