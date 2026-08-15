"""Tests for alerts-consumer — observational-memory integration."""

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
    kafka_mod = types.ModuleType("confluent_kafka")
    kafka_mod.Consumer = MagicMock
    kafka_mod.KafkaError = type("KafkaError", (), {"_PARTITION_EOF": -191})
    sys.modules["confluent_kafka"] = kafka_mod

    sys.path.insert(0, str(CONSUMER_PATH))
    yield
    sys.path.remove(str(CONSUMER_PATH))

    for name in ("consumer", "confluent_kafka"):
        sys.modules.pop(name, None)


def _import_consumer(memory_dir=None):
    """Import the consumer module with MEMORY_DIR set."""
    env_patch = {"MEMORY_DIR": memory_dir} if memory_dir else {"MEMORY_DIR": ""}
    sys.modules.pop("consumer", None)
    with patch.dict("os.environ", env_patch, clear=False):
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


class TestAlertObservation:
    def test_shapes_full_alert(self):
        consumer = _import_consumer()
        obs = consumer.alert_observation(
            {
                "alert_type": "BATTLE_LOOP",
                "detail": "enemy_hp=12 player_hp=9",
                "event_count": 20,
                "window_end": "2026-06-26T10:05:00Z",
            }
        )
        assert obs["priority"] == "important"
        assert obs["source_session"] == "flink"
        assert obs["referenced_time"] == "2026-06-26T10:05:00Z"
        assert obs["content"] == "Flink alert [BATTLE_LOOP]: enemy_hp=12 player_hp=9 (count=20)"

    def test_falls_back_to_window_start_and_omits_zero_count(self):
        consumer = _import_consumer()
        obs = consumer.alert_observation(
            {"alert_type": "NO_PROGRESS", "detail": "", "window_start": "2026-06-26T09:00:00Z"}
        )
        assert obs["referenced_time"] == "2026-06-26T09:00:00Z"
        # empty detail trimmed, no count suffix
        assert obs["content"] == "Flink alert [NO_PROGRESS]:"


class TestMemoryIntegration:
    def test_alert_written_as_observation(self, tmp_path):
        consumer = _import_consumer(str(tmp_path))
        from memory_writer import append_observations

        data = {
            "alert_type": "POSITION_DEADLOCK",
            "detail": "map=12 pos=(5,31)",
            "event_count": 50,
            "window_end": "2026-06-26T10:00:00Z",
        }
        n = append_observations(str(tmp_path), [consumer.alert_observation(data)], dedupe=True)

        assert n == 1
        content = (tmp_path / "observations.md").read_text()
        assert "## 2026-06-26" in content
        assert "- [important] Flink alert [POSITION_DEADLOCK]: map=12 pos=(5,31) (count=50) (session: flink)" in content

    def test_no_memory_dir_configured(self):
        consumer = _import_consumer(None)
        assert not consumer.MEMORY_DIR


class TestAppendAlertLine:
    def test_appends_raw_alert_json(self, tmp_path):
        """Alerts land in alerts.jsonl so the viewer can merge and live-stream them."""
        import json

        consumer = _import_consumer(str(tmp_path))
        data = {"alert_type": "STUCK_LOOP", "detail": "map=51", "event_count": 3}
        consumer.append_alert_line(str(tmp_path), data)
        consumer.append_alert_line(str(tmp_path), {"alert_type": "NO_PROGRESS"})

        lines = (tmp_path / "alerts.jsonl").read_text().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0]) == data
        assert json.loads(lines[1])["alert_type"] == "NO_PROGRESS"


