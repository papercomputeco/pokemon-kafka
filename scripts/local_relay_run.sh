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
# Reap whatever the operator leaves running, parents first, verified gone (see reap_emulators.sh).
trap '"$REPO/scripts/reap_emulators.sh" "$WT" || true' EXIT
SVC="game-event-bridge-pi-${TAG}"
OUT="${OUT_DIR:-$REPO/data/local_runs}"; mkdir -p "$OUT"
PROMPT="${PROMPT_FILE:-$REPO/docs/prompts/operator_prompt_v2.md}"
PI_CLI="${PI_CLI:-$(ls "$HOME"/.local/share/fnm/node-versions/*/installation/lib/node_modules/@mariozechner/pi-coding-agent/dist/cli.js | tail -1)}"

[ -f "$PROMPT" ] || { echo "missing mission prompt: $PROMPT" >&2; exit 2; }
# ASSIST is OPT-IN so baseline rows keep measuring the model alone:
#   ASSIST=none     (default) no tips, no consult — the row is comparable to every earlier benchmark row
#   ASSIST=tips     append docs/prompts/tips.md (gated tips from scripts/advisor.py promote) to the mission
#   ASSIST=consult  register the `consult` (Oracle) tool in the guardrails
#   ASSIST=fit      append this model's measured operator character (references/model_fit.json, scripts/model_fit.py)
#   ASSIST=both     tips + consult;  ASSIST=all  tips + consult + fit
# The bench row label carries the assist mode; assisted rows are a separate comparison.
# Expedition mode (docs/expedition-spec.md): assists on by default; the supervisor owns termination.
MODE="${MODE:-bench}"
[ "$MODE" = "expedition" ] && ASSIST="${ASSIST:-all}"
ASSIST="${ASSIST:-none}"
TIPS="$REPO/docs/prompts/tips.md"
MISSION="$(cat "$PROMPT")"
case "$ASSIST" in
  tips|both)
    if [ -s "$TIPS" ]; then MISSION="$MISSION

## Tips from past runs (each one proved lift on a fresh model before it was written here)
$(grep '^- ' "$TIPS")"; fi ;;
esac
case "$ASSIST" in consult|both|all) export PI_GUARD_CONSULT=1 ;; *) unset PI_GUARD_CONSULT ;; esac
# ASSIST=fit: this model's measured operator character (references/model_fit.json) appended to the
# mission. Knowledge from other runs -> assisted row, labelled. Unlisted alias -> nothing, and says so.
case "$ASSIST" in
  fit|all) FIT="$(cd "$REPO" && uv run python scripts/model_fit.py section "$ALIAS" 2>/dev/null)"
    if [ -n "$FIT" ]; then MISSION="$MISSION

$FIT"; else echo "   (ASSIST=fit: no fit entry for $ALIAS — running unassisted)"; ASSIST="none"; fi ;;
esac
echo "== assist: $ASSIST"
echo "== mode: $MODE"
# Supervisor evidence: scripts/expedition_run.sh writes continuation prompts / wall nudges here
# between attempts; a bench run never sets it, so rows stay unassisted by default.
if [ -n "${MISSION_EXTRA_FILE:-}" ] && [ -s "$MISSION_EXTRA_FILE" ]; then
  MISSION="$MISSION

## Supervisor
$(cat "$MISSION_EXTRA_FILE")"
  echo "== mission extra: $MISSION_EXTRA_FILE"
