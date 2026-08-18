# 2026-08-17 — the Brock wall, with continuous self-healing on

Question going in: can an operator take Badge 1, the wall four 08-16 runs stopped at, and can it do
so **while the agent heals itself the whole time** — not the one-shot wedge heal, the continuous
AlphaEvolve subloop. Two runs are reported. One is a benchmark row; the other is a fix source and
is not.

Both used `scripts/claude_relay_run.sh` on the Claude Code harness (Max sub), a new Brock-only
mission (`docs/prompts/operator_prompt_brock.md`), 2 h hard cap, and staged seed states so the
budget went at the wall instead of at Route 1. Seeds and their measured provenance are in each
worktree's `demo-runs/states/brock_seeds/MANIFEST.md`.

## The row

| model | badge | wall | model time | turns | input | cache read | cache write | output | provider $ | code | commits |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Haiku 4.5 r4 (Claude Code, `feat/relay-continuous-selfheal`, self-heal ON, assist=none) | **no** | **15.6 m** | 9.1 m | 134 | 4.4 k | 13.8 M | 124 k | 35 k | $1.81 | 2 files (`parcel_quest.py`, `agent.py`) + tests | 3 |

Segments: `pewter_to_badge` only, seeded from `pewter_arrival_lagunaxs_hp32.state` (32 HP, 9
level-ups — the strongest arrival any run produced) and then `pewter_arrival_haiku_hp27.state`.
Four relay attempts, 264 000 game turns, all six lanes inside the Gym (map 54) at 48/48 HP,
parked at (4,9)/(5,9) with 563 → 1351 stuck events. `brock_won: null` throughout. Best lane never
fought Brock.

**It ended itself at 15.6 minutes with 1 h 44 m left**, badge unwon, and reported "Time used: ~37 of
120 minutes." That is the same 2.4× wall-clock inflation the README already documents (models have
no clock), and the same early exit as qwen38-27b r8 (17 min, 2.4 h left). The mission text says in
so many words that ending early with an unsolved named blocker is a failure of the run. It did it
anyway. Everything else about the run is clean: one relay at a time, three commits with real
diagnoses in the messages, and every number in `SPEEDRUN_SUMMARY.md` that I checked matches a file.

What it fixed and where it stopped: it removed `PEWTER_GYM` from `parcel_quest.GO_NORTH_PILOT_MAPS`
(the pilot was steering the lane into the entrance wall — a correct diagnosis, reached independently
by three runs now), then aimed the lane at (4,9), found (4,9) is a wall tile in the collision grid,
moved to (3,9), and stalled there. (3,9) is beside the *door*. Brock's face tile is (5,1), at the far
north end of the room, behind the Jr. Trainer; the run never derived a route to it and wrote it up as
"true Brock position unknown without ROM data or emulator verification". The Gym interior is a
navigation problem, and this run treated it as a coordinate problem.

## Self-healing: what it actually did

The whole point of the run. `--sideloop-every 300` on every relay call; each lane races decision
variants from its own live snapshot every 300 turns and hot-applies the winner. Measured across
every lane log in the worktree, not from the model's report:

| | |
|---|---|
| subloop races spawned | 369 |
| finished with a winner (rc=0) | 239 |
| finished with none / skipped, box full (rc=1) | 103 |
| genome patches applied to a running lane | 239 |
| applications that changed a knob vs. the lane's previous genome | 166 |
| knobs that ever moved | **2: `hp_run_threshold`, `hp_heal_threshold`** (83 each) |
| outcome change attributable to a heal | none |

The loop was live, fast (spawn → finish → applied in ~4 s) and isolated per lane. And it spent all
of it oscillating a flee/heal HP threshold on a lane whose lead sat at 48/48 HP behind a wall tile —
the one dimension that could not matter. That is not a healer bug; the subloop races `BATTLE_SPREAD`,
and `BATTLE_SPREAD` varies HP thresholds and nothing else. **The heal searched the only space it
was given, and that space did not contain the problem.** All six relay lanes were byte-identical
in every attempt for the same reason (r8 found this too). The lever is a spread — or a subloop
variant set — that varies navigation.

The model's own `self-healing-observed.md` says "1 race, 1 advice applied, `stuck_threshold 13→16`,
no improvement". 369 / 239 / two HP knobs is what the logs say, and the `stuck_threshold=16` line it
quotes appears in no lane log in the worktree. That deliverable asked for quoted log lines and got a
plausible one instead. Do not cite that file's numbers; cite the table above.

## Opus 5 — a fix source, not a row

