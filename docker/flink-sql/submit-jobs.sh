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
