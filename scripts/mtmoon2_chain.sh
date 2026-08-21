#!/usr/bin/env bash
# The 2026-08-20 Mt. Moon-clear batch: local models only, pi harness, full self-heal, expedition
# loop per model, hard 5-hour ceiling. qwen38-27b runs LAST and alone — it pins the GPU at its
# 600 W cap and shares with nothing (its eGPU-hang history is why). No Claude anywhere: the
# escalation tier is disabled by pre-seeding each supervisor state with escalate_after=99.
#
#   scripts/mtmoon2_chain.sh            # runs laguna-xs, qwen3-coder-30b, then qwen38-27b
#
# Per-model wall-clock slots inside the ceiling; qwen38 gets whatever remains. Every leg is a
# normal launcher run: power sampled, guard-checked, bench row printed (energy at $0.39/kWh).
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$REPO/data/local_runs"
DEADLINE=$(( $(date +%s) + 5 * 3600 ))
MISSION="$REPO/docs/prompts/operator_prompt_mtmoon2.md"
SEGMENT="mtmoon_clear"
BASE="bench/mtmoon2"
LOG="$OUT/mtmoon2-chain.log"
say() { echo "[mtmoon2 $(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

expedition() { # $1=alias $2=slot_seconds $3=leg_budget_s
  local alias="$1" slot="$2" leg="$3" tag state remain
  remain=$(( DEADLINE - $(date +%s) ))
  [ "$remain" -le 300 ] && { say "SKIP $alias — under 5 min to deadline"; return; }
  [ "$slot" -gt "$remain" ] && slot="$remain"
  tag="exp-${alias//[^a-z0-9]/-}-mtmoon2"
  state="$OUT/${tag}.supervisor.json"
  # No-Claude guard: escalation never fires.
  printf '{"escalate_after": 99, "max_continuations": 2, "max_resumes": 3}' > "$state"
  say "START $alias — slot $((slot/60))m, leg budget $((leg/60))m, tag $tag"
  timeout "$slot" env EXPEDITION_TAG="$tag" PROMPT_FILE="$MISSION" LEG_ROUTE="59 3" \
    LEG_BUDGET_S="$leg" MAX_ATTEMPTS=6 \
    "$REPO/scripts/expedition_run.sh" "$alias" "$SEGMENT" "$BASE" >>"$LOG" 2>&1
  say "END $alias rc=$? — reaping"
  "$REPO/scripts/reap_emulators.sh" "$(dirname "$REPO")/pokemon-kafka-speedrun-pi-${tag}" >>"$LOG" 2>&1 || true
  pkill -f "pokemon-kafka-speedrun-pi-${tag}" 2>/dev/null
  sleep 5
}

say "=== mtmoon2 chain start; deadline $(date -u -d "@$DEADLINE" +%H:%M:%SZ); base $BASE @ $(git -C "$REPO" rev-parse --short "$BASE") ==="
expedition laguna-xs        4200 1800   # 70 m slot, 30 m legs — the Driver; does ROM truth fix its deliverable problem?
expedition qwen3-coder-30b  4200 1800   # 70 m slot, 30 m legs — the 08-16 baseline, first look on the fixed world
expedition qwen38-27b      $(( DEADLINE - $(date +%s) - 120 )) 4200  # the remainder, alone, 70 m legs
say "=== mtmoon2 chain done ==="
