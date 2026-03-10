# Kafka + Flink Agent Telemetry Streaming Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real-time Kafka telemetry streaming and Flink anomaly detection to the live Pokemon agent.

**Architecture:** Sidecar `kafka_producer.py` module imported by `agent.py` constructs Merkle DAG nodes (SHA-256 chained) and publishes to Kafka. Docker Compose runs Kafka, Flink (real Apache Flink with SQL jobs), and Python consumers. Agent runs on host, connects to `localhost:9092`.

**Tech Stack:** Python 3.11+, confluent-kafka, Apache Kafka (Confluent images), Apache Flink 1.18, Docker Compose

**Spec:** `docs/superpowers/specs/2026-03-10-kafka-flink-telemetry-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `scripts/kafka_producer.py` | Merkle DAG node construction, Kafka publishing, chain state |
| `scripts/agent.py` | Modified: import producer, 5 hook points (init, log, battle, overworld, run end) |
| `pyproject.toml` | Modified: add optional `kafka` dependency group |
| `tests/test_kafka_producer.py` | Unit tests for producer (hashing, chaining, publish, graceful degradation) |
| `docker-compose.yml` | Kafka, Zookeeper, Flink, consumers |
| `docker/telemetry-consumer/Dockerfile` | Container for telemetry consumer |
| `docker/telemetry-consumer/consumer.py` | Reads `agent.telemetry.raw`, prints formatted events |
| `docker/alerts-consumer/Dockerfile` | Container for alerts consumer |
| `docker/alerts-consumer/consumer.py` | Reads `agent.telemetry.alerts`, prints alerts |
| `docker/flink-sql/init.sql` | Flink SQL table definitions + anomaly detection queries |
| `docker/flink-sql/submit-jobs.sh` | Script to submit SQL jobs to Flink SQL client |
| `.env.example` | Documents host agent env vars (KAFKA_BOOTSTRAP_SERVERS, KAFKA_SESSION_ID) |

---

## Chunk 1: Kafka Producer Module

### Task 1: Kafka Producer — Merkle DAG Hashing and Node Construction

**Files:**
- Create: `scripts/kafka_producer.py`
- Create: `tests/test_kafka_producer.py`

- [ ] **Step 1: Write failing tests for Merkle DAG hashing**

In `tests/test_kafka_producer.py`:

```python
"""Tests for kafka_producer.py — Merkle DAG construction and Kafka publishing."""

import hashlib
import json
from unittest.mock import MagicMock, patch

import pytest

from kafka_producer import MerkleNode, TelemetryProducer


class TestMerkleNode:
    """Test content-addressed node construction."""

    def test_hash_deterministic(self):
        """Same inputs produce same hash."""
        node1 = MerkleNode(role="user", content="hello", parent="abc")
        node2 = MerkleNode(role="user", content="hello", parent="abc")
        assert node1.hash == node2.hash

    def test_hash_changes_with_role(self):
        node1 = MerkleNode(role="user", content="hello", parent="abc")
        node2 = MerkleNode(role="assistant", content="hello", parent="abc")
        assert node1.hash != node2.hash

    def test_hash_changes_with_content(self):
        node1 = MerkleNode(role="user", content="hello", parent="abc")
        node2 = MerkleNode(role="user", content="world", parent="abc")
        assert node1.hash != node2.hash

    def test_hash_changes_with_parent(self):
        node1 = MerkleNode(role="user", content="hello", parent="abc")
        node2 = MerkleNode(role="user", content="hello", parent="def")
        assert node1.hash != node2.hash

    def test_hash_is_sha256_hex(self):
        node = MerkleNode(role="user", content="test", parent="")
        assert len(node.hash) == 64
        int(node.hash, 16)  # valid hex

    def test_hash_matches_manual_sha256(self):
        node = MerkleNode(role="user", content="test", parent="root")
        expected = hashlib.sha256(b"user:test:root").hexdigest()
        assert node.hash == expected

    def test_to_dict_contains_all_fields(self):
        node = MerkleNode(
            role="tool_call",
            content="press_a",
            parent="abc123",
            session_id="sess-1",
            turn=5,
            tokens_in=100,
            tokens_out=50,
            latency_ms=200,
        )
        d = node.to_dict()
        assert d["hash"] == node.hash
        assert d["parent"] == "abc123"
        assert d["role"] == "tool_call"
        assert d["content"] == "press_a"
        assert d["session_id"] == "sess-1"
        assert d["turn"] == 5
        assert d["tokens_in"] == 100
        assert d["tokens_out"] == 50
        assert d["latency_ms"] == 200
        assert "timestamp" in d
        assert d["model"] == "pokemon-agent-v0.1"

    def test_root_node_has_empty_parent(self):
        node = MerkleNode(role="user", content="start", parent="")
        assert node.parent == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_kafka_producer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'kafka_producer'`

- [ ] **Step 3: Implement MerkleNode**

Create `scripts/kafka_producer.py`:

```python
"""Kafka telemetry producer with Merkle DAG content-addressing.

Constructs SHA-256-chained nodes from agent events and publishes
them to Kafka. Degrades gracefully if Kafka is unavailable.
"""

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field