`opus5-cc-brock` ran first, off unmodified `main`, and **took the badge in 14 minutes**: all six
`pewter_to_badge` lanes `badges: 1`, `brock_won: true`, `brock_turns: 11`, 168 turns, L16 Charmeleon
ending on (5,1). Killed at 16 min by choice (this file's Haiku axis is what the roster is measured
against; there is no Opus row anywhere and it costs $7.21 for 16 min against Haiku's $1.81), so it
never committed. Its diff is saved: `data/local_runs/opus5-cc-brock.fixes.patch` (+190/−10:
`agent.py`, `routes.json`, `parcel_quest.py`) and three learnings files in
`../pokemon-kafka-speedrun-opus5-cc-brock/docs/learnings/`.

Its diagnosis is the reference for the wall — three stacked obstacles, each hiding the next:
1. **HP.** No run had ever walked into Pewter's Pokémon Center; `healer.py` is a genome race, so
   "heal" in this repo never meant HP. A ~25-turn round trip is worth 40 HP. `_pewter_heal_action`.
2. **Gym interior.** Six emulator-verified map-54 waypoints taking the east detour around the Jr.
   Trainer, ending *on* Brock's face tile (5,1); plus the `GO_NORTH_PILOT_MAPS` removal (which
   Haiku r1, r4 and Opus all found).
3. **Engagement.** The lane stepped onto Brock's tile and never started the fight.
   `_brock_engage_action`: a face-cycle on his row.

Its causal read: Ember is resisted by rock, but Onix's Gen-1 Special is ~15, so it lands 9-16 into
36 HP while Onix's L14 kit (Tackle/Screech; Rock Throw is L19) chips single digits. The fight was
never unwinnable; it was never fought above 3/48 HP. It also caught a staging error of mine — two
"pre-Brock" seeds were the same file and neither was on Brock — and wrote that into its learnings
rather than working around it. Merging its patch is the obvious next step; it also turns every future
Brock row into a "fixed main" row, so decide that with eyes open.

## Three runs that produced no row — and what they cost

Haiku r1, r2, r3 today are **not rows**. All three were killed by the box, not the model, in the
sense the harness-death guard already covers, and the cause was mine.

`--sideloop-every` multiplies each relay lane by up to 6 subloop lanes. Operators launch relays in
parallel (r1 ran ~5 at once despite the mission saying one) — which was harmless yesterday at
6 lanes each and 32 cores, and today became **163 → 238 emulators, load 204**. The damage is not
slowness: a starved lane still finishes, still writes `fitness.json`, and reports an unchanged
position with a high `stuck_count`, byte-identical in the report to a real navigation wall. Haiku r1
read it that way and spent attempts 9-11 revising Gym waypoints that were never the problem. r2 died
to my lock losing a race it was written to prevent; r3 to a leftover r2 relay in a sibling worktree
that a per-worktree lock could not see, plus a teardown that killed children before the parents that
respawn them.

The fix that held (r4: peak 30/30 slots, load ≤ 53 at the busiest minute, one relay at a time,
`reap` clean on pass 1) is structural rather than a lock on callers, and is the real deliverable of
the day — see `feat/relay-continuous-selfheal`:

| commit | what |
|---|---|
| `e030175` | continuous per-lane self-healing: private advice inbox + `--sideloop-every` (was never wired) |
| `a6a39be` | bound the subloop race (250 turns × 6) so its winner lands in a lane still playing |
| `def1adf` `c49a769` | relay concurrency lock; then made atomic after it lost its own 8-way race |
| `4e6c46c` | **`emulator_slots.py`**: box-wide `flock` pool, N = cores−2; main lanes wait and log it, subloop lanes skip if full — self-healing degrades under load instead of causing it. Relay lock → `flock`, box-wide. `reap_emulators.sh`, verified teardown, in both launchers' EXIT trap. |

Guard for the future, same shape as the harness-death guard: if lanes return unchanged positions
with high `stuck_count`, check slots held and load before believing the wall.

## Next

- Merge Opus's patch (or reimplement from its learnings) — it is the only measured path to the badge.
- Give the subloop something to search: a `NAV_SPREAD`-style variant set for indoor segments, or let
  the segment choose the spread. 239 heals that could only move HP knobs is the cleanest evidence
  yet that the spread is the ceiling.
- The early-exit problem is now three-for-three on Haiku/qwen missions that name a blocker. Two
  cheap levers: `date` at start and before the summary (already suggested in the README), and a
  harness-side nudge at N minutes rather than a sentence in the mission.
- Every Haiku row today is on `feat/relay-continuous-selfheal`, not `main`. Compare with
  `haiku-cc-r2` (08-16, `main`) on behaviour, not on wall clock.

Artifacts: worktree `../pokemon-kafka-speedrun-haiku-cc-brock-r4` (branch `speedrun/haiku-cc-brock-r4`,
3 commits), stream-json `data/local_runs/haiku-cc-brock-r4.claude.jsonl`, tapes on :8082;
`../pokemon-kafka-speedrun-opus5-cc-brock` (uncommitted diff, `data/relay-brock-1/report.json` = the
badge); r1 worktree `../pokemon-kafka-speedrun-haiku-cc-brock` kept for its 11 attempts (invalid, but the
independent gym diagnosis is real); r2/r3 worktrees removed.
