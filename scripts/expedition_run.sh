#!/usr/bin/env bash
# The expedition outer loop (docs/expedition-spec.md): one leg attempted repeatedly under the
# supervisor until its baton exists, with harness deaths resumed, early exits continued, and
# walls that eat `ESCALATE_AFTER` attempts handed to the fix-source tier. This is the cross-run
# loop — the only loop that has ever cleared a wall — with the human replaced by
# scripts/supervisor.py for everything except merging to main.
#
#   scripts/expedition_run.sh <model> <segment> [base-commit]
#     e.g. scripts/expedition_run.sh qwen38-27b badge_to_mtmoon main
#
# Env: HARNESS=claude|local (default: claude for claude-* models, local otherwise)
#      LEG_BUDGET_S per attempt (default 7200); MAX_ATTEMPTS safety cap (default 12)
#      ESCALATE_MODEL (default claude-opus-5) + ESCALATE_BUDGET_S (default 1800, Brock took 14 min)
#      PROMPT_FILE mission override; EXPEDITION_TAG names worktree/branch/state
#
# Every attempt is a normal launcher run (MODE=expedition), so capture, guards, reaping and the
# bench row all work unchanged; expedition rows are labelled by mode and never enter the
# model-vs-model tables. Merging fixes to main stays a human-gated PR — the expedition carries
# its own fixes forward on its worktree branch and does not wait.
set -euo pipefail

MODEL="${1:?usage: expedition_run.sh <model> <segment> [base-commit]}"
SEGMENT="${2:?usage: expedition_run.sh <model> <segment> [base-commit]}"
BASE="${3:-main}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
case "$MODEL" in claude-*) HARNESS="${HARNESS:-claude}" ;; *) HARNESS="${HARNESS:-local}" ;; esac
LEG_BUDGET_S="${LEG_BUDGET_S:-7200}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-12}"
ESCALATE_MODEL="${ESCALATE_MODEL:-claude-opus-5}"
ESCALATE_BUDGET_S="${ESCALATE_BUDGET_S:-1800}"
TAG="${EXPEDITION_TAG:-exp-$(printf '%s' "$MODEL" | sed -E 's/[^a-z0-9]+/-/g')-${SEGMENT//_/-}}"
OUT="$REPO/data/local_runs"
STATE="$OUT/${TAG}.supervisor.json"
EXTRA="$OUT/${TAG}.mission-extra.md"
# The local launcher prefixes its worktrees with `pi-`; the claude launcher does not. The
# baton/lane-log checks below must look where the launcher actually put the worktree.
if [ "$HARNESS" = "claude" ]; then
  WT="$(dirname "$REPO")/pokemon-kafka-speedrun-${TAG}"
else
  WT="$(dirname "$REPO")/pokemon-kafka-speedrun-pi-${TAG}"
fi
LOG="$OUT/${TAG}.expedition.log"
mkdir -p "$OUT"
# Leg briefing (spec: mission integration) — the ROM-truth routed chain, so operator budget goes
# to execution walls, not topology. LEG_ROUTE="<src> <dst>" (default: the badge_to_mtmoon leg).
LEG_ROUTE="${LEG_ROUTE:-54 59}"
write_briefing() {
{
  echo "ROM truth is available in this worktree: \`references/rom_truth.json\` (warps, edge"
  echo "connections, collision grids for every map) via \`scripts/rom_truth.py\`. Do NOT re-derive"
  echo "topology by probing — look it up. Never cat rom_truth.json raw (the grids are huge and will"
  echo "drown your context); query it with \`rom_truth.py route\` or targeted python -c one-liners."
  echo "The routed chain for this leg:"
  echo '```'
  # shellcheck disable=SC2086
  uv run python "$REPO/scripts/rom_truth.py" route $LEG_ROUTE 2>/dev/null || echo "(route unavailable)"
  echo '```'
  echo "Seed the pilot with the full grids before your first relay:"
  echo '```'
  echo "uv run python scripts/rom_truth.py seed-worldmap 2 14 15 54 59 --out mtmoon.worldmap"
  echo "# then add:  --seed-worldmap mtmoon.worldmap  to the relay.py command"
  echo '```'
} > "$EXTRA"
}
write_briefing

say() { echo "[expedition] $*" | tee -a "$LOG"; }