@dataclass
class MerkleNode:
    """A content-addressed telemetry node."""

    role: str
    content: str
    parent: str
    session_id: str = ""
    turn: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    model: str = "pokemon-agent-v0.1"
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()))
    hash: str = field(default="", init=False)

    def __post_init__(self):
        self.hash = hashlib.sha256(
            f"{self.role}:{self.content}:{self.parent}".encode()
        ).hexdigest()

    def to_dict(self) -> dict:
        return {
            "hash": self.hash,
            "parent": self.parent,
            "role": self.role,
            "content": self.content,
            "model": self.model,
            "timestamp": self.timestamp,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "latency_ms": self.latency_ms,
            "session_id": self.session_id,
            "turn": self.turn,
        }
```

- [ ] **Step 4: Run tests to verify MerkleNode tests pass**

Run: `uv run pytest tests/test_kafka_producer.py::TestMerkleNode -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/kafka_producer.py tests/test_kafka_producer.py
git commit -m "feat: add MerkleNode with SHA-256 content-addressing"
```

---

### Task 2: Kafka Producer — TelemetryProducer with Chain State and Publishing

**Files:**
- Modify: `scripts/kafka_producer.py`
- Modify: `tests/test_kafka_producer.py`

- [ ] **Step 1: Write failing tests for TelemetryProducer**

Append to `tests/test_kafka_producer.py`:

```python
class TestTelemetryProducer:
    """Test chain management and Kafka publishing."""

    def test_init_generates_session_id(self):
        producer = TelemetryProducer(enabled=False)
        assert len(producer.session_id) > 0

    def test_init_uses_provided_session_id(self):
        producer = TelemetryProducer(session_id="test-123", enabled=False)
        assert producer.session_id == "test-123"

    def test_publish_chains_nodes(self):
        producer = TelemetryProducer(enabled=False)
        node1 = producer.publish("user", "first")
        node2 = producer.publish("assistant", "second")
        assert node2.parent == node1.hash

    def test_publish_third_node_chains_to_second(self):
        producer = TelemetryProducer(enabled=False)
        producer.publish("user", "first")
        node2 = producer.publish("assistant", "second")
        node3 = producer.publish("tool_call", "third")
        assert node3.parent == node2.hash

    def test_publish_sets_session_id_on_node(self):
        producer = TelemetryProducer(session_id="sess-1", enabled=False)
        node = producer.publish("user", "hello")
        assert node.session_id == "sess-1"

    def test_publish_sets_turn(self):
        producer = TelemetryProducer(enabled=False)
        node = producer.publish("user", "hello", turn=42)
        assert node.turn == 42

    def test_publish_sets_token_fields(self):
        producer = TelemetryProducer(enabled=False)
        node = producer.publish("assistant", "resp", tokens_in=100, tokens_out=50, latency_ms=300)
        assert node.tokens_in == 100
        assert node.tokens_out == 50
        assert node.latency_ms == 300

    def test_publish_sends_to_kafka_when_enabled(self):
        mock_client = MagicMock()
        with patch("kafka_producer._ensure_kafka_client"):
            import kafka_producer
            kafka_producer.KafkaProducerClient = MagicMock(return_value=mock_client)
            producer = TelemetryProducer(bootstrap_servers="localhost:9092", enabled=True)
        producer.publish("user", "hello")
        mock_client.produce.assert_called_once()
        args, kwargs = mock_client.produce.call_args
        assert args[0] == "agent.telemetry.raw"
        payload = json.loads(kwargs["value"])
        assert payload["role"] == "user"

    def test_publish_calls_flush(self):
        mock_client = MagicMock()
        with patch("kafka_producer._ensure_kafka_client"):
            import kafka_producer
            kafka_producer.KafkaProducerClient = MagicMock(return_value=mock_client)
            producer = TelemetryProducer(bootstrap_servers="localhost:9092", enabled=True)
        producer.publish("user", "hello")
        mock_client.flush.assert_called()

    def test_publish_handles_mid_session_kafka_failure(self):
        """Kafka error during publish doesn't crash — node is still returned."""
        mock_client = MagicMock()
        mock_client.produce.side_effect = Exception("broker down")
        with patch("kafka_producer._ensure_kafka_client"):
            import kafka_producer
            kafka_producer.KafkaProducerClient = MagicMock(return_value=mock_client)
            producer = TelemetryProducer(bootstrap_servers="localhost:9092", enabled=True)
        node = producer.publish("user", "hello")
        assert node.role == "user"
        assert node.hash != ""

    def test_disabled_producer_still_returns_nodes(self):
        producer = TelemetryProducer(enabled=False)
        node = producer.publish("user", "hello")
        assert node.role == "user"
        assert node.hash != ""

    def test_graceful_degradation_on_kafka_init_error(self):
        """Producer falls back to disabled mode if Kafka connection fails at init."""
        with patch("kafka_producer._ensure_kafka_client", side_effect=Exception("connection refused")):
            producer = TelemetryProducer(bootstrap_servers="bad:9092", enabled=True)
        assert producer.enabled is False
        node = producer.publish("user", "hello")
        assert node.role == "user"

    def test_from_env_defaults(self):
        with patch.dict(os.environ, {"KAFKA_BOOTSTRAP_SERVERS": ""}, clear=False):
            producer = TelemetryProducer.from_env()
            assert producer.enabled is False

    def test_from_env_with_bootstrap_servers(self):
        with patch.dict(os.environ, {"KAFKA_BOOTSTRAP_SERVERS": "kafka:9092"}):
            with patch("kafka_producer._ensure_kafka_client"):
                import kafka_producer
                kafka_producer.KafkaProducerClient = MagicMock()
                producer = TelemetryProducer.from_env()
                assert producer.enabled is True

    def test_from_env_with_session_id(self):
        with patch.dict(os.environ, {"KAFKA_SESSION_ID": "my-session", "KAFKA_BOOTSTRAP_SERVERS": ""}, clear=False):
            producer = TelemetryProducer.from_env()
            assert producer.session_id == "my-session"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_kafka_producer.py::TestTelemetryProducer -v`
Expected: FAIL — `ImportError: cannot import name 'TelemetryProducer'`

- [ ] **Step 3: Implement TelemetryProducer**

Append to `scripts/kafka_producer.py`:

```python
# Lazy-loaded Kafka client class. Set at module level so tests can patch it directly.
KafkaProducerClient = None


