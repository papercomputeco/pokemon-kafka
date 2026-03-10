# Tapes-Native Kafka + Flink Telemetry

**Date:** 2026-03-10
**Status:** Approved

## Summary

Re-architect the Kafka telemetry pipeline to use the Tapes proxy as the sole Kafka publisher. Tapes already captures every LLM conversation turn as Merkle DAG nodes. With PR #131 merged, `tapes serve proxy --kafka-brokers --kafka-topic` publishes `tapes.node.v1` events to Kafka after each persisted turn. This replaces the custom Python `kafka_producer.py` and agent.py hooks.

Flink and the consumer containers remain, updated for the Tapes event schema.

## Architecture

```
Host:
  agent.py → Tapes Proxy (Docker, port 8080) → SQLite + Kafka

Docker Compose:
  tapes-proxy (--kafka-brokers kafka:29092 --kafka-topic agent.telemetry.raw)
  zookeeper → kafka
  kafka → flink (anomaly detection)
  kafka → telemetry-consumer (displays raw events)
  kafka → alerts-consumer (displays Flink alerts)
  flink → kafka (agent.telemetry.alerts topic)
```

## Tapes Event Schema (tapes.node.v1)

Published by Tapes proxy to Kafka:

```json
{
  "schema": "tapes.node.v1",
  "root_hash": "conversation-root-hash",
  "occurred_at": "2026-03-10T12:00:00.123456789Z",
  "node": {
    "hash": "node-hash",
    "parent_hash": "parent-hash",
    "bucket": {
      "type": "message",
      "role": "user | assistant | tool",
      "content": [... content blocks ...],
      "model": "claude-sonnet-4-20250514",
      "provider": "anthropic",
      "agent_name": "claude"
    },
    "stop_reason": "end_turn",
    "usage": {
      "input_tokens": 100,
      "output_tokens": 50
    },
    "project": "pokemon-kafka"
  }
}
```

Kafka partition key: `root_hash` (all turns in a conversation land on the same partition).

## Changes from Previous Implementation

### Remove
- `scripts/kafka_producer.py` — redundant with Tapes publishing
- `tests/test_kafka_producer.py` — tests for removed module
- Agent.py telemetry hooks (import, init, 5 publish calls)
- `kafka` dependency group in `pyproject.toml`

### Keep
- Docker Compose infrastructure (Kafka, Zookeeper, Flink, consumers)
- Flink anomaly detection concept (stuck loops, token spikes)

### Add
- `tapes-proxy` service in Docker Compose

### Update
- Flink SQL tables for `tapes.node.v1` nested schema
- Consumer scripts for Tapes event format
- `.env.example` with Tapes proxy config

## Flink SQL

Source table uses nested ROW types matching the Tapes event envelope. The `content` array field is omitted (complex nested structure not needed for anomaly detection).

Stuck loop detection: 3+ assistant turns within a 30s tumbling window per conversation.

Token spike detection: max `input_tokens` exceeds 2x the window average over 2-minute tumbling windows.

## Docker Compose — Tapes Proxy Service

```yaml
tapes-proxy:
  image: ghcr.io/papercomputeco/tapes:latest
  command: >
    serve proxy
    --listen 0.0.0.0:8080
    --upstream ${ANTHROPIC_API_BASE:-https://api.anthropic.com}
    --kafka-brokers kafka:29092
    --kafka-topic agent.telemetry.raw
  ports:
    - "8080:8080"
  depends_on:
    kafka:
      condition: service_healthy
```

The agent on the host sets its API base URL to `http://localhost:8080` to route through the proxy.
