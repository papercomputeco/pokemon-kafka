# 2026-08-26 — the roster engine's first rows: supply, catch, catalog

Engine rows, not model rows: these measure the harness capabilities PR #109 added
(quartermaster errands, the catch hook, the encounter catalog), the way `mtmoon_clear`'s
deterministic replay measures the dungeon drive. The operator column — whether a MODEL wields
these tools — is a separate matrix slot, specced at the bottom. Reproduce with
`scripts/roster_bench.sh` (~4 min wall; headless PyBoy runs ~100x realtime).

Seed for every row: the mtmoon baton driven to Cerulean (96 turns, deterministic), i.e. map 3,
₽2467, no balls, no potions, Charmeleon L22 at 25/63.

## SUPPLY — the mart + heal errand, 3 reps from the same seed

| rep | rc | wall | money | balls | potions | lead |
|---|---|---|---|---|---|---|
| 1 | 0 | 1 s | 2467 → 367 | 0 → 6 | 0 → 3 | 25/63 → **63/63** |
| 2 | 0 | 1 s | 367 | 6 | 3 | 63/63 |
| 3 | 0 | 1 s | 367 | 6 | 3 | 63/63 |

Three byte-identical outcomes: the RAM-verified settle loops are deterministic from a fixed
state. The planner's clamp is visible in the row — 4 potions requested, 3 bought, ₽100 reserve
kept. An errand costs ~1 wall-second: **supplies are effectively free between legs.**

## CATCH — transit across Route 4's grass band, 4 stagings (different tiles = different RNG)

| staging | turns | encounters | outcome |
|---|---|---|---|
| x=64 (first run) | 3000 | 1 | **WEDGE** — threw at one Rattata for ~2,900 turns, never arrived |
| x=64 (after fix) | 39 | 2 | 3 capped throws → strategy unstuck the menu → both fights won, arrived |
| x=66 | 31 | 0 | clean transit |
| x=68 | 32 | 1 | **Rattata L8 caught, 1 ball** |
| x=70 | 27 | 0 | clean transit |

The wedge is the benchmark's find: **the catch hook bypasses `choose_action`, so it also
bypassed the battle stall guard** — a wedged battle menu ate ball-throw actions forever with
nothing ever pressing the unstick. Fixed the same hour: throws are capped at 3 per enemy, then
the strategy takes the turn back (unstick, fight, flee — its machinery, its battle). The
regression test pins the cap and its reset on a new enemy.

Encounter frequency over the ~10-tile band is low (2 encounters per 4 transits): transit
catching is opportunistic. A real hunt (the Paras trip) wants the training-loop's roam
primitive — still the next build.

## CATALOG — the full scan, twice

| scan | wall | streams | battle rows | species rows |
|---|---|---|---|---|
| 1 | 19 s | 84 | 3,676,033 | 56 |
| 2 | 19 s | 84 | 3,676,033 | 56 |

The two catalogs agree byte-for-byte (aggregation is a pure function of the streams), and the
recommendation is stable: **Paras, score 4.0** (bug/grass — hits water ×2, takes ×0.5, L8–12,
6,515 wild sightings, all three Mt. Moon floors), then Pikachu 3.0 (Viridian Forest).

## What the rows earned

- The `stop_on_party` condition landed (agent, relay, tests) and the **`cerulean_recruit`**
  segment now exists: stop at party 3, `--catch` list straight from the optimizer. With
  `route4_to_cerulean` and `cerulean_to_badge2` this completes the roster road's segments.
- One engine bug found and fixed by benchmarking (the uncapped-throw wedge) — the exact reason
  these rows exist before any model slot spends hours on the same wall.

## The operator leg (next matrix column, not yet run)

The model question these engine rows deliberately do not answer: given the mission "win Badge
2", does an operator *use* the tools — run the supply errand before the gauntlet, pick the
catch list from `encounters.py recommend`, choose `cerulean_recruit` before `cerulean_to_badge2`?
That is a RESOURCE column for the skill matrix: same harness for every model, one slot per
model, `vllm-sr/auto` as the routed row. Segments exist; the slot needs only a mission prompt
and a chain script.

## Postscript, same day: THE CASCADE BADGE

The 2-hour validation mandate ended with **Badge 2 in hand** — the furthest this project has
ever been. The full chain, every link an engine capability built or fixed today:

1. **Round 1** (2 h): wedged at turn ~2,000 for 88,000 turns — the battle bag REMEMBERS its
   cursor between opens, and the blind heal-item walk drifted onto CANCEL over a wild NidoranF.
   Fixed: the bag walks by ABSOLUTE row (wListScrollOffset + cursor, read live). Verified on
   the wedged checkpoint itself: HP 14 → 34, potion spent, battle resumed.
2. **Round 2** (resumed from the wedge): the freed lane ground the bridge to **L27, 63 wins**
   — and parked in Bill's cottage, because above grind level no driver owned the northern maps.
   Fixed: the come-home branch (cottage door → Route 25 west → bridge south → gym).
3. **The errand chain home**: potions bought; the mart exit was body-blocked by a customer
   parked on ONE of the two exit mats — the walk now drops a blocked target when another
   remains and vetoes non-target bodies (the parked-body class, third appearance today).
4. **The challenge**: from L27 at 76/76 — a first loss white-outed to the Center, the driver
   ground back, rechallenged, and **won at L33: `badges: 0b11`, turn 2,556 of the final
   segment, baton settled**. The self-correction loop carried the badge without a single
   human intervention after launch.

Baton: `demo-runs/states/cerulean_seeds/badge2_hp38.state` — Cerulean Gym (5,2), Badge 1+2,
Charmeleon L33 at 38/92 (Scratch/Rage/Ember/Leer), 5 balls, TM11 in the bag, ₽2,079. The road
to Vermilion — and the Paras/Oddish roster work — starts from here.

Six engine bugs found and fixed by one validation mandate, every one screenshot-diagnosed and
regression-tested: the learn flow, the bag cursor, the gym approach geometry, the grind
threshold, the northern-maps gap, and the exit-mat body. The benchmark did exactly what
benchmarks are for.
