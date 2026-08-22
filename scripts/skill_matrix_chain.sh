#!/usr/bin/env bash
# The per-skill model matrix (2026-08-22): 5 models x 3 skill legs, pi harness, expedition loop,
# NO Claude anywhere (escalation pre-seeded off). Cloud legs run first (no GPU load, no thermal
# history), locals after, qwen38-27b LAST and alone (600 W pin; eGPU-hang history). One leg at a
# time — the box-wide relay lock serializes relays regardless, so the chain never fights it.
#
#   scripts/skill_matrix_chain.sh          # full matrix, ~7.5 h ceiling
#
# Legs per model: battle (15 m slot), nav (25 m), puzzle (50 m). Every leg is a normal launcher
# run: capture, guards, reaping, bench row. Expedition rows are labelled by mode and never enter
# the unassisted tables.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$REPO/data/local_runs"
DEADLINE=$(( $(date +%s) + 8 * 3600 ))
BASE="${SKILL_BASE:-bench/mtmoon2}"
LOG="$OUT/skill-matrix-chain.log"
mkdir -p "$OUT"
say() { echo "[skill-matrix $(date -u +%H:%M:%SZ)] $*" | tee -a "$LOG"; }

leg() { # $1=model $2=segment $3=mission $4=slot_s $5=leg_budget_s $6=leg_route
  local model="$1" segment="$2" mission="$3" slot="$4" legb="$5" route="$6" tag state remain
  remain=$(( DEADLINE - $(date +%s) ))
  [ "$remain" -le 300 ] && { say "SKIP $model/$segment — under 5 min to deadline"; return; }
  [ "$slot" -gt "$remain" ] && slot="$remain"
  tag="skl-$(printf '%s' "$model" | sed -E 's/[^a-z0-9]+/-/g')-${segment//_/-}"
  state="$OUT/${tag}.supervisor.json"
  printf '{"escalate_after": 99, "max_continuations": 2, "max_resumes": 3}' > "$state"
  say "START $model / $segment — slot $((slot/60))m, leg $((legb/60))m, tag $tag"
  timeout "$slot" env EXPEDITION_TAG="$tag" PROMPT_FILE="$REPO/docs/prompts/$mission" \
    LEG_ROUTE="$route" LEG_BUDGET_S="$legb" MAX_ATTEMPTS=4 \
    "$REPO/scripts/expedition_run.sh" "$model" "$segment" "$BASE" >>"$LOG" 2>&1
  say "END $model / $segment rc=$? — reaping"
  "$REPO/scripts/reap_emulators.sh" "$(dirname "$REPO")/pokemon-kafka-speedrun-pi-${tag}" >>"$LOG" 2>&1 || true
  pkill -f "pokemon-kafka-speedrun-pi-${tag}" 2>/dev/null
  sleep 5
}

model_row() { # all three legs for one model
  local m="$1"
  leg "$m" pewter_to_badge   operator_prompt_skill_battle.md  900 600  "54 2"
  leg "$m" mtmoon_1f_to_b1f  operator_prompt_skill_nav.md    1500 900  "59 60"
  leg "$m" mtmoon_clear      operator_prompt_skill_puzzle.md 3000 1500 "59 15"
}

say "=== skill matrix start; deadline $(date -u -d "@$DEADLINE" +%H:%M:%SZ); base $BASE @ $(git -C "$REPO" rev-parse --short "$BASE") ==="
model_row "kimi-k2.6:cloud"
model_row "qwen3.5:397b-cloud"
model_row "laguna-xs"
model_row "qwen3-coder-30b"
model_row "qwen38-27b"
say "=== skill matrix done ==="
