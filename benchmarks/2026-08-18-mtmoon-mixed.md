# 2026-08-18 — Mt. Moon, mixed benchmarks on the fixed `main`

First runs east of Pewter. `badge_to_mtmoon` (Gym → Route 3 → Mt. Moon 1F, map 59) had no waypoints,
no learnings and no prior attempt; the mission says so (`docs/prompts/operator_prompt_mtmoon.md`). All
three rows share one seed — a badge baton produced on `main` @ e83bdf9 (PR #93): Charmeleon L16 on
Brock's tile at **6/48 HP**, badge in hand — one relay on the box at a time, 2 h hard cap, self-heal
`--sideloop-every 300` required, `date` at start and before the summary. Base is `bench/mtmoon-mixed`
= `main` + mission + launchers carrying the seed. **Every row here is a "fixed main" row.**

Mode is `mixed` (README): Claude on Claude Code, local roster on pi. Compare Claude ↔ local on
behaviour, not on wall clock; compare the two local rows with each other.

## Scoreboard

| model | harness | map 59 | furthest | wall | model time | turns | s/turn | out tok/s | input | output | provider $ | cloud $ eq | Wh | code | commits | learnings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Haiku 4.5 | Claude Code | **no** | map 54 (4,13) — never left the Gym | 38.6 m | 13.2 m | 81 | — | — | 3.5 k (+7.7 M cache) | 47 k | $1.37 | — | — | 0 files | 5 | 3 (real log lines) |
| laguna-xs (128k) | pi, local | **no** | map 54 (6,4) — one relay call | 18.9 m | 13.7 m | 353 | 2.3 | 133.8 | 20.9 M | 110 k | $0 | $3.03 | 124.2 | 0 | 0 | **0** |
| **qwen38-27b** (128k, no MTP, 600 W) | pi, local | **no** | **map 14 (3,11) — Route 3, all six lanes** | 95.3 m | 87.8 m | 274 | 19.2 | 54.5 | 17.5 M | 287 k | $0 | $2.73 | 875.3 | **+376 `agent.py`, +7 `evolve.py`, 265 lines of tests** | 2 | 4 (one per obstacle) |

Guard: both local rows passed the harness-death check (no dead stream, no `Xid`, no Ollama crash;
power logs `data/power/`). No `REFUSED`, one relay at a time throughout; slot pool peaked 30/30.

## What each model did with the same seed

**Haiku 4.5** ran six relays in 22 minutes before its first commit, then five commits and three
learnings files by 25 minutes — its clock is now accurate ("30 min, ~89 remaining"; the `date`
instruction fixed the 2.4× inflation) — and it kept working after writing the summary, which is new.
It named the wall as a **"one-way trap warp"** at the Gym door: exit to Pewter (16,17), warp straight
back to the Gym. That is a real symptom read the wrong way. The lane leaves the Gym and its next
step is back onto the door it just came out of; qwen38 later measured the same door and named it
correctly (a `LAST_MAP` mat — the door warps to "where you came from", so pressing it from outside
puts you back inside). Haiku called the Gym "sealed" and ended at 38.6 min with 80 left. Same shape as
its Brock r4 coordinate misread: real measurement, wrong attribution, and the wrong attribution
ends the investigation. 108 lanes; furthest was the door mat after 12 000 turns.

**laguna-xs** made one relay call and produced **no commit and no learnings file** — the transcript
ends in a compaction loop at 98 k tokens, three compactions in its last minutes. This is its 08-16 r2
failure ("compaction amnesia", SUMMARY §10) recurring on a fresh, harder mission. The Driver cadence
is intact (2.3 s/turn, 133.8 tok/s, the fastest on the box); the context discipline is not, and on a
mission where the first move is *reasoning* about the seed rather than driving, nothing survives.
The row is valid — the guard passed, 124 Wh — the deliverable is empty.

**qwen38-27b** read the code first: `+220` lines with tests committed at 11 minutes, *before* its
first relay call. Then it built the whole path the mission asked for, one obstacle file each:
- `route3-heal-gating.md` — a heal that works *with* the badge (the Pewter heal path was gated on
  not having it; the seed's 6 HP was the first thing to reason about, and it did);
- `route3-gym-exit.md` — the door is a `LAST_MAP` mat, not a warp to map 2 (the thing Haiku called a
  trap); exit west, then the city's east edge is Route 3 (dropped the lane at (0,8)/(0,11));
- a "14 march" and `--seed-worldmap`. **All six lanes reached map 14.** Route 3, for the first time.

Then a 14-probe campaign on Route 3's edges — west/south/north → city — and a verdict: *"Route 3 is a
city pocket; its warp table is empty; map 59 is unreachable from this seed."* Item by item that is
right and the conclusion is wrong. Route 3 *is* warp-less — outdoor maps connect by edge adjacency,
and Mt. Moon's door is a warp on **Route 4**, past Route 3's east end. **The furthest any lane got
on map 14 was x = 3.** Route 3 is ~70 tiles wide. 817 turns on the map, zero battles, x ≤ 3: the
lanes lived in the west pocket, and the "east → solid" reading came from there. The wall is walk
east through the trainers; it was diagnosed as topology. Same failure class as Haiku's, one map
further along, and with the entire path to it built and tested.

95 minutes and it ended by choice with 25 left — the longest run of the three and the first local
run to use most of its budget.

## Self-healing on this segment

`badge_to_mtmoon` races `NAV_SPREAD`, so for the first time the subloop had navigation knobs to move.
Measured from lane logs:

| | Haiku | laguna-xs | qwen38-27b |
|---|---|---|---|
| lanes | 108 | 2 | 12 |
| patches applied | **1 258** | (n/a) | **0** |
| knobs that moved | `axis_preference_map_0` 1051, `waypoint_skip_distance` 1046, `door_cooldown` 840, `stuck_threshold` 831, `hp_run/heal` 559 | — | — |
| `SIDELOOP finished rc=1` (skipped, box full) | — | — | **188** |
| outcome change attributable | none | — | none |

Two findings. First, on Brock the loop could only move HP knobs and moved nothing useful; here it
moved navigation knobs 1 258 times and still moved nothing useful — **no knob value makes a lane not
step back onto a door**. The subloop searches the genome; both walls today were code. Second, the
priority scheme cost qwen38 its healing entirely: 6 lanes × 12 000 turns held the pool at 30/30, so
every one of its 188 subloop races found the box full and skipped. That is the designed degradation
(subloops never starve the lane they heal) — but it means the longest, deepest run of the day ran
unhealed. Reserving a few slots for subloops (say 6 of 30) is the obvious lever; it trades a little
main-lane parallelism for a heal that can actually run.

## Rows vs. `docs/model-fit.md`

- **Haiku — Driver, confirmed again; the accurate clock is new and welcome; the misattribution-then-stop
  pattern is now two for two on walls.**
- **laguna-xs — Driver whose deliverable evaporates when the mission needs a paragraph of thought
  before the first relay call.** Two rows now (r2 08-16, today) with the same compaction signature.
- **qwen38-27b — Investigator, and today an Experimenter (14 probes) and a Reporter (four obstacle
  files, log lines that check out).** Its verdict was wrong, but it built and tested the path to the
  place where it could be wrong, which no other row did. 19.2 s/turn and 875 Wh is what that costs.

## Next

- The lever is concrete: **walk east on Route 3.** Trainers, grass, then Route 4 and the Mt. Moon
  warp. qwen38's branch (`speedrun/pi-qwen38-27b-mtmoon`, `8042b58`) already exits the Gym, heals
  with the badge and reaches map 14 with tests green — cherry-pick that; do not re-derive it.
- Reserve subloop slots so a full box does not silence the heal (see above).
- Route 3 waypoints in `references/routes.json` from the lanes' `world.map` files — the format is
  there, the geometry is now partially measured.
- Whether Opus goes at this as a fix source is your call; the path to the wall is built, so it
  would start where qwen38 stopped.

Artifacts: worktrees `../pokemon-kafka-speedrun-{haiku-cc,pi-laguna-xs,pi-qwen38-27b}-mtmoon`;
stream-json / pi transcripts in `data/local_runs/*-mtmoon.*`; power `data/power/`; chain log
`data/local_runs/mtmoon-chain.log`; seed + manifest `demo-runs/states/mtmoon_seeds/`.
