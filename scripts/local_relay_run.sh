#!/usr/bin/env bash
# One local (Ollama) operator run on the pi harness, the way the dated benchmarks/ rows are made.
#
#   scripts/local_relay_run.sh <alias> [base-commit]     e.g. scripts/local_relay_run.sh qwen38-27b 2cd9240
#
# Creates ../pokemon-kafka-speedrun-pi-<alias> as a worktree off <base-commit> (default: the commit
# the 2026-08-15 runs used, so every model faces the same repo defects), seeds ROM + route1.state,
# starts a game-event-bridge container for it, samples GPU power for the whole run, launches pi
# with the guardrails extension and the operator mission, waits, and prints the bench_report row.
# Requires: `tapes serve` up (proxy :42345), Kafka up (docker compose), the <alias>-128k model
# created by scripts/local_models.py, and PI_CLI (found via fnm below).
set -euo pipefail

ALIAS="${1:?usage: local_relay_run.sh <alias> [base-commit]}"
BASE="${2:-2cd9240}"
TAG="${RUN_TAG:-$ALIAS}"                            # worktree/branch/bridge name; set RUN_TAG for a rerun
CTX_K="${CTX_K:-128}"
MODEL="${ALIAS}-${CTX_K}k"
BUDGET_S="${BUDGET_S:-10800}"                      # hard kill; the mission text says 2.5 h
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PARENT="$(dirname "$REPO")"
WT="$PARENT/pokemon-kafka-speedrun-pi-${TAG}"
SVC="game-event-bridge-pi-${TAG}"
OUT="${OUT_DIR:-$REPO/data/local_runs}"; mkdir -p "$OUT"
PROMPT="${PROMPT_FILE:-$REPO/docs/prompts/operator_prompt_v2.md}"
PI_CLI="${PI_CLI:-$(ls "$HOME"/.local/share/fnm/node-versions/*/installation/lib/node_modules/@mariozechner/pi-coding-agent/dist/cli.js | tail -1)}"

[ -f "$PROMPT" ] || { echo "missing mission prompt: $PROMPT" >&2; exit 2; }
# Gated tips (scripts/advisor.py promote) ride along with the mission; only what cleared the gate is in there.
TIPS="$REPO/docs/prompts/tips.md"
MISSION="$(cat "$PROMPT")"
if [ -s "$TIPS" ]; then MISSION="$MISSION

## Tips from past runs (each one proved lift on a fresh model before it was written here)
$(grep '^- ' "$TIPS")"; fi
curl -sf "http://127.0.0.1:11434/api/tags" | grep -q "\"${MODEL}" || { echo "model ${MODEL} not in Ollama — run local_models.py create ${ALIAS}" >&2; exit 2; }
nc -z 127.0.0.1 42345 || { echo "tapes proxy :42345 is down — start tapes serve" >&2; exit 2; }

echo "== worktree $WT @ $BASE"
if [ ! -d "$WT" ]; then
  git -C "$REPO" worktree add -b "speedrun/pi-${TAG}" "$WT" "$BASE" >/dev/null
fi
mkdir -p "$WT/rom" "$WT/demo-runs/states" "$WT/data/telemetry/game" "$WT/data/power"
ln -sf "$REPO/rom/pokemon_red.gb" "$WT/rom/pokemon_red.gb"
cp -n "$REPO/demo-runs/states/route1.state" "$WT/demo-runs/states/" 2>/dev/null || true
( cd "$WT" && uv sync --group dev >/dev/null 2>&1 )

echo "== kafka bridge $SVC"
COMPOSE="$OUT/compose.${TAG}.yml"
cat > "$COMPOSE" <<EOF
services:
  ${SVC}:
    build: docker/game-event-bridge
    depends_on: {kafka: {condition: service_healthy}}
    environment: {KAFKA_BOOTSTRAP_SERVERS: "kafka:29092", KAFKA_TOPIC: agent.game.events, TELEMETRY_DIR: /telemetry, POLL_MS: 500, FROM_BEGINNING: 1}
    volumes: ["${WT}/data/telemetry/game:/telemetry:ro"]
EOF
( cd "$REPO" && docker compose -f docker-compose.yml -f "$COMPOSE" up -d "$SVC" >/dev/null 2>&1 ) || echo "   (bridge not started — Kafka down? continuing without it)"

echo "== power sampler"
POWER_CSV="$WT/data/power/${TAG}.csv"
# exec the venv python directly so the pid we record is the sampler itself, not a uv wrapper
( cd "$REPO" && exec "$REPO/.venv/bin/python" scripts/power_sampler.py --out "$POWER_CSV" --interval 5 >"$OUT/${TAG}.power.log" 2>&1 ) &
echo $! > "$OUT/${TAG}.power.pid"

echo "== pi $MODEL (budget ${BUDGET_S}s) — log $OUT/${TAG}.pi.log"
START=$(date +%s)
( cd "$WT" && timeout "$BUDGET_S" node "$PI_CLI" -p --no-extensions \
    -e "$HOME/.pi/agent/extensions/tapes-gateway.ts" \
    -e "$REPO/scripts/pi-ext/guardrails.ts" \
    --model "$MODEL" "$MISSION" >"$OUT/${TAG}.pi.log" 2>&1 ) || echo "   pi exited rc=$?"
END=$(date +%s)
kill "$(cat "$OUT/${TAG}.power.pid")" 2>/dev/null || true
pkill -f "power_sampler.py --out $POWER_CSV" 2>/dev/null || true

echo "== done in $(( (END-START)/60 )) min; batons:"; ls "$WT"/data/relay/*/batons/ 2>/dev/null | sort -u | grep -v ':$' || echo "   none"
echo "== learnings:"; ls "$WT/docs/learnings/" 2>/dev/null || true
SESSION=$(ls -t "$HOME/.pi/agent/sessions/"*"speedrun-pi-${TAG}--"/*.jsonl 2>/dev/null | head -1 || true)
echo "== bench row (session $SESSION)"
[ -n "$SESSION" ] && ( cd "$REPO" && uv run python scripts/bench_report.py "$SESSION" --label "${TAG} (local, ${CTX_K}k)" \
    --rate-in "${RATE_IN:-0.14}" --rate-out "${RATE_OUT:-1.00}" --power-log "$POWER_CSV" --kwh-price 0.30 )
