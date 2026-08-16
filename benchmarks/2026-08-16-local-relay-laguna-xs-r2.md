# 2026-08-16 — Mt. Moon relay, laguna-xs r2 on the fixed `main` (compaction guard + Pewter fix + battle watchdog)

Rerun of `2026-08-16-local-relay-laguna-xs.md` after PRs #74/#75/#76 merged (`RUN_TAG=laguna-xs-r2
scripts/local_relay_run.sh laguna-xs main`). Same model, prompt, seed, harness; the worktree is off
`main` (`410ee6f`) instead of `2cd9240`, so the flee-loop, the Pokécenter and the 128k wall are no
longer in the way. Guardrails at launch: compaction guard yes, read cap **no** (#78 merged mid-run).

## Scoreboard

| model | segs | wall | model time | turns | tools | out tok/s | s/turn | input tok | cache read | output tok | cloud $ | Wh | energy $ | max ctx | compactions | code fix | learnings | commits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| laguna-xs r2 (local, 128k, fixed main) | **2/4 + inside the Gym** | 36.7 m | 22.2 m | **398** | 398 | 126.3 | **3.3** | 22.9 M | 0 | 168 k | $3.37 | **203.6** | $0.061 | 98 k | **12** | attempted (2 files, unverified) | 2 (+1 dup) | 0 |
| _laguna-xs r1 (2cd9240)_ | 2/4 | 40.0 m | 6.6 m | 98 | 97 | 91.1 | 4.0 | 8.4 M | 0 | 36 k | $0.85 | 77.5 | $0.023 | 130.8 k | 1 (pi's) | no | 1 | 0 |
| _Haiku 4.5 (08-15)_ | 2/4 | 67 m | 5.9 m | 74 | 73 | 91.9 | 4.8 | 4.7 k | 3.5 M | 32 k | $0.87 | — | — | — | — | no | 3 + summary | 3 |

Power: 444 samples over 37.1 min, GPU mean **329 W** (r1: 114 W — the model was busy every second
this time), peak 610 W. Ended on its own at 36.7 min ("The fix is complete. Here's a summary") —
not on context (max 98 k; the guard compacted 12 times) and not on the budget.

## What happened

1. `route1_to_forest` cleared on the first relay (winner `base`) — the flee-loop no longer blocks.
2. `forest_to_pewter` cleared (`aggressive`). `pewter_to_badge`: every lane **walked past the
   Pokémon Center, into the Gym (map 54)** — the first time any run has been inside — and one lane
   fought a Gym trainer (`pre_brock.state`, saved by `--save-state-on-trainer 54`). Nobody reached
   Brock: five lanes wedged inside the Gym (stuck streak 2800/4000, 6800/8000); `very_cautious`
   explored (28 battles, 45 HP, streak 51) but never found him.
3. Laguna diagnosed the wedge **correctly and on its own**: `parcel_quest.py` still lists
   `PEWTER_GYM` in `GO_NORTH_PILOT_MAPS`, so inside the Gym the quest pilots "north" toward a map
   edge that doesn't exist — the exact out-of-scope note in PR #75. It wrote
   `docs/learnings/gym-pilot-north-indoor-map-mismatch.md` (well-formed, causal) and edited two
   files: removed `PEWTER_GYM` from the pilot list (right) and added an `EARLY_GAME_TARGETS` entry
   for map 54 targeting `(16,17)` (that is the *overworld* Gym-door tile, not an interior
   coordinate — probably wrong). It then declared the learning "✅ FIXED" without a passing
   `pewter_to_badge` — the only false claim of the run — and did not commit.
4. **Compaction amnesia** (SUMMARY §10): after the second relay it read `agent.py`,
   `parcel_quest.py`, `world_map.py` whole via the `read` tool (40 KB cap each), the guard compacted
   100 k → 15 k twelve times, and it re-read after each. 398 tool calls in 37 min; the last 60 were
   reads and rewrites of the learning file. The read cap (#78) exists because of this run.

## Reading

- **The three fixes did what they were for.** Flee-loop: cleared first try. Pokécenter: bypassed.
  Context: never hit the wall (max 98 k, 12 compactions, 0 errors). Yesterday's run died at
  130.8 k with the Pokécenter unsolved; today's got inside the Gym and named the next bug.
- **Faster than Haiku on every cadence number** — 3.3 s/turn (Haiku 4.8), 126 out tok/s (91.9),
  398 turns to Haiku's 74 — and 4× the turns bought one more room, not one more badge. Turn quality
  again.
- **The cost of staying alive:** 22.9 M uncached input tokens ($3.37 cloud-eq, 4× r1) and 204 Wh
  (2.6× r1) — the compaction loop is expensive even when it works. The read cap should cut this
  hard; that is the r3 comparison to make.
- **Fit verdict stands (SUMMARY §10): driver.** Honest about what it saw, wrong about "FIXED",
  found the bug, botched the fix, forgot across compactions. Pair with an investigator (#79).

## Next

- `qwen38-27b` on the fixed `main` with the read cap — the local investigator with the Gym now
  reachable. Then laguna r3 with the read cap for the cost/energy comparison.
- Land the real Gym fix (remove `PEWTER_GYM` from `GO_NORTH_PILOT_MAPS` + an interior route to
  Brock at the north end of map 54); Laguna's diagnosis is the spec, its patch is not the fix.

Artifacts: worktree `../pokemon-kafka-speedrun-pi-laguna-xs-r2` (branch `speedrun/pi-laguna-xs-r2`,
uncommitted diff + learnings), pi session `~/.pi/agent/sessions/--home-bdougie-code-pcc-labs-pokemon-kafka-speedrun-pi-laguna-xs-r2--/2026-08-16T13-*.jsonl`,
relay `<worktree>/data/relay/260816-135024/` (batons `route1_to_forest`, `forest_to_pewter`, `pre_brock`),
power CSV `<worktree>/data/power/laguna-xs-r2.csv`, pi log `data/local_runs/laguna-xs-r2.pi.log`.
