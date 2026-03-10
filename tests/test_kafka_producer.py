"""Tests for kafka_producer.py — Merkle DAG construction and Kafka publishing."""

import hashlib
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from kafka_producer import MerkleNode, TelemetryProducer


class TestMerkleNode:
    """Test content-addressed node construction."""

    def test_hash_deterministic(self):
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
        int(node.hash, 16)

    def test_hash_matches_manual_sha256(self):
        node = MerkleNode(role="user", content="test", parent="root")
        expected = hashlib.sha256(b"user:test:root").hexdigest()
        assert node.hash == expected

    def test_to_dict_contains_all_fields(self):
        node = MerkleNode(
            role="tool_call", content="press_a", parent="abc123",
            session_id="sess-1", turn=5, tokens_in=100, tokens_out=50, latency_ms=200,
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


class TestEnsureKafkaClient:
    """Test lazy-loading of the Kafka client class."""

    def test_returns_existing_client_when_already_set(self):
        import kafka_producer
        original = kafka_producer.KafkaProducerClient
        try:
            sentinel = object()
            kafka_producer.KafkaProducerClient = sentinel
            result = kafka_producer._ensure_kafka_client()
            assert result is sentinel
        finally:
            kafka_producer.KafkaProducerClient = original

    def test_imports_confluent_kafka_producer(self):
        import kafka_producer
        original = kafka_producer.KafkaProducerClient
        try:
            kafka_producer.KafkaProducerClient = None
            mock_producer_class = MagicMock()
            mock_confluent = MagicMock()
            mock_confluent.Producer = mock_producer_class
            with patch.dict("sys.modules", {"confluent_kafka": mock_confluent}):
                result = kafka_producer._ensure_kafka_client()
            assert result is mock_producer_class
            assert kafka_producer.KafkaProducerClient is mock_producer_class
        finally:
            kafka_producer.KafkaProducerClient = original
