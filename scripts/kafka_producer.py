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

    def __init__(self, bootstrap_servers: str = "", session_id: str = "", enabled: bool = False):
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

    def publish(self, role: str, content: str, turn: int = 0, tokens_in: int = 0, tokens_out: int = 0, latency_ms: int = 0) -> MerkleNode:
        """Construct a node, chain it, optionally publish to Kafka. Returns the node."""
        node = MerkleNode(
            role=role, content=content, parent=self._last_hash,
            session_id=self.session_id, turn=turn,
            tokens_in=tokens_in, tokens_out=tokens_out, latency_ms=latency_ms,
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
        return cls(bootstrap_servers=bootstrap, session_id=session_id, enabled=enabled)
