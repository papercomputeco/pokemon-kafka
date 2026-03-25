# scripts/publisher.py
"""Telemetry publisher — local-first event publishing.

Local-first complement to the tapes Kafka publisher. The tapes proxy
already ships a Kafka-backed Publisher for the cloud path; this module
provides a zero-infrastructure alternative that writes directly to
date-partitioned JSONL files on disk. Same event shape, no broker needed.

The local JSONL path lets us iterate on the learning loop (agent →
telemetry → Historical Observer → evolution) without cloud dependencies,
then graduate data to Kafka/Confluent Cloud when ready.

Four implementations:
- JSONLPublisher: writes events to date-partitioned JSONL files
- NoopPublisher: discards events (for runs without telemetry)
- ConfluentPublisher: publishes events to Confluent Cloud via confluent-kafka Producer
- FanoutPublisher: fans out to multiple backends with per-publisher fault isolation
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Publisher(Protocol):
    """Event publisher protocol — same shape as the tapes Kafka publisher."""

    def publish(self, event: dict) -> None: ...
    def close(self) -> None: ...


class JSONLPublisher:
    """Publishes events to date-partitioned JSONL files.

    Reuses the JSONLWriter from the telemetry-consumer for file handling.
    """

    def __init__(self, telemetry_dir: str):
        import sys

        writer_dir = str(Path(__file__).resolve().parent.parent / "docker" / "telemetry-consumer")
        if writer_dir not in sys.path:
            sys.path.insert(0, writer_dir)
        from jsonl_writer import JSONLWriter

        self._writer = JSONLWriter(telemetry_dir)

    def publish(self, event: dict) -> None:
        if "occurred_at" not in event:
            event = {
                **event,
                "occurred_at": datetime.now(timezone.utc).isoformat() + "Z",
            }
        self._writer.write(event)

    def close(self) -> None:
        self._writer.close()


class NoopPublisher:
    """Discards all events. Used when telemetry is disabled."""

    def publish(self, event: dict) -> None:
        pass

    def close(self) -> None:
        pass


# Schema → topic suffix mapping
_TOPIC_MAP: dict[str, str] = {
    "tapes.node.v1": "telemetry.raw",
    "pokemon.game.v1": "game.events",
}


class ConfluentPublisher:
    """Publishes events to Confluent Cloud via confluent-kafka Producer.

    Routes events to topics based on the ``schema`` field.
    Unknown schemas are logged and dropped.
    """

    def __init__(self, bootstrap_servers: str, api_key: str, api_secret: str, topic_prefix: str):
        from confluent_kafka import Producer

        self._topic_prefix = topic_prefix
        self._producer = Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "security.protocol": "SASL_SSL",
                "sasl.mechanisms": "PLAIN",
                "sasl.username": api_key,
                "sasl.password": api_secret,
            }
        )

    @staticmethod
    def _delivery_callback(err, msg):
        if err is not None:
            print(f"[confluent] delivery failed: {err}")

    def publish(self, event: dict) -> None:
        schema = event.get("schema", "")
        suffix = _TOPIC_MAP.get(schema)
        if suffix is None:
            print(f"[confluent] unknown schema {schema!r}, dropping event")
            return
        topic = f"{self._topic_prefix}.{suffix}"
        key = schema.encode("utf-8")
        value = json.dumps(event).encode("utf-8")
        self._producer.produce(topic=topic, key=key, value=value, callback=self._delivery_callback)
        self._producer.poll(0)  # Process delivery callbacks without blocking

    def close(self) -> None:
        self._producer.flush(timeout=10)


class FanoutPublisher:
    """Publishes events to multiple backends. One failing does not stop others."""

    def __init__(self, publishers: list[Publisher]):
        self._publishers = list(publishers)

    def publish(self, event: dict) -> None:
        for pub in self._publishers:
            try:
                pub.publish(event)
            except Exception as exc:
                print(f"[fanout] publisher {type(pub).__name__} failed: {exc}")

    def close(self) -> None:
        for pub in self._publishers:
            try:
                pub.close()
            except Exception as exc:
                print(f"[fanout] close {type(pub).__name__} failed: {exc}")


def make_publisher(telemetry_dir: str | None = None, config_path: Path | None = None) -> Publisher:
    """Factory: builds publisher stack from config.

    Always includes JSONLPublisher when telemetry_dir is set.
    Adds ConfluentPublisher when config enables it and confluent-kafka is installed.
    Returns FanoutPublisher if multiple backends, single publisher otherwise.
    """
    from config import load_config

    cfg = load_config(config_path)
    publishers: list[Publisher] = []

    if telemetry_dir:
        publishers.append(JSONLPublisher(telemetry_dir))

    confluent_cfg = cfg["telemetry"]["confluent"]
    if confluent_cfg["enabled"]:
        api_key = os.environ.get(confluent_cfg["api_key_env"], "")
        api_secret = os.environ.get(confluent_cfg["api_secret_env"], "")
        try:
            publishers.append(
                ConfluentPublisher(
                    bootstrap_servers=confluent_cfg["bootstrap_servers"],
                    api_key=api_key,
                    api_secret=api_secret,
                    topic_prefix=confluent_cfg["topic_prefix"],
                )
            )
        except Exception as exc:
            print(f"[publisher] confluent setup failed, continuing with JSONL only: {exc}")

    if not publishers:
        return NoopPublisher()
    if len(publishers) == 1:
        return publishers[0]
    return FanoutPublisher(publishers)
