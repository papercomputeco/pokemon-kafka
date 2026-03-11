"""Telemetry consumer — reads tapes.node.v1 events from Kafka and displays them."""

import json
import os

from confluent_kafka import Consumer, KafkaError

TOPIC = os.environ.get("KAFKA_TOPIC", "agent.telemetry.raw")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "telemetry-consumer")
SINK_DIR = os.environ.get("SINK_DIR", "")


def format_event(data: dict) -> str:
    root = data.get("root_hash", "?")[:12]
    node = data.get("node", {})
    node_hash = node.get("hash", "?")[:12]
    parent = (node.get("parent_hash") or "")[:12] or "ROOT"
    bucket = node.get("bucket", {})
    role = bucket.get("role", "?")
    model = bucket.get("model", "?")
    usage = node.get("usage") or {}
    tokens_in = usage.get("input_tokens", 0)
    tokens_out = usage.get("output_tokens", 0)
    stop = node.get("stop_reason", "")

    return (
        f"[{root}] {role:<10} "
        f"hash={node_hash} parent={parent} "
        f"in={tokens_in} out={tokens_out} "
        f"model={model}"
        f"{f' stop={stop}' if stop else ''}"
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
    print("[consumer] Subscribed. Waiting for messages...", flush=True)

    sink = None
    if SINK_DIR:
        from jsonl_writer import JSONLWriter

        sink = JSONLWriter(SINK_DIR)
        print(f"[consumer] JSONL sink: {SINK_DIR}", flush=True)

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
                print(format_event(data), flush=True)
                if sink:
                    try:
                        sink.write(data)
                    except Exception as exc:
                        print(f"[consumer] Sink write failed: {exc}", flush=True)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                print(f"[consumer] Bad message: {exc}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        if sink:
            sink.close()
        consumer.close()


if __name__ == "__main__":
    main()
