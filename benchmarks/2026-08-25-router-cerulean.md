# 2026-08-25 — the first routed progress run: Route 4 stands, and it isn't a road

Three-hour expedition slot, `vllm-sr/auto` on the pi harness (the semantic router's first
operator seat, PR #105), segment chain `route4_to_cerulean → cerulean_to_badge2` from the Mt.
Moon clear's baton. **No baton.** ASSIST=expedition — this is a progress-run writeup, not a
benchmark row; per the bench guard, the attempt is written up instead of published.

## The attempts

| attempt | outcome | fitness |
|---|---|---|
| 1 (60 m) | 15↔60 door spring, 571 bounces | map 60 (27,3), 8000 t, all six lanes byte-identical |
| 2 (60 m) | same wall, supervisor nudge consumed | map 60, no movement in the row |
| 3 (~55 m, killed by slot) | **escaped the spring**, wedged at the lake | map 15 (25,6), 4000 t, stuck streak 3977 |

Supervisor: `retry_leg` ×2 on wall `15<->60`; the third strike (escalation to fix-source)
never fired — the outer 3 h timeout killed attempt 3 first.

## What the run established (worktree `…-speedrun-pi-exp-router-cerulean`, kept for mining)

1. **The seed MANIFEST lies.** `route4_east_hp25.state` loads at **(24,5) — standing on the
   east cave door mat**, not (27,3). That is the whole 15↔60 spring: the lane is born on the
   warp. The step-off-the-landing-mat discipline that killed the inside springs never covered
   a *seed that starts on one*. (The operator's party read also claimed "Charmander L20 at 47/50 HP" — a proper 44-byte
   struct read says **Charmeleon L22 at 25/63**: the filename was honest, the learning was not.
   Verify the verifier.)
2. **Route 4 east is a lake maze, not open road.** Holding east crosses to (49,6) and the
   engine refuses ~146 further presses — solid column at x=50, rows 2..9. The hardcoded
   "drive east" state machine (`_mtmoon_action`, map 15 x≥24 special case) walks straight
   into it; that is attempt 3's 3977-turn stuck streak.
3. **The extracted grid says the east road is unreachable — which cannot be true.** BFS over
   `rom_truth.json` map 15 tops out at x=79; two single-tile solid columns (x=62, x=75,
   rows 9-12) and a seal at x=80 disconnect the west region from the east road. A real map
   is not disconnected: either those columns are a tileset mis-decode or they are
   engine-solid and the row-10 strip needs a live press-sweep. The engine arbitrates.
4. **One correction to the operator's own learning:** it calls Misty vs a fire lead
   "favourable". Water beats fire — the matchup is *against* the lane. The Route 24/25
   catches (or Oddish/Bellsprout on the way) are part of the badge answer, not a detour.

## The router in the field

41 operator requests over the slot: **24 → kimi-k2.6:cloud (`puzzle-to-deepest`)**, 14 →
qwen38-27b (`navigation-to-best-line`), 3 → default. The mission classified as navigation at
launch; once the transcript filled with spring/diagnose vocabulary the seat escalated to the
cloud puzzle model mid-session and stayed there while the wall stood. The mechanism works;
whether 24 cloud calls on one wall is the right spend is a policy question the next isolated
benchmark can answer.

## The fix spec (for the next slot, or the fix-source tier)

- Plan map 15 with `_truth_step(state, 3)` — the ROM-truth BFS with per-lane hard-blocks —
  instead of the hardcoded march (the operator's own uncommitted 44-line patch in the
  worktree is the wrong shape and its learning says so).
- Step off the mat on seed load, unconditionally — a seed is a landing.
- Live press-sweep the three suspect columns (x=62, x=75, x=80, rows 9-12); let
  `truth_refuse_strikes` and the expiring hard-block layer absorb whichever are real.
- Fix the seed MANIFEST (position, species, level) so the next mission doesn't inherit the lie.

## Postscript, 2026-08-26: the road opens — it was ledges all along

The fix spec above, implemented (`run/cerulean-router`): the grid's "disconnection" was real in
the grid and false in the world — **Route 4's east road is connected only over one-way LEDGE
hops**, which no walkable-cell BFS can see. `rom_truth.py` now extracts pokered's LedgeTiles
table from the ROM (found by structure, not address: 8 records) and `path_on_map` adds the
one-way two-cell edges on the overworld tileset; `_mtmoon_action` hands Route 4 east (x ≥ 22)
to `_truth_step(→ 3)` so the cave door is never hunted again — killing the 15↔60 seed spring
without touching the mat logic. The MANIFEST's two lies are corrected in place.

Live gate: a single-lane probe from the exact seed reached **Cerulean (map 3) in 96 turns**,
zero battles, path crossing the (44,8) and (79,8) ledges. Three hours of six-lane relays could
never have found this row; one hour of the operator's measurement plus a 40-line planner change
did. The wall was never navigation — it was a missing edge type in the world model.