def _ensure_kafka_client():
    """Load confluent_kafka.Producer into the module-level KafkaProducerClient."""
    global KafkaProducerClient
    if KafkaProducerClient is not None:
        return KafkaProducerClient
    from confluent_kafka import Producer as _Producer
    KafkaProducerClient = _Producer
    return KafkaProducerClient


class TelemetryProducer:
    """Manages Merkle DAG chain and publishes nodes to Kafka."""

    TOPIC = "agent.telemetry.raw"

    def __init__(
        self,
        bootstrap_servers: str = "",
        session_id: str = "",
        enabled: bool = False,
    ):
        self.session_id = session_id or str(uuid.uuid4())[:8]
        self.enabled = enabled
        self._last_hash = ""
        self._client = None

        if enabled and bootstrap_servers:
            try:
                _ensure_kafka_client()
                self._client = KafkaProducerClient({"bootstrap.servers": bootstrap_servers})
            except Exception as exc:
                print(f"[kafka] Failed to connect: {exc}. Telemetry disabled.")
                self.enabled = False
                self._client = None

    def publish(
        self,
        role: str,
        content: str,
        turn: int = 0,
        tokens_in: int = 0,
        tokens_out: int = 0,
        latency_ms: int = 0,
    ) -> MerkleNode:
        """Construct a node, chain it, optionally publish to Kafka. Returns the node."""
        node = MerkleNode(
            role=role,
            content=content,
            parent=self._last_hash,
            session_id=self.session_id,
            turn=turn,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        self._last_hash = node.hash

        if self.enabled and self._client is not None:
            try:
                self._client.produce(
                    self.TOPIC,
                    value=json.dumps(node.to_dict()).encode("utf-8"),
                    key=node.session_id.encode("utf-8"),
                )
                self._client.flush(timeout=1)
            except Exception as exc:
                print(f"[kafka] Publish error: {exc}")

        return node

    @classmethod
    def from_env(cls) -> "TelemetryProducer":
        """Create a producer from environment variables."""
        bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "")
        session_id = os.environ.get("KAFKA_SESSION_ID", "")
        enabled = bool(bootstrap)
        return cls(
            bootstrap_servers=bootstrap,
            session_id=session_id,
            enabled=enabled,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_kafka_producer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite to check no regressions**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/kafka_producer.py tests/test_kafka_producer.py
git commit -m "feat: add TelemetryProducer with Kafka publishing and graceful degradation"
```

---

### Task 3: Agent Integration — Wire Producer into agent.py

**Files:**
- Modify: `scripts/agent.py:424-500` (PokemonAgent.__init__)
- Modify: `scripts/agent.py:641-646` (log method)
- Modify: `scripts/agent.py:705-748` (run_battle_turn)
- Modify: `scripts/agent.py:750-883` (run_overworld)
- Modify: `scripts/agent.py:901-953` (run method)
- Modify: `pyproject.toml`

- [ ] **Step 1: Add optional kafka dependency to pyproject.toml**

Add the `kafka` key to the existing `[dependency-groups]` section in `pyproject.toml` (do NOT duplicate the `[dependency-groups]` header — add below the existing `dev` entry):

```toml
kafka = [
    "confluent-kafka",
]
```

- [ ] **Step 2: Add producer import and init to PokemonAgent.__init__**

At the top of `scripts/agent.py`, after the existing imports (around line 18), add:

```python
from kafka_producer import TelemetryProducer
```

In `PokemonAgent.__init__` (after line 500, after the evolve params block), add:

```python
        # Kafka telemetry producer
        self.telemetry = TelemetryProducer.from_env()
        if self.telemetry.enabled:
            print(f"[agent] Kafka telemetry enabled: {os.environ.get('KAFKA_BOOTSTRAP_SERVERS')}")
```

- [ ] **Step 3: Hook into log() method**

Replace the `log()` method at line 641-646 with this version (adds the telemetry publish line at the end):

```python
    def log(self, msg: str):
        """Structured log line for Tapes to capture."""
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line, flush=True)
        self.events.append(line)
        self.telemetry.publish("tool_result", msg, turn=self.turn_count)
