#!/usr/bin/env bash
# One operator run on the CLAUDE CODE harness (the "harness axis" — Claude models on the Max sub),
# the sibling of scripts/local_relay_run.sh. Same worktree/seed/mission/bridge; no pi guardrails
# (Claude Code has its own compaction and permission model), no power sampler (cloud).
#
#   scripts/claude_relay_run.sh <model> [base-commit]      e.g. scripts/claude_relay_run.sh claude-haiku-4-5-20251001 main
#   RUN_TAG=haiku-cc-r2 ... for a rerun; ASSIST=none|tips (consult is a pi tool; not available here)
#
# Captured to tapes via `tapesctl start --tapes-url http://localhost:8082 claude` (the ingest port; the
# read port 404s — see memory). ANTHROPIC_API_KEY is unset for the run so the claude.ai login (Max) is
# used, per the project preference; set CLAUDE_USE_API_KEY=1 to keep it.
set -euo pipefail

MODEL="${1:?usage: claude_relay_run.sh <model> [base-commit]}"
BASE="${2:-main}"
SHORT="$(printf '%s' "$MODEL" | sed -E 's/^claude-//; s/-[0-9]{8}$//; s/[^a-z0-9]+/-/g')"
TAG="${RUN_TAG:-${SHORT}-cc}"
BUDGET_S="${BUDGET_S:-10800}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PARENT="$(dirname "$REPO")"
WT="$PARENT/pokemon-kafka-speedrun-${TAG}"
# Whatever the operator leaves running when it exits (or is killed) is reaped, parents first, and
# verified gone — a leftover relay in this worktree is invisible to the next run's guards until it
# has already starved it.
trap '"$REPO/scripts/reap_emulators.sh" "$WT" || true' EXIT
SVC="game-event-bridge-${TAG}"
OUT="${OUT_DIR:-$REPO/data/local_runs}"; mkdir -p "$OUT"
PROMPT="${PROMPT_FILE:-$REPO/docs/prompts/operator_prompt_v2.md}"
ASSIST="${ASSIST:-none}"

[ -f "$PROMPT" ] || { echo "missing mission prompt: $PROMPT" >&2; exit 2; }
command -v claude >/dev/null || { echo "claude not on PATH" >&2; exit 2; }
command -v tapesctl >/dev/null || { echo "tapesctl not on PATH" >&2; exit 2; }
nc -z 127.0.0.1 8082 || { echo "tapes ingest :8082 is down — start tapes serve" >&2; exit 2; }

MISSION="$(cat "$PROMPT")"
# Claude Code's window is 200k; the mission's context-safety line names the pi window. Keep the rule, fix the number.
MISSION="${MISSION//this harness has a 128k window and no prompt caching/this harness has a 200k window and prompt caching}"
case "$ASSIST" in
  tips|both) TIPS="$REPO/docs/prompts/tips.md"; if [ -s "$TIPS" ]; then MISSION="$MISSION

## Tips from past runs (each one proved lift on a fresh model before it was written here)
$(grep '^- ' "$TIPS")"; fi ;;
esac
echo "== assist: $ASSIST"

echo "== worktree $WT @ $BASE"
if [ ! -d "$WT" ]; then
  git -C "$REPO" worktree add -b "speedrun/${TAG}" "$WT" "$BASE" >/dev/null
fi
mkdir -p "$WT/rom" "$WT/demo-runs/states" "$WT/data/telemetry/game"
ln -sf "$REPO/rom/pokemon_red.gb" "$WT/rom/pokemon_red.gb"
cp -n "$REPO/demo-runs/states/route1.state" "$WT/demo-runs/states/" 2>/dev/null || true
[ -d "$REPO/demo-runs/states/mtmoon_seeds" ] && cp -rn "$REPO/demo-runs/states/mtmoon_seeds" "$WT/demo-runs/states/" 2>/dev/null || true
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

LOG="$OUT/${TAG}.claude.jsonl"
echo "== claude $MODEL on the Claude Code harness (budget ${BUDGET_S}s) — stream-json log $LOG"
START=$(date +%s)
ENVARGS=()
[ "${CLAUDE_USE_API_KEY:-0}" = 1 ] || ENVARGS=(-u ANTHROPIC_API_KEY)
( cd "$WT" && timeout "$BUDGET_S" env "${ENVARGS[@]}" tapesctl start --tapes-url http://localhost:8082 claude -- \
    -p --model "$MODEL" --dangerously-skip-permissions --output-format stream-json --verbose \
    "$MISSION" >"$LOG" 2>"$OUT/${TAG}.claude.err" ) || echo "   claude exited rc=$?"
END=$(date +%s)

echo "== done in $(( (END-START)/60 )) min; batons:"; ls "$WT"/data/relay/*/batons/ 2>/dev/null | sort -u | grep -v ':$' || echo "   none"
echo "== learnings:"; ls "$WT/docs/learnings/" 2>/dev/null || true
echo "== bench row (from the stream-json result event)"
python3 - "$LOG" "$TAG" "$ASSIST" "$START" "$END" <<'PY'
import json,sys
log,tag,assist,start,end=sys.argv[1],sys.argv[2],sys.argv[3],int(sys.argv[4]),int(sys.argv[5])
res=None; turns=0; usage_in=usage_out=cache_read=cache_write=0
for line in open(log):
    try: d=json.loads(line)
    except json.JSONDecodeError: continue
    if d.get("type")=="assistant": turns+=1
    if d.get("type")=="result": res=d
if res is None:
    print("no result event (run killed?) — turns seen:",turns); sys.exit(0)
u=res.get("usage") or {}
mu=res.get("modelUsage") or {}
for m in mu.values():
    usage_in+=m.get("inputTokens",0); usage_out+=m.get("outputTokens",0)
    cache_read+=m.get("cacheReadInputTokens",0); cache_write+=m.get("cacheCreationInputTokens",0)
wall=(end-start)/60; api_ms=res.get("duration_api_ms",0)/60000
print("| model | wall | model time | turns | input tok | cache read | cache write | output tok | provider $ | subtype |")
print("|---|---|---|---|---|---|---|---|---|---|")
print(f"| {tag} (Claude Code, assist={assist}) | {wall:.1f} m | {api_ms:.1f} m | {res.get('num_turns',turns)} | {usage_in:,} | {cache_read:,} | {cache_write:,} | {usage_out:,} | ${res.get('total_cost_usd',0):.2f} | {res.get('subtype')} |")
PY