launch() { # $1=model $2=budget $3=prompt-file-or-empty
  local start rc launcher
  local -a envs=(MODE=expedition RUN_TAG="$TAG" BUDGET_S="$2" MISSION_EXTRA_FILE="$EXTRA")
  # NB: a var=val word produced by expansion is a command, not an assignment — hence `env`.
  [ -n "${3:-}" ] && envs+=(PROMPT_FILE="$3")
  launcher="$REPO/scripts/local_relay_run.sh"
  if [ "$HARNESS" = "claude" ] || [ "$1" != "$MODEL" ]; then
    launcher="$REPO/scripts/claude_relay_run.sh"
  fi
  start=$(date +%s)
  set +e
  env "${envs[@]}" "$launcher" "$1" "$BASE" >>"$LOG" 2>&1
  rc=$?
  set -e
  USED_S=$(( $(date +%s) - start ))
  return $rc
}

attempt=0
while [ "$attempt" -lt "$MAX_ATTEMPTS" ]; do
  attempt=$((attempt + 1))
  say "attempt $attempt/$MAX_ATTEMPTS: $MODEL on $SEGMENT (budget ${LEG_BUDGET_S}s, harness $HARNESS)"
  rc=0; launch "$MODEL" "$LEG_BUDGET_S" "${PROMPT_FILE:-}" || rc=$?

  BATON=0
  [ -e "$WT/batons/${SEGMENT}.state" ] || ls "$WT"/data/relay/*/batons/*.state >/dev/null 2>&1 && BATON=1
  # Harness death per the guard's definition: the operator died without spending its budget and
  # without saying anything — a timeout kill (rc 124) is the budget, any other nonzero is the box.
  DEATH=0
  [ "$rc" -ne 0 ] && [ "$rc" -ne 124 ] && DEATH=1
  LOAD_OK=1
  [ "$(cut -d. -f1 /proc/loadavg)" -gt 60 ] && LOAD_OK=0

  LANE_ARGS=()
  while IFS= read -r f; do LANE_ARGS+=(--lane-log "$f"); done \
    < <(find "$WT/data/relay" -name 'agent.log' 2>/dev/null | head -40)
  DECISION=$(uv run python "$REPO/scripts/supervisor.py" classify-exit \
    --state "$STATE" --budget "$LEG_BUDGET_S" --used "$USED_S" \
    --baton "$BATON" --harness-death "$DEATH" --load-ok "$LOAD_OK" ${LANE_ARGS[@]+"${LANE_ARGS[@]}"})
  ACTION=$(printf '%s' "$DECISION" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["action"])')
  say "decision: $DECISION"

  case "$ACTION" in
    next_leg)
      # Feed the cleared leg into the advisor pipeline (investigate -> design -> gate -> promote):
      # investigate extracts candidate tips now; gate/promote still require proven lift, by design.
      SESSION="$OUT/${TAG}.claude.jsonl"
      [ -s "$SESSION" ] || SESSION="$(ls -t "$HOME/.pi/agent/sessions/"*"${TAG}"*/*.jsonl 2>/dev/null | head -1)"
      say "leg cleared — baton written; investigating session ${SESSION:-'(none found)'}"
      [ -s "${SESSION:-}" ] && uv run python "$REPO/scripts/advisor.py" investigate "$SESSION" \
        --worktree "$WT" --no-design >>"$LOG" 2>&1 || true
      exit 0 ;;
    continue|resume|retry_leg)
      # The next attempt keeps the ROM-truth briefing; the supervisor's prompt and nudges append.
      write_briefing
      printf '%s' "$DECISION" | uv run python -c \
        'import json,sys; d=json.load(sys.stdin); t=[d.get("prompt","")]+d.get("nudges",[]); print("\n".join(x for x in t if x))' >> "$EXTRA"
      "$REPO/scripts/reap_emulators.sh" "$WT" >>"$LOG" 2>&1 || true ;;
    escalate)
      WALL=$(printf '%s' "$DECISION" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["wall"])')
      say "escalating wall $WALL to $ESCALATE_MODEL (fix source, ${ESCALATE_BUDGET_S}s)"
      { echo "## The wall"; echo "Fingerprint: $WALL, unresolved after repeated attempts."
        echo "Evidence: docs/learnings/ in worktree $WT, supervisor state $STATE."
        uv run python "$REPO/scripts/rom_truth.py" route "${WALL%%<->*}" "${WALL##*<->}" 2>/dev/null || true
      } > "$EXTRA"
      RUN_TAG="${TAG}-fixsource-$attempt" HARNESS=claude \
        launch "$ESCALATE_MODEL" "$ESCALATE_BUDGET_S" "$REPO/docs/prompts/operator_prompt_fixsource.md" || true
      : > "$EXTRA" ;;
    stop_alert|*)
      say "stopping: $ACTION — the box needs a human"; exit 3 ;;
  esac
done
say "attempt cap ($MAX_ATTEMPTS) reached without a baton"; exit 4
