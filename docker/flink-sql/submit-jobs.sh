#!/bin/bash
set -e

echo "[flink-sql] Waiting for Flink JobManager to be ready..."
until curl -sf http://flink-jobmanager:8081/overview > /dev/null 2>&1; do
    sleep 2
done

echo "[flink-sql] Waiting for Flink TaskManager to register..."
until curl -sf http://flink-jobmanager:8081/taskmanagers 2>/dev/null | grep -q '"id"'; do
    sleep 2
done
# Extra wait for dispatcher RPC to be fully ready
sleep 5

echo "[flink-sql] Waiting for Kafka to be ready..."
# Use bash /dev/tcp instead of nc (which isn't installed in flink image)
until bash -c "echo > /dev/tcp/kafka/29092" 2>/dev/null; do
    sleep 2
done

echo "[flink-sql] Submitting SQL jobs..."
# Override the config so the embedded SQL client connects to the remote JobManager
# instead of trying to start its own mini-cluster on localhost.
FLINK_CONF_DIR=$(mktemp -d)
cp /opt/flink/conf/* "$FLINK_CONF_DIR/" 2>/dev/null || true
cat > "$FLINK_CONF_DIR/flink-conf.yaml" <<EOF
jobmanager.rpc.address: flink-jobmanager
jobmanager.rpc.port: 6123
rest.address: flink-jobmanager
rest.port: 8081
execution.target: remote
EOF
FLINK_CONF_DIR="$FLINK_CONF_DIR" /opt/flink/bin/sql-client.sh -f /opt/flink-sql/init.sql

echo "[flink-sql] Jobs submitted. Keeping container alive for logs..."
tail -f /dev/null
