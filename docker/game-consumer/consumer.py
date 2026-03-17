"""Game event consumer — reads pokemon.game.v1 events from Kafka."""

import json
import os

from confluent_kafka import Consumer, KafkaError

TOPIC = os.environ.get("KAFKA_TOPIC", "agent.game.events")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "game-consumer")
SINK_DIR = os.environ.get("SINK_DIR", "")


def format_event(data: dict) -> str:
    event_type = data.get("event_type", "?")
    turn = data.get("turn", "?")
    inner = data.get("data", {})

    if event_type == "battle":
        php = inner.get("player_hp", "?")
        phpm = inner.get("player_max_hp", "?")
        ehp = inner.get("enemy_hp", "?")
        ehpm = inner.get("enemy_max_hp", "?")
        return f"[turn {turn}] BATTLE php={php}/{phpm} ehp={ehp}/{ehpm}"
    elif event_type == "map_change":
        prev = inner.get("prev_map", "?")
        new = inner.get("new_map", "?")
        return f"[turn {turn}] MAP {prev}->{new}"
    elif event_type == "stuck":
        streak = inner.get("streak", "?")
        return f"[turn {turn}] STUCK streak={streak}"
    elif event_type == "milestone":
        return f"[turn {turn}] MILESTONE {inner.get('description', '')}"
    elif event_type == "overworld":
        pos = inner.get("position", {})
        return f"[turn {turn}] OW map={inner.get('map_id')} ({pos.get('x')},{pos.get('y')})"
    elif event_type == "session":
        return f"[turn {turn}] SESSION {inner.get('phase', '?')}"
    return f"[turn {turn}] {event_type}: {json.dumps(inner)[:120]}"


def main():
    print(f"[game] Connecting to {BOOTSTRAP}, topic={TOPIC}", flush=True)

    conf = {
        "bootstrap.servers": BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
    }

    consumer = Consumer(conf)
    consumer.subscribe([TOPIC])
    print("[game] Subscribed. Waiting for game events...", flush=True)

    sink = None
    if SINK_DIR:
        from jsonl_writer import JSONLWriter

        sink = JSONLWriter(SINK_DIR)
        print(f"[game] JSONL sink: {SINK_DIR}", flush=True)

    try:
        while True:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                print(f"[game] Error: {msg.error()}", flush=True)
                continue

            try:
                data = json.loads(msg.value().decode("utf-8"))
                print(format_event(data), flush=True)
                if sink:
                    try:
                        sink.write(data)
                    except Exception as exc:
                        print(f"[game] Sink write failed: {exc}", flush=True)
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                print(f"[game] Bad message: {exc}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        if sink:
            sink.close()
        consumer.close()


if __name__ == "__main__":
    main()