fi
curl -sf "http://127.0.0.1:11434/api/tags" | grep -q "\"${MODEL}" || { echo "model ${MODEL} not in Ollama — run local_models.py create ${ALIAS}" >&2; exit 2; }
nc -z 127.0.0.1 42345 || { echo "tapes proxy :42345 is down — start tapes serve" >&2; exit 2; }
# Power preflight: a model whose Spec carries `power_w` has hung the eGPU at the stock 600 W limit
# (qwen38-27b, four Xid 8s on 2026-08-15/16) and may only run once `nvidia-smi` reports the card
# capped at or below it. The cap resets on reboot, so it is checked here every time rather than
# trusted from the last time it was set (scripts/nvidia-power-cap.service makes it persistent).
# POWER_OVERRIDE=1 skips the check — the row it produces is then not a model verdict.
echo "== power preflight"
if ! ( cd "$REPO" && uv run python scripts/local_models.py power "$ALIAS" ); then
  if [ "${POWER_OVERRIDE:-0}" = "1" ]; then echo "   POWER_OVERRIDE=1 — running uncapped; do not publish this row as a verdict"
  else echo "   refusing to start: cap the card first (see above), or POWER_OVERRIDE=1" >&2; exit 2; fi
fi

echo "== worktree $WT @ $BASE"
if [ ! -d "$WT" ]; then
  git -C "$REPO" worktree add -b "speedrun/pi-${TAG}" "$WT" "$BASE" >/dev/null
fi
mkdir -p "$WT/rom" "$WT/demo-runs/states" "$WT/data/telemetry/game" "$WT/data/power"
ln -sf "$REPO/rom/pokemon_red.gb" "$WT/rom/pokemon_red.gb"
cp -n "$REPO/demo-runs/states/route1.state" "$WT/demo-runs/states/" 2>/dev/null || true
# The skill-matrix battle leg seeds from the pre-Brock baton (gitignored, like every state).
cp -n "$REPO/demo-runs/states/pre-brock.state" "$WT/demo-runs/states/" 2>/dev/null || true
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

# GPU lock: advisor.py / run_model_evals.py refuse to load models while a relay run owns the card.
# (2026-08-16: running the Investigator during qwen38-27b r3 evicted the relay's model — dead stream,
# invalid row. Same failure class as the CUDA crash; this time self-inflicted.)
GPU_LOCK="$OUT/GPU_BUSY"; echo "$TAG pid=$$ started=$(date -Is)" > "$GPU_LOCK"
trap 'rm -f "$GPU_LOCK"' EXIT
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

# Capture the run window's logs next to the row's other evidence, so the harness-death guard in
# bench_report.py still has them after the journal rotates (2026-08-16: four Xid 8 hangs killed
# qwen38-27b runs that pi recorded as ordinary `stop` turns). The kernel log is small enough to
# keep whole; the Ollama unit logs every request, so only its error lines are kept. A journalctl
# that cannot run leaves NO file, which the guard reports as unchecked rather than clean.
KERNEL_LOG="$OUT/${TAG}.kernel.log"; OLLAMA_LOG="$OUT/${TAG}.ollama.log"
UNTIL="@$((END + 120))"
journalctl -k --since "@$START" --until "$UNTIL" --no-pager >"$KERNEL_LOG" 2>/dev/null || rm -f "$KERNEL_LOG"
if journalctl -u ollama --since "@$START" --until "$UNTIL" --no-pager >"$OLLAMA_LOG.raw" 2>/dev/null; then
  grep -E 'CUDA|ERROR|error:|terminated|core dumped' "$OLLAMA_LOG.raw" >"$OLLAMA_LOG" || true
else
  rm -f "$OLLAMA_LOG"
fi
rm -f "$OLLAMA_LOG.raw"

SESSION=$(ls -t "$HOME/.pi/agent/sessions/"*"speedrun-pi-${TAG}--"/*.jsonl 2>/dev/null | head -1 || true)
echo "== bench row (session $SESSION)"
if [ -n "$SESSION" ]; then
  ( cd "$REPO" && uv run python scripts/bench_report.py "$SESSION" --label "${TAG} (local, ${CTX_K}k, assist=${ASSIST})" \
      --rate-in "${RATE_IN:-0.14}" --rate-out "${RATE_OUT:-1.00}" --power-log "$POWER_CSV" --kwh-price "${KWH_PRICE:-0.39}" \
      --kernel-log "$KERNEL_LOG" --ollama-log "$OLLAMA_LOG" ) \
    || echo "   ^ no row (rc=3: the run died on the harness) — write the attempt up, do not publish a row"
fi