class TestAdviceSink:
    def test_advice_from_alert_shapes_note(self):
        from datetime import datetime, timezone

        consumer = _import_consumer()
        data = {"alert_type": "LOW_HP_GRIND", "detail": "player_hp=3/19", "event_count": 12}
        adv = consumer.advice_from_alert(data, now=datetime(2026, 8, 14, tzinfo=timezone.utc))
        assert adv["schema"] == "pokemon.advice.v1"
        assert adv["type"] == "note"
        assert adv["source"] == "flink:LOW_HP_GRIND"
        assert adv["id"].startswith("flink:LOW_HP_GRIND:")
        assert adv["data"]["text"] == "[LOW_HP_GRIND] player_hp=3/19"
        assert adv["expires_at"] == "2026-08-14T00:10:00Z"  # default 600s TTL

    def test_advice_id_is_deterministic_per_alert(self):
        consumer = _import_consumer()
        a = {"alert_type": "DOOR_STALL", "detail": "map=40"}
        assert consumer.advice_from_alert(a)["id"] == consumer.advice_from_alert(a)["id"]
        b = {"alert_type": "DOOR_STALL", "detail": "map=42"}
        assert consumer.advice_from_alert(a)["id"] != consumer.advice_from_alert(b)["id"]

    def test_append_advice_line_creates_dir_and_appends(self, tmp_path):
        import json

        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        consumer.append_advice_line(str(inbox), {"id": "x1"})
        consumer.append_advice_line(str(inbox), {"id": "x2"})
        lines = (inbox / "advice.jsonl").read_text().splitlines()
        assert [json.loads(ln)["id"] for ln in lines] == ["x1", "x2"]


def _now():
    from datetime import datetime, timezone

    return datetime(2026, 8, 14, tzinfo=timezone.utc)


class TestPatchRules:
    """The decide step's mapping table: alert type -> pre-clamped genome nudge."""

    def test_stuck_alerts_lower_stuck_threshold_and_raise_skip_distance(self):
        from evolve import DEFAULT_PARAMS

        consumer = _import_consumer()
        for alert_type in ("STUCK_STREAK_SPIKE", "GAME_STUCK_LOOP"):
            patch = consumer.PATCH_RULES[alert_type]
            assert set(patch) == {"stuck_threshold", "waypoint_skip_distance"}
            assert patch["stuck_threshold"] < DEFAULT_PARAMS["stuck_threshold"]
            assert patch["waypoint_skip_distance"] > DEFAULT_PARAMS["waypoint_skip_distance"]

    def test_door_stall_raises_door_cooldown(self):
        from evolve import DEFAULT_PARAMS

        consumer = _import_consumer()
        patch = consumer.PATCH_RULES["DOOR_STALL"]
        assert set(patch) == {"door_cooldown"}
        assert patch["door_cooldown"] > DEFAULT_PARAMS["door_cooldown"]

    def test_deadlock_alerts_lower_bt_restore_threshold(self):
        from evolve import DEFAULT_PARAMS

        consumer = _import_consumer()
        for alert_type in ("POSITION_DEADLOCK", "IN_PLACE_WEDGE"):
            patch = consumer.PATCH_RULES[alert_type]
            assert set(patch) == {"bt_restore_threshold"}
            assert patch["bt_restore_threshold"] < DEFAULT_PARAMS["bt_restore_threshold"]

    def test_exhaustion_alerts_have_no_patch_rule(self):
        """LOW_HP_GRIND / BATTLE_LOSS_STREAK have no healing knob today — note only."""
        consumer = _import_consumer()
        assert "LOW_HP_GRIND" not in consumer.PATCH_RULES
        assert "BATTLE_LOSS_STREAK" not in consumer.PATCH_RULES

    def test_all_rule_values_are_already_clamped(self):
        """Every emitted value must sit inside evolve's bounds — clamping is a no-op."""
        from evolve import DEFAULT_PARAMS, PARAM_BOUNDS, clamp_params

        consumer = _import_consumer()
        for alert_type, rule in consumer.PATCH_RULES.items():
            for key, value in rule.items():
                lo, hi, typ = PARAM_BOUNDS[key]
                assert lo <= value <= hi, f"{alert_type}.{key}={value} outside [{lo}, {hi}]"
                assert isinstance(value, typ)
            merged = clamp_params({**DEFAULT_PARAMS, **rule})
            assert {k: merged[k] for k in rule} == rule