```

- [ ] **Step 4: Hook into run_battle_turn()**

After line 714 (after the `self.log(...)` call in `run_battle_turn`), add:

```python
        self.telemetry.publish(
            "tool_call",
            json.dumps(action),
            turn=self.turn_count,
        )
```

- [ ] **Step 5: Hook into run_overworld()**

After line 883 (`self.last_overworld_action = action`), add:

```python
        self.telemetry.publish(
            "tool_call",
            json.dumps({"action": action, "map_id": state.map_id, "x": state.x, "y": state.y}),
            turn=self.turn_count,
        )
```

- [ ] **Step 6: Hook into run() — session start and end**

In `run()`, after line 903 (`self.log("Agent starting...")`), add:

```python
        self.telemetry.publish(
            "user",
            json.dumps({"rom": self.rom_path, "strategy": self.strategy_engine.tier, "max_turns": max_turns}),
            turn=0,
        )
```

After line 948 (`fitness = self.compute_fitness()`) and before `self.pyboy.stop()`, add:

```python
        self.telemetry.publish(
            "assistant",
            json.dumps(fitness),
            turn=self.turn_count,
        )
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS (existing tests mock PyBoy, producer will be disabled since no KAFKA_BOOTSTRAP_SERVERS env var)

- [ ] **Step 8: Commit**

