#!/usr/bin/env bash
set -euo pipefail

cd /workspace

echo "[entrypoint] Installing dependencies..."
bash scripts/install.sh

export LD_LIBRARY_PATH="${HOME}/.nix-profile/lib:${LD_LIBRARY_PATH:-}"
export PATH="/usr/local/bin:${PATH}"

echo "[entrypoint] Starting Kafka..."
docker compose up -d kafka

echo "[entrypoint] Waiting for Kafka to be ready..."
until docker compose exec -T kafka kafka-topics --bootstrap-server kafka:29092 --list >/dev/null 2>&1; do
    sleep 2
done
echo "[entrypoint] Kafka ready."

echo "[entrypoint] Starting Tapes proxy..."
tapes serve proxy \
    --config-dir /workspace/.tapes \
    --sqlite /workspace/.tapes/tapes.sqlite \
    --kafka-brokers localhost:9092 \
    --kafka-topic agent.telemetry.raw &
TAPES_PID=$!

# Wait for proxy to accept connections
echo "[entrypoint] Waiting for Tapes proxy on :8080..."
until curl -sf http://localhost:8080 >/dev/null 2>&1 || kill -0 "$TAPES_PID" 2>/dev/null; do
    sleep 1
done
sleep 1

echo "[entrypoint] Starting remaining services..."
docker compose up -d

echo "[entrypoint] Launching agent..."
~/venv/bin/python3 scripts/agent.py rom/pokemon_red.gb --strategy heuristic --max-turns 500000
