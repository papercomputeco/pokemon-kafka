"""Alerts consumer — reads Flink anomaly alerts from Kafka and displays them.

When MEMORY_DIR is set, each alert is also appended as an `[important]`
observation to <MEMORY_DIR>/observations.md, the same file the observational
memory loop maintains, so the agent surfaces Flink anomalies at session start.
"""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from confluent_kafka import Consumer, KafkaError

TOPIC = os.environ.get("KAFKA_TOPIC", "agent.telemetry.alerts")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "alerts-consumer")
MEMORY_DIR = os.environ.get("MEMORY_DIR")
ADVICE_INBOX_DIR = os.environ.get("ADVICE_INBOX_DIR")
ADVICE_TTL_SECONDS = int(os.environ.get("ADVICE_TTL_SECONDS", "600"))
# Decide-step knobs: a genome patch expires faster than a note (it should only
# steer a run that is in the alerted condition right now), and each alert type
# nudges the genome at most once per cooldown window.
PATCH_TTL_SECONDS = int(os.environ.get("PATCH_TTL_SECONDS", "300"))
PATCH_COOLDOWN_SECONDS = int(os.environ.get("PATCH_COOLDOWN_SECONDS", "600"))
# Healer race history (healer.py --state), mounted read-only when available.
HEALER_STATE_FILE = os.environ.get("HEALER_STATE_FILE")
HEALER_QUIET_SECONDS = int(os.environ.get("HEALER_QUIET_SECONDS", "900"))
# Cooldown state lives beside the advice it gates; .json keeps it outside the
# agent's *.jsonl inbox poll glob.
DECIDE_STATE_FILE = "decide_state.json"

# The decide step (issue #63): map Flink alert types to genome_patch advice.
# Rules are data (the healer.RULES idiom) so the table can migrate to a future
# pokemon-cassette `advise` surface unchanged. Values are absolute targets —
# the consumer cannot see the live genome, and pokemon.advice.v1 genome_patch
# carries a partial genome, not deltas. Each value is one decisive step from
# evolve.DEFAULT_PARAMS, already inside evolve.PARAM_BOUNDS (the container
# ships without evolve.py, so the values are inlined and the test suite
# cross-checks them against the real bounds); the agent re-clamps against its
# live genome on apply.
PATCH_RULES = {
    # Stuck loops: skip a wedged waypoint sooner (default 8, bounds 3-20,
    # halved) and reach farther for the skip (default 3, bounds 1-8, doubled).
    "STUCK_STREAK_SPIKE": {"stuck_threshold": 4, "waypoint_skip_distance": 6},
    "GAME_STUCK_LOOP": {"stuck_threshold": 4, "waypoint_skip_distance": 6},
    # Door stalls: walk away from re-triggering doors longer (default 8,
    # bounds 4-16, +50% — halfway to the cap, not pinned at it).
    "DOOR_STALL": {"door_cooldown": 12},
    # Deadlocks/wedges: restore a backtrack snapshot sooner (default 15,
    # bounds 8-30, down a third — decisive but above the floor).
    "POSITION_DEADLOCK": {"bt_restore_threshold": 10},
    "IN_PLACE_WEDGE": {"bt_restore_threshold": 10},
    # LOW_HP_GRIND / BATTLE_LOSS_STREAK are deliberately absent: no genome
    # knob heals resource exhaustion today, so they stay note-only rather
    # than inventing a healing behavior.
}


def format_alert(data: dict) -> str:
    alert_type = data.get("alert_type", "UNKNOWN")
    root = data.get("root_hash", "?")[:12]
    detail = data.get("detail", "")[:200]
    window_start = data.get("window_start", "")
    window_end = data.get("window_end", "")
    count = data.get("event_count", 0)
    window = f" window=[{window_start} -> {window_end}]" if window_start else ""
    return f"*** ALERT [{alert_type}] conv={root} count={count}{window} | {detail}"