```bash
git add scripts/agent.py pyproject.toml
git commit -m "feat: wire Kafka telemetry producer into agent loop"
```

---

## Chunk 2: Docker Compose Infrastructure

### Task 4: Docker Compose — Kafka and Zookeeper

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create docker-compose.yml with Kafka and Zookeeper**

```yaml
services:
  zookeeper:
    image: confluentinc/cp-zookeeper:7.6.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    ports:
      - "2181:2181"

  kafka:
    image: confluentinc/cp-kafka:7.6.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092,PLAINTEXT_INTERNAL://kafka:29092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT,PLAINTEXT_INTERNAL:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT_INTERNAL
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    healthcheck:
      test: ["CMD", "kafka-topics", "--bootstrap-server", "kafka:29092", "--list"]
      interval: 10s
      timeout: 5s
      retries: 5
```

- [ ] **Step 2: Test Kafka comes up**

Run: `docker compose up -d kafka`
Then: `docker compose logs kafka | tail -5`
Expected: Kafka broker started, listening on 9092

Run: `docker compose down -v`

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Docker Compose with Kafka and Zookeeper"
```

---

### Task 5: Docker Compose — Telemetry Consumer

**Files:**
- Create: `docker/telemetry-consumer/Dockerfile`
- Create: `docker/telemetry-consumer/consumer.py`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create consumer script**

Create `docker/telemetry-consumer/consumer.py`:

```python
"""Telemetry consumer — reads Merkle DAG nodes from Kafka and displays them."""

import json
import os
import sys
import time

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
```

- [ ] **Step 2: Create Dockerfile**

Create `docker/telemetry-consumer/Dockerfile`:

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir confluent-kafka
COPY consumer.py /app/consumer.py
WORKDIR /app
CMD ["python", "consumer.py"]
```

- [ ] **Step 3: Add service to docker-compose.yml**

Append to `docker-compose.yml` services:

```yaml
  telemetry-consumer:
    build: docker/telemetry-consumer
    depends_on:
      kafka:
        condition: service_healthy
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      KAFKA_TOPIC: agent.telemetry.raw
      KAFKA_GROUP_ID: telemetry-consumer
```

- [ ] **Step 4: Commit**

```bash
git add docker/telemetry-consumer/ docker-compose.yml
git commit -m "feat: add telemetry consumer container"
```

---

