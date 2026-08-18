#!/usr/bin/env bash
# Verified teardown of everything a run left behind: relays, self-heal subloops, emulator lanes.
#
#   scripts/reap_emulators.sh                 # everything on the box
#   scripts/reap_emulators.sh <worktree-path> # only processes launched from that worktree
#
# Order matters and is the whole point: kill the PARENTS first (relay.py, sideloop.py) — they respawn
# lanes faster than a child-first sweep can kill them, which is how a "killed" run kept 100+ emulators
# alive through two manual sweeps. Then the lanes. Then loop until the count is actually zero, and
# exit non-zero if it never gets there, so a launcher's exit trap cannot silently leave a mess for
# the next run to be starved by.
set -uo pipefail
SCOPE="${1:-}"
# Match on the process's argv[0..1] being an interpreter running the script — not on any command
# line that merely mentions it (a monitor shell's `zsh -c "... scripts/agent.py ..."` is not a lane).
match() { ps -eo pid,args --no-headers | awk -v re="$1" -v scope="$SCOPE" '($2 ~ /(^|\/)(python[0-9.]*|uv|timeout)$/) && ($0 ~ re) && (scope == "" || index($0, scope)) {print $1}'; }
PARENTS='scripts/(relay|sideloop)\.py'
LANES='scripts/agent\.py'
for pass in 1 2 3 4 5 6 7 8; do
  # parents and their `uv run` wrappers first, so nothing respawns behind the sweep
  match "$PARENTS" | xargs -r kill -9 2>/dev/null
  match "$LANES" | xargs -r kill -9 2>/dev/null
  sleep 1
  left=$(( $(match "$PARENTS" | wc -l) + $(match "$LANES" | wc -l) ))
  [ "$left" -eq 0 ] && { echo "[reap] clean (pass $pass)${SCOPE:+ for $SCOPE}"; exit 0; }
  echo "[reap] pass $pass: $left still alive"
done
echo "[reap] FAILED: $left processes survived eight passes" >&2
match "$PARENTS"; match "$LANES"
exit 1
