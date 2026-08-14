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