### Task 6: Docker Compose — Alerts Consumer

**Files:**
- Create: `docker/alerts-consumer/Dockerfile`
- Create: `docker/alerts-consumer/consumer.py`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create alerts consumer script**

Create `docker/alerts-consumer/consumer.py`:

```python
"""Alerts consumer — reads Flink anomaly alerts from Kafka and displays them."""

import json
import os
import sys

from confluent_kafka import Consumer, KafkaError

TOPIC = os.environ.get("KAFKA_TOPIC", "agent.telemetry.alerts")
BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
GROUP_ID = os.environ.get("KAFKA_GROUP_ID", "alerts-consumer")


def format_alert(data: dict) -> str:
    alert_type = data.get("alert_type", "UNKNOWN")
    session = data.get("session_id", "?")[:8]
    detail = data.get("detail", "")[:200]
    window_start = data.get("window_start", "")
    window_end = data.get("window_end", "")
    count = data.get("event_count", 0)
    window = f" window=[{window_start} -> {window_end}]" if window_start else ""
    return f"*** ALERT [{alert_type}] session={session} count={count}{window} | {detail}"


def main():
    print(f"[alerts] Connecting to {BOOTSTRAP}, topic={TOPIC}", flush=True)

    conf = {
        "bootstrap.servers": BOOTSTRAP,
        "group.id": GROUP_ID,
        "auto.offset.reset": "earliest",
    }

    consumer = Consumer(conf)
    consumer.subscribe([TOPIC])
    print(f"[alerts] Subscribed. Waiting for alerts...", flush=True)

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
            except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                print(f"[alerts] Bad message: {exc}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create Dockerfile**

Create `docker/alerts-consumer/Dockerfile`:

```dockerfile
FROM python:3.12-slim
RUN pip install --no-cache-dir confluent-kafka
COPY consumer.py /app/consumer.py
WORKDIR /app
CMD ["python", "consumer.py"]
```

- [ ] **Step 3: Add service to docker-compose.yml**

Append to `docker-compose.yml` services:

```yaml
  alerts-consumer:
    build: docker/alerts-consumer
    depends_on:
      kafka:
        condition: service_healthy
    environment:
      KAFKA_BOOTSTRAP_SERVERS: kafka:29092
      KAFKA_TOPIC: agent.telemetry.alerts
      KAFKA_GROUP_ID: alerts-consumer
```

- [ ] **Step 4: Commit**

```bash
git add docker/alerts-consumer/ docker-compose.yml
git commit -m "feat: add alerts consumer container"
```

---

## Chunk 3: Flink Anomaly Detection

### Task 7: Flink SQL Jobs and Docker Services

**Files:**
- Create: `docker/flink-sql/init.sql`
- Create: `docker/flink-sql/submit-jobs.sh`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Create Flink SQL init file**

Create `docker/flink-sql/init.sql`:

```sql
-- Source table: reads raw telemetry from Kafka
CREATE TABLE agent_telemetry_raw (
    `hash` STRING,
    `parent` STRING,
    `role` STRING,
    `content` STRING,
    `model` STRING,
    `timestamp` STRING,
    `tokens_in` INT,
    `tokens_out` INT,
    `latency_ms` INT,
    `session_id` STRING,
    `turn` INT,
    `event_time` AS TO_TIMESTAMP(`timestamp`),
    WATERMARK FOR `event_time` AS `event_time` - INTERVAL '5' SECONDS
) WITH (
    'connector' = 'kafka',
    'topic' = 'agent.telemetry.raw',
    'properties.bootstrap.servers' = 'kafka:29092',
    'properties.group.id' = 'flink-telemetry',
    'scan.startup.mode' = 'earliest-offset',
    'format' = 'json'
);