class TestPatchAdvice:
    def test_mapped_alert_shapes_genome_patch(self):
        consumer = _import_consumer()
        data = {"alert_type": "GAME_STUCK_LOOP", "detail": "map=37 streak=20", "event_count": 4}
        adv = consumer.patch_advice_from_alert(data, now=_now())
        assert adv["schema"] == "pokemon.advice.v1"
        assert adv["type"] == "genome_patch"
        assert adv["source"] == "flink:GAME_STUCK_LOOP"
        assert adv["id"].startswith("flink:GAME_STUCK_LOOP:genome:")
        assert adv["data"] == consumer.PATCH_RULES["GAME_STUCK_LOOP"]

    def test_patch_ttl_is_short_and_set(self):
        consumer = _import_consumer()
        adv = consumer.patch_advice_from_alert({"alert_type": "DOOR_STALL", "detail": "map=40"}, now=_now())
        assert adv["expires_at"] == "2026-08-14T00:05:00Z"  # default 300s patch TTL
        assert consumer.PATCH_TTL_SECONDS <= consumer.ADVICE_TTL_SECONDS

    def test_unmapped_alert_returns_none_but_still_notes(self):
        consumer = _import_consumer()
        for alert_type in ("LOW_HP_GRIND", "BATTLE_LOSS_STREAK", "UNKNOWN_FUTURE"):
            data = {"alert_type": alert_type, "detail": "x"}
            assert consumer.patch_advice_from_alert(data, now=_now()) is None
            assert consumer.advice_from_alert(data, now=_now())["type"] == "note"

    def test_patch_id_distinct_from_note_id_for_same_alert(self):
        """The agent dedupes by id; the note and its patch must both apply."""
        consumer = _import_consumer()
        data = {"alert_type": "POSITION_DEADLOCK", "detail": "map=51 pos=(6,1)"}
        note = consumer.advice_from_alert(data, now=_now())
        patch = consumer.patch_advice_from_alert(data, now=_now())
        assert note["id"] != patch["id"]

    def test_patch_id_is_deterministic(self):
        consumer = _import_consumer()
        data = {"alert_type": "IN_PLACE_WEDGE", "detail": "map=51"}
        assert (
            consumer.patch_advice_from_alert(data, now=_now())["id"]
            == consumer.patch_advice_from_alert(data, now=_now())["id"]
        )


