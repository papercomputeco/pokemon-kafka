"""Alerts consumer — reads Flink anomaly alerts from Kafka and displays them.

When TAPES_DB_PATH is set, each alert is also written as a Tapes node so the
observational memory loop can pick it up.
"""

import json
import os

from confluent_kafka import Consumer, KafkaError

TOPIC = os.environ.get("KAFKA_TOPIC", "agent.telemetry.alerts")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "alerts-consumer")
TAPES_DB = os.environ.get("TAPES_DB_PATH")


def format_alert(data: dict) -> str:
    alert_type = data.get("alert_type", "UNKNOWN")
    root = data.get("root_hash", "?")[:12]
    detail = data.get("detail", "")[:200]
    window_start = data.get("window_start", "")
    window_end = data.get("window_end", "")
    count = data.get("event_count", 0)
    window = f" window=[{window_start} -> {window_end}]" if window_start else ""
    return f"*** ALERT [{alert_type}] conv={root} count={count}{window} | {detail}"


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

    tape_writer = None
    if TAPES_DB:
        from tape_writer import TapeWriter

        tape_writer = TapeWriter(TAPES_DB)
        print(f"[alerts] Tapes writer: {TAPES_DB}", flush=True)

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
                alert_text = format_alert(data)
                print(alert_text, flush=True)

                if tape_writer:
                    try:
                        tape_writer.write_node(
                            role="assistant",
                            content_blocks=[{"type": "text", "text": alert_text}],
                            agent_name="flink",
                        )
                    except Exception as exc:
                        print(f"[alerts] Tapes write failed: {exc}", flush=True)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                print(f"[alerts] Bad message: {exc}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        if tape_writer:
            tape_writer.close()
        consumer.close()


if __name__ == "__main__":
    main()