def alert_observation(data: dict) -> dict:
    """Shape a Flink alert as an observation row for memory_writer."""
    alert_type = data.get("alert_type", "UNKNOWN")
    detail = data.get("detail", "")[:200]
    count = data.get("event_count", 0)
    content = f"Flink alert [{alert_type}]: {detail}".rstrip()
    if count:
        content += f" (count={count})"
    return {
        "referenced_time": data.get("window_end") or data.get("window_start", ""),
        "priority": "important",
        "content": content,
        "source_session": "flink",
    }


def advice_from_alert(data: dict, now: datetime | None = None) -> dict:
    """Shape a Flink alert as a pokemon.advice.v1 note for the agent's inbox.

    Deterministic id (alert type + content hash) so the agent's dedupe absorbs
    at-least-once redelivery; a short TTL keeps stale anomalies from steering
    a run that has already moved on.
    """
    now = now or datetime.now(timezone.utc)
    digest = hashlib.sha1(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    alert_type = data.get("alert_type", "UNKNOWN")
    detail = data.get("detail", "")[:200]
    return {
        "schema": "pokemon.advice.v1",
        "id": f"flink:{alert_type}:{digest}",
        "type": "note",
        "data": {"text": f"[{alert_type}] {detail}".rstrip()},
        "expires_at": (now + timedelta(seconds=ADVICE_TTL_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"flink:{alert_type}",
    }


def patch_advice_from_alert(data: dict, now: datetime | None = None) -> dict | None:
    """Shape a mapped alert as a pokemon.advice.v1 genome_patch; None when unmapped.

    Same deterministic-id discipline as the note (redelivery is absorbed by the
    agent's per-run dedupe), with a `genome` segment so the note and its patch
    for one alert carry distinct ids and both apply.
    """
    alert_type = data.get("alert_type", "UNKNOWN")
    patch = PATCH_RULES.get(alert_type)
    if patch is None:
        return None
    now = now or datetime.now(timezone.utc)
    digest = hashlib.sha1(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return {
        "schema": "pokemon.advice.v1",
        "id": f"flink:{alert_type}:genome:{digest}",
        "type": "genome_patch",
        "data": dict(patch),
        "expires_at": (now + timedelta(seconds=PATCH_TTL_SECONDS)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"flink:{alert_type}",
    }


def load_decide_state(path: str) -> dict:
    """Read the decide step's cooldown state; missing or corrupt means empty."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def save_decide_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


def patch_cooldown_active(state: dict, alert_type: str, now_ts: float) -> bool:
    """True while this alert type's last patch is younger than the cooldown window."""
    last = (state.get("last_patch_at") or {}).get(alert_type)
    return last is not None and (now_ts - float(last)) < PATCH_COOLDOWN_SECONDS


def healer_recently_raced(state_path: str | None, now_ts: float) -> bool:
    """True when the healer's state file shows a race inside the quiet window.

    This is the healer-race signal: healer.py records `last_race_at` in its
    state file (data/healer_state.json) after every race — end-of-run checks
    and the agent's in-run wedge heals alike. A recent race means freshly
    tuned knobs (or a race that just resolved), and our default-derived
    absolute targets must not stomp them. A race still in flight is also
    safe without a signal: the winner is applied *after* it finishes via
    apply_genome_live, which overwrites anything a patch nudged meanwhile —
    the healer always gets the final word. Missing/unreadable state fails
    open (no signal must never mute the feedback loop).
    """
    if not state_path:
        return False
    try:
        with open(state_path, encoding="utf-8") as fh:
            state = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    last = state.get("last_race_at")
    try:
        return last is not None and (now_ts - float(last)) < HEALER_QUIET_SECONDS
    except (TypeError, ValueError):
        return False


def pending_patch_in_inbox(inbox_dir: str, now: datetime | None = None) -> bool:
    """True when an unexpired genome_patch (ours, an operator's, or a future
    cassette's) is already waiting in advice.jsonl — one nudge at a time."""
    now = now or datetime.now(timezone.utc)
    path = os.path.join(inbox_dir, "advice.jsonl")
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return False
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict) or item.get("type") != "genome_patch":
            continue
        expires_at = item.get("expires_at")
        if not expires_at:
            return True  # never expires — an operator's explicit choice
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        except ValueError:
            continue  # unparseable expiry — the agent drops it, so can we
        if expiry > now:
            return True
    return False


def emit_patch_advice(inbox_dir: str, data: dict, now: datetime | None = None) -> dict | None:
    """The decide step: append a genome_patch for a mapped alert unless a guardrail vetoes.

    Guardrails, in order: per-alert-type cooldown (persisted in
    <inbox>/decide_state.json so restarts and at-least-once replays cannot
    burst-patch), the healer quiet window (see healer_recently_raced), and an
    unexpired patch already pending in the inbox. Returns the emitted advice,
    or None when the alert is unmapped or a guardrail fired.
    """
    now = now or datetime.now(timezone.utc)
    item = patch_advice_from_alert(data, now=now)
    if item is None:
        return None
    alert_type = data.get("alert_type", "UNKNOWN")
    now_ts = now.timestamp()
    state_path = os.path.join(inbox_dir, DECIDE_STATE_FILE)
    state = load_decide_state(state_path)
    if patch_cooldown_active(state, alert_type, now_ts):
        print(f"[alerts] decide: {alert_type} on cooldown — note only", flush=True)
        return None
    if healer_recently_raced(HEALER_STATE_FILE, now_ts):
        print(f"[alerts] decide: healer raced recently — deferring {alert_type} patch", flush=True)
        return None
    if pending_patch_in_inbox(inbox_dir, now=now):
        print(f"[alerts] decide: a genome_patch is already pending — deferring {alert_type}", flush=True)
        return None
    append_advice_line(inbox_dir, item)
    state.setdefault("last_patch_at", {})[alert_type] = now_ts
    save_decide_state(state_path, state)
    print(f"[alerts] decide: {alert_type} -> genome_patch {json.dumps(item['data'])}", flush=True)
    return item


def append_advice_line(inbox_dir: str, item: dict) -> None:
    """Append advice to <inbox_dir>/advice.jsonl, creating the inbox on first use."""
    os.makedirs(inbox_dir, exist_ok=True)
    path = os.path.join(inbox_dir, "advice.jsonl")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(item) + "\n")


def append_alert_line(memory_dir: str, data: dict) -> None:
    """Append the raw alert to <memory_dir>/alerts.jsonl for the viewer.

    The viewer merges this file into run feeds (REST) and live-streams appended
    lines to open Pokédex sessions, tagging them as anomaly entries.
    """
    path = os.path.join(memory_dir, "alerts.jsonl")
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(data) + "\n")


def main():
    print(f"[alerts] Connecting to {BOOTSTRAP}, topic={TOPIC}", flush=True)

    conf = {
        "bootstrap.servers": BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
    }

    consumer = Consumer(conf)
    consumer.subscribe([TOPIC])
    print("[alerts] Subscribed. Waiting for alerts...", flush=True)

    append_observations = None
    if MEMORY_DIR:
        from memory_writer import append_observations as _append

        append_observations = _append
        print(f"[alerts] Memory: {MEMORY_DIR}", flush=True)

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"[alerts] Error: {msg.error()}", flush=True)
                continue

            try:
                data = json.loads(msg.value().decode("utf-8"))
                print(format_alert(data), flush=True)

                if MEMORY_DIR:
                    try:
                        append_alert_line(MEMORY_DIR, data)
                    except Exception as exc:
                        print(f"[alerts] alerts.jsonl write failed: {exc}", flush=True)

                if ADVICE_INBOX_DIR:
                    try:
                        append_advice_line(ADVICE_INBOX_DIR, advice_from_alert(data))
                    except Exception as exc:
                        print(f"[alerts] advice write failed: {exc}", flush=True)
                    try:
                        emit_patch_advice(ADVICE_INBOX_DIR, data)
                    except Exception as exc:
                        print(f"[alerts] patch advice failed: {exc}", flush=True)

                if append_observations:
                    try:
                        append_observations(MEMORY_DIR, [alert_observation(data)], dedupe=True)
                    except Exception as exc:
                        print(f"[alerts] memory write failed: {exc}", flush=True)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                print(f"[alerts] Bad message: {exc}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