class TestDecideGuardrails:
    def _emit(self, consumer, inbox, alert_type="GAME_STUCK_LOOP", now=None, detail="map=37 streak=20"):
        return consumer.emit_patch_advice(str(inbox), {"alert_type": alert_type, "detail": detail}, now=now or _now())

    def _patch_lines(self, inbox):
        import json

        path = inbox / "advice.jsonl"
        if not path.exists():
            return []
        lines = [json.loads(ln) for ln in path.read_text().splitlines()]
        return [ln for ln in lines if ln.get("type") == "genome_patch"]

    def test_emit_appends_patch_and_records_cooldown(self, tmp_path):
        import json

        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        adv = self._emit(consumer, inbox)
        assert adv is not None
        assert [ln["id"] for ln in self._patch_lines(inbox)] == [adv["id"]]
        state = json.loads((inbox / "decide_state.json").read_text())
        assert state["last_patch_at"]["GAME_STUCK_LOOP"] == _now().timestamp()

    def test_cooldown_suppresses_repeat_for_same_alert_type(self, tmp_path):
        from datetime import timedelta

        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        assert self._emit(consumer, inbox) is not None
        # Inside the window, a different detail (new advice id) is still suppressed.
        inside = _now() + timedelta(seconds=consumer.PATCH_COOLDOWN_SECONDS - 1)
        assert self._emit(consumer, inbox, now=inside, detail="map=37 streak=40") is None
        assert len(self._patch_lines(inbox)) == 1

    def test_cooldown_expires_and_is_per_alert_type(self, tmp_path):
        from datetime import timedelta

        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        assert self._emit(consumer, inbox) is not None
        # A different alert type patches immediately... but the pending-patch
        # guard defers it while the first patch is unexpired, so age it out.
        after_ttl = _now() + timedelta(seconds=consumer.PATCH_TTL_SECONDS + 1)
        assert self._emit(consumer, inbox, alert_type="DOOR_STALL", now=after_ttl, detail="map=40") is not None
        # And the first type patches again once its cooldown lapses.
        after_cooldown = _now() + timedelta(seconds=consumer.PATCH_COOLDOWN_SECONDS + 400)
        assert self._emit(consumer, inbox, now=after_cooldown, detail="again") is not None
        assert len(self._patch_lines(inbox)) == 3

    def test_cooldown_state_survives_restart(self, tmp_path):
        """State lives in decide_state.json, so a consumer restart keeps the window."""
        from datetime import timedelta

        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        assert self._emit(consumer, inbox) is not None
        consumer2 = _import_consumer()  # fresh module = fresh process
        # Past the patch TTL (so the pending-patch guard is moot) but inside the
        # cooldown window: only the persisted decide_state can suppress this.
        inside = _now() + timedelta(seconds=consumer.PATCH_TTL_SECONDS + 50)
        assert self._emit(consumer2, inbox, now=inside, detail="other") is None

    def test_healer_recent_race_suppresses_patch(self, tmp_path, monkeypatch):
        import json

        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        healer_state = tmp_path / "healer_state.json"
        healer_state.write_text(json.dumps({"last_race_at": _now().timestamp() - 60}))
        monkeypatch.setattr(consumer, "HEALER_STATE_FILE", str(healer_state))
        assert self._emit(consumer, inbox) is None
        assert self._patch_lines(inbox) == []

    def test_healer_old_race_does_not_suppress(self, tmp_path, monkeypatch):
        import json

        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        healer_state = tmp_path / "healer_state.json"
        old = _now().timestamp() - consumer.HEALER_QUIET_SECONDS - 1
        healer_state.write_text(json.dumps({"last_race_at": old}))
        monkeypatch.setattr(consumer, "HEALER_STATE_FILE", str(healer_state))
        assert self._emit(consumer, inbox) is not None

    def test_healer_state_missing_or_unreadable_fails_open(self, tmp_path, monkeypatch):
        consumer = _import_consumer()
        monkeypatch.setattr(consumer, "HEALER_STATE_FILE", str(tmp_path / "nope.json"))
        assert self._emit(consumer, tmp_path / "inbox-a") is not None
        (tmp_path / "garbage.json").write_text("not json")
        monkeypatch.setattr(consumer, "HEALER_STATE_FILE", str(tmp_path / "garbage.json"))
        assert self._emit(consumer, tmp_path / "inbox-b") is not None

    def test_pending_unexpired_patch_in_inbox_defers(self, tmp_path):
        """An operator/cassette patch already waiting in the inbox blocks a new one."""
        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        consumer.append_advice_line(
            str(inbox),
            {
                "schema": "pokemon.advice.v1",
                "id": "operator:1",
                "type": "genome_patch",
                "data": {"door_cooldown": 10},
                "expires_at": "2026-08-14T00:10:00Z",  # unexpired at _now()
                "source": "operator",
            },
        )
        assert self._emit(consumer, inbox) is None
        assert len(self._patch_lines(inbox)) == 1

    def test_expired_pending_patch_and_notes_do_not_defer(self, tmp_path):
        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        consumer.append_advice_line(
            str(inbox),
            {
                "schema": "pokemon.advice.v1",
                "id": "operator:old",
                "type": "genome_patch",
                "data": {"door_cooldown": 10},
                "expires_at": "2026-08-13T00:00:00Z",  # expired at _now()
                "source": "operator",
            },
        )
        consumer.append_advice_line(str(inbox), consumer.advice_from_alert({"alert_type": "LOW_HP_GRIND"}))
        assert self._emit(consumer, inbox) is not None

    def test_unmapped_alert_emits_nothing(self, tmp_path):
        consumer = _import_consumer()
        inbox = tmp_path / "inbox"
        assert self._emit(consumer, inbox, alert_type="LOW_HP_GRIND", detail="hp=3/19") is None
        assert not (inbox / "advice.jsonl").exists()