-- Sink table: writes alerts to Kafka
CREATE TABLE agent_telemetry_alerts (
    `alert_type` STRING,
    `session_id` STRING,
    `detail` STRING,
    `window_start` TIMESTAMP(3),
    `window_end` TIMESTAMP(3),
    `event_count` BIGINT
) WITH (
    'connector' = 'kafka',
    'topic' = 'agent.telemetry.alerts',
    'properties.bootstrap.servers' = 'kafka:29092',
    'format' = 'json'
);

-- Stuck loop detection: same tool_call content 3+ times in 30s window
INSERT INTO agent_telemetry_alerts
SELECT
    'STUCK_LOOP' AS alert_type,
    session_id,
    content AS detail,
    window_start,
    window_end,
    COUNT(*) AS event_count
FROM TABLE(
    TUMBLE(
        TABLE agent_telemetry_raw,
        DESCRIPTOR(event_time),
        INTERVAL '30' SECONDS
    )
)
WHERE role = 'tool_call'
GROUP BY session_id, content, window_start, window_end
HAVING COUNT(*) >= 3;

-- Token spike detection: tokens_in > 2x the average over a 2-minute tumbling window
-- Uses a tumbling window to compute per-session average, then filters rows that
-- exceed 2x the window average. This approximates the spec's rolling average approach.
INSERT INTO agent_telemetry_alerts
SELECT
    'TOKEN_SPIKE' AS alert_type,
    session_id,
    CONCAT('avg_tokens=', CAST(CAST(avg_tokens AS INT) AS STRING),
           ' max_tokens=', CAST(max_tokens AS STRING)) AS detail,
    window_start,
    window_end,
    cnt AS event_count
FROM (
    SELECT
        session_id,
        window_start,
        window_end,
        AVG(tokens_in) AS avg_tokens,
        MAX(tokens_in) AS max_tokens,
        COUNT(*) AS cnt
    FROM TABLE(
        TUMBLE(
            TABLE agent_telemetry_raw,
            DESCRIPTOR(event_time),
            INTERVAL '2' MINUTES
        )
    )
    WHERE role = 'assistant' AND tokens_in > 0
    GROUP BY session_id, window_start, window_end
)
WHERE max_tokens > avg_tokens * 2.0;
```

- [ ] **Step 2: Create job submission script**

Create `docker/flink-sql/submit-jobs.sh`:

```bash
#!/bin/bash
set -e

echo "[flink-sql] Waiting for Flink JobManager to be ready..."
until curl -sf http://flink-jobmanager:8081/overview > /dev/null 2>&1; do
    sleep 2
done

echo "[flink-sql] Waiting for Kafka to be ready..."
# Use bash /dev/tcp instead of nc (which isn't installed in flink image)
until bash -c "echo > /dev/tcp/kafka/29092" 2>/dev/null; do
    sleep 2
done

echo "[flink-sql] Submitting SQL jobs..."
/opt/flink/bin/sql-client.sh -f /opt/flink-sql/init.sql

echo "[flink-sql] Jobs submitted. Keeping container alive for logs..."
tail -f /dev/null
```

- [ ] **Step 3: Add Flink services to docker-compose.yml**

Append to `docker-compose.yml` services:

```yaml
  flink-jobmanager:
    image: flink:1.18
    ports:
      - "8081:8081"
    command: jobmanager
    volumes:
      - flink-lib:/opt/flink/lib-extra
    environment:
      FLINK_PROPERTIES: |
        jobmanager.rpc.address: flink-jobmanager

  flink-taskmanager:
    image: flink:1.18
    depends_on:
      - flink-jobmanager
    command: taskmanager
    volumes:
      - flink-lib:/opt/flink/lib-extra
    environment:
      FLINK_PROPERTIES: |
        jobmanager.rpc.address: flink-jobmanager
        taskmanager.numberOfTaskSlots: 4

  # Downloads the Kafka connector JAR required by Flink SQL.
  # The flink:1.18 image does NOT include it by default.
  flink-kafka-connector:
    image: flink:1.18
    volumes:
      - flink-lib:/opt/flink/lib
    entrypoint: ["/bin/bash", "-c"]
    command:
      - |
        echo "Downloading Flink Kafka connector..."
        curl -fSL https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/3.1.0-1.18/flink-sql-connector-kafka-3.1.0-1.18.jar \
          -o /opt/flink/lib/flink-sql-connector-kafka-3.1.0-1.18.jar
        echo "Done."

  flink-sql-client:
    image: flink:1.18
    depends_on:
      flink-jobmanager:
        condition: service_started
      flink-taskmanager:
        condition: service_started
      flink-kafka-connector:
        condition: service_completed_successfully
      kafka:
        condition: service_healthy
    volumes:
      - ./docker/flink-sql:/opt/flink-sql
      - flink-lib:/opt/flink/lib-extra
    command: ["/bin/bash", "/opt/flink-sql/submit-jobs.sh"]
    environment:
      FLINK_PROPERTIES: |
        jobmanager.rpc.address: flink-jobmanager

