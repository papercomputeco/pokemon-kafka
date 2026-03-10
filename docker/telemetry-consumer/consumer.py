"""Telemetry consumer — reads Merkle DAG nodes from Kafka and displays them."""

import json
import os

from confluent_kafka import Consumer, KafkaError

TOPIC = os.environ.get("KAFKA_TOPIC", "agent.telemetry.raw")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "telemetry-consumer")


def format_node(data: dict) -> str:
    role = data.get("role", "?")
    turn = data.get("turn", "?")
    content = data.get("content", "")[:120]
    session = data.get("session_id", "?")[:8]
    node_hash = data.get("hash", "?")[:12]
    parent = data.get("parent", "")[:12] or "ROOT"
    tokens = f"in={data.get('tokens_in', 0)} out={data.get('tokens_out', 0)}"

    return (
        f"[{session}] turn={turn} {role:<12} "
        f"hash={node_hash} parent={parent} "
        f"{tokens} | {content}"
    )


def main():
    print(f"[consumer] Connecting to {BOOTSTRAP}, topic={TOPIC}", flush=True)

    conf = {
        "bootstrap.servers": BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
    }

    consumer = Consumer(conf)
    consumer.subscribe([TOPIC])
    print(f"[consumer] Subscribed. Waiting for messages...", flush=True)

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"[consumer] Error: {msg.error()}", flush=True)
                continue

            try:
                data = json.loads(msg.value().decode("utf-8"))
                print(format_node(data), flush=True)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                print(f"[consumer] Bad message: {exc}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
