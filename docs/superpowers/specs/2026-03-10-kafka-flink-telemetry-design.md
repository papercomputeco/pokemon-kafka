# Kafka + Flink Agent Telemetry Streaming

**Date:** 2026-03-10
**Status:** Approved

## Summary

Add real-time telemetry streaming to the Pokemon agent using Apache Kafka as the message bus and Apache Flink for anomaly detection. The live agent produces Merkle DAG nodes to Kafka as it plays. Flink detects stuck loops, token spikes, and oscillation patterns. Consumers display telemetry and alerts in the terminal.

All infrastructure runs locally via Docker Compose. The agent runs on the host.

## Decisions

- **Data source:** Live agent producing events during gameplay (not a replay simulator)
- **Anomaly detection:** Real Apache Flink via Docker (not a Python stand-in)
- **Event format:** Merkle DAG nodes with SHA-256 content-addressing (role + content + parent hash)
- **Architecture:** Sidecar producer module imported by agent.py

## Architecture

```
Host machine:
  agent.py → KafkaProducer (scripts/kafka_producer.py) → localhost:9092

Docker Compose:
  zookeeper → kafka (broker)
  kafka → flink-jobmanager + flink-taskmanager (anomaly detection SQL)
  kafka → telemetry-consumer (displays raw events)
  kafka → alerts-consumer (displays Flink alerts)
  flink → kafka (writes alerts to agent.telemetry.alerts topic)
```

## Kafka Topics

| Topic | Description |
|---|---|
| `agent.telemetry.raw` | Merkle DAG nodes from the agent. Every battle, overworld move, map change, log event. |
| `agent.telemetry.alerts` | Flink-generated alerts: stuck loops, token spikes, oscillation. |

## Merkle DAG Node Schema

```json
{
  "hash": "sha256(role + content + parent)",
  "parent": "hash of previous node",
  "role": "user | assistant | tool_call | tool_result",
  "content": "the actual payload",
  "model": "pokemon-agent-v0.1",
  "timestamp": "ISO-8601",
  "tokens_in": 0,
  "tokens_out": 0,
  "latency_ms": 0,
  "session_id": "pokemon-red-001",
  "turn": 1
}
```

## Component: kafka_producer.py

New file `scripts/kafka_producer.py`:

- Constructs Merkle DAG nodes: `hash = sha256(role + content + parent_hash)`
- Maintains chain state (previous hash)
- Publishes JSON-serialized nodes to `agent.telemetry.raw`
- Uses `confluent-kafka` Python client
- Graceful degradation: no-op if Kafka unavailable
- Config via env vars: `KAFKA_BOOTSTRAP_SERVERS` (default `localhost:9092`), `KAFKA_SESSION_ID` (auto-generated if unset)

## Component: Agent Integration

Minimal changes to `agent.py` — 5 hook points:

1. `log()` — every structured log event becomes a `role="tool_result"` node
2. `run_battle_turn()` — battle decision as `role="tool_call"` node
3. `run_overworld()` — overworld action as `role="tool_call"` node
4. `run()` start — session metadata as `role="user"` node
5. `run()` end — fitness summary as `role="assistant"` node

No changes to existing behavior. Producer calls are additive.

## Component: Docker Compose

Services in `docker-compose.yml`:

1. **zookeeper** — `confluentinc/cp-zookeeper`
2. **kafka** — `confluentinc/cp-kafka`, exposes `localhost:9092`, auto-creates topics
3. **flink-jobmanager** — `flink:1.18`, Flink master
4. **flink-taskmanager** — Flink worker
5. **flink-sql-client** — Submits anomaly detection SQL jobs on startup
6. **telemetry-consumer** — Python, reads `agent.telemetry.raw`, prints formatted events
7. **alerts-consumer** — Python, reads `agent.telemetry.alerts`, prints alerts

## Flink SQL Jobs

Stuck loop detection (tumbling 30s window, 3+ repeated tool_calls):
```sql
SELECT session_id, window_start, window_end, last_action, COUNT(*) AS action_count
FROM TABLE(TUMBLE(TABLE agent_telemetry_raw, DESCRIPTOR(event_time), INTERVAL '30' SECONDS))
WHERE role = 'tool_call'
GROUP BY session_id, window_start, window_end, last_action
HAVING COUNT(*) >= 3;
```

Token spike detection (sliding window, 2x rolling average):
```sql
SELECT session_id, turn, tokens_in, avg_tokens, tokens_in / avg_tokens AS spike_ratio
FROM (
  SELECT *, AVG(tokens_in) OVER (
    PARTITION BY session_id ORDER BY event_time
    ROWS BETWEEN 10 PRECEDING AND 1 PRECEDING
  ) AS avg_tokens
  FROM agent_telemetry_raw WHERE role = 'assistant'
)
WHERE tokens_in > avg_tokens * 2.0;
```

## Dependencies

New Python dependency: `confluent-kafka` (added to pyproject.toml as optional)

## File Changes

- **New:** `scripts/kafka_producer.py`
- **New:** `docker-compose.yml`
- **New:** `docker/telemetry-consumer/` (Dockerfile + consumer script)
- **New:** `docker/alerts-consumer/` (Dockerfile + consumer script)
- **New:** `docker/flink-sql/` (SQL init scripts)
- **Modified:** `scripts/agent.py` (import producer, 5 hook points)
- **Modified:** `pyproject.toml` (optional kafka dependency)
- **New:** `tests/test_kafka_producer.py`