volumes:
  flink-lib:
```

**Important:** The `flink:1.18` image does NOT bundle the Kafka SQL connector. The `flink-kafka-connector` init container downloads `flink-sql-connector-kafka-3.1.0-1.18.jar` into a shared volume that all Flink services mount. The `flink-sql-client` waits for this download to complete before submitting jobs.

- [ ] **Step 4: Commit**

```bash
chmod +x docker/flink-sql/submit-jobs.sh
git add docker/flink-sql/ docker-compose.yml
git commit -m "feat: add Flink SQL anomaly detection jobs and Docker services"
```

---

### Task 8: Integration Test — End to End

**Files:**
- Create: `.env.example`
- Modify: `.gitignore`

- [ ] **Step 1: Create .env.example with host agent config**

Create `.env.example` to document the environment variables for running the agent on the host:

```bash
# Kafka broker address for the host agent.
# Docker containers use kafka:29092 (internal network).
# The host agent uses localhost:9092 (exposed port).
KAFKA_BOOTSTRAP_SERVERS=localhost:9092

# Optional: set a fixed session ID (auto-generated if unset)
# KAFKA_SESSION_ID=pokemon-red-001
```

- [ ] **Step 2: Add docker artifacts to .gitignore**

Append to `.gitignore`:

```
# Docker
docker-compose.override.yml
```

- [ ] **Step 2: Full stack smoke test**

Run:
```bash
docker compose up --build -d
docker compose logs -f telemetry-consumer &
```

In another terminal, run a quick Kafka publish test (no agent needed):
```bash
echo '{"hash":"test","parent":"","role":"user","content":"smoke test","model":"test","timestamp":"2026-03-10T00:00:00.000Z","tokens_in":0,"tokens_out":0,"latency_ms":0,"session_id":"smoke","turn":0}' | docker compose exec -T kafka kafka-console-producer --broker-list kafka:29092 --topic agent.telemetry.raw
```

Expected: telemetry-consumer prints the formatted message.

Run: `docker compose down -v`

- [ ] **Step 3: Commit**

```bash
git add .gitignore docker-compose.yml
git commit -m "feat: complete Docker Compose stack with Kafka, Flink, and consumers"
```

---

### Task 9: Update coverage config and verify full test suite

**Files:**
- Modify: `pyproject.toml` (coverage omit)

- [ ] **Step 1: Update coverage config to omit Kafka-dependent code if needed**

If `kafka_producer.py` causes coverage issues due to `confluent_kafka` import, add to `pyproject.toml` `[tool.coverage.run]` omit list. However, since the tests mock the import, this should not be needed. Verify:

Run: `uv run pytest --cov --cov-report=term-missing -v`
Expected: ALL PASS, 100% coverage maintained

- [ ] **Step 2: Commit if any changes needed**

```bash
git add pyproject.toml
git commit -m "chore: update coverage config for kafka producer"
```
