# 2026-09-02 — the crew against solo analysis: 121 legs, and the arc that talked

**This file deviates from the house column set on purpose.** The standard table
(segs / wall / model time / turns / out tok/s / $ / Wh) compares *models running the same leg*.
This compares two **modes of work** over the same three days — a local-model crew running legs
against the cartridge, versus an Anthropic model reasoning about it between legs — so the
comparable unit is a leg outcome and a recorded observation, not a token rate. Rows here are not
comparable with the model-matrix files; they answer a different question.

Window **2026-08-30 19:09 → 2026-09-02 18:05 UTC**. Source: `data/telemetry/game/*.jsonl`, all
figures re-derived from the sink rather than from session notes. Published companion:
<https://claude.ai/code/artifact/fc0ee20f-f5cb-4f9c-847b-01de6705f02a>.

## The headline: engagement and outcome moved together

Every conversation with a body lands in the sink. Split by story arc:

| arc | bodies engaged | maps | outcome |
|---|---|---|---|
| badge 6 — Silph / Saffron | **82** (178:25, 210:22, 212:9, 207:9, 213:6, 208:5, 182:3, 234:3) | 8 | **badge won** |
| badge 7 — the sea route | **0** (7:0, 30:0, 31:0, 8:0, 166:0, 154:0) | 6 | five legs lost |

Same crew, same engine, same ladder. Not a gradient — a total split. Map 30's own exhaustion
record listed ten live bodies and used them only as obstacles to route around; the cartridge's
object data calls all ten `trainer`, and two sit adjacent to walkable cells. The first time
anyone spoke to one it answered.

## Throughput

| outcome | legs | share |
|---|---|---|
| arrived (reached the goal map) | 81 | 67% |
| exhausted (ladder ended, record written) | 14 | 12% |
| gave-up (seat chose to stop) | 12 | 10% |
| engaged-no-badge | 8 | 7% |
| budget expired | 4 | 3% |
| heal-refused / max-hops | 2 | 2% |
| **total** | **121** | |

The 14 exhaustions are the point, not the failure: each wrote a dated document with the facts at
the point of failure and every action tried.

## Seats, scored on their own traffic

175 consults — 112 navigation, 63 puzzle. An unparsed reply is a non-answer; the leg moves
nothing rather than acting on whatever sits first in the menu.

| seat | model | answered | rate |
|---|---|---|---|
| The Point Man | `qwen38-27b-128k` | 96 / 105 | **91%** |
| The Extractor | `kimi-k2.6:cloud` | 35 / 57 | 61% |
| (deterministic control) | `--no-consult` | 0 / 13 | by design |

Most-chosen actions: `WAIT_FOR_BODIES` 38, `BACK_OUT_AND_REENTER` 24, `TALK_TO_BLOCKER` 17,
`TRY_FAR_EDGE_CELL` 13, `USE_GATE_WARP` 12, `GIVE_UP` 12, `ORACLE_SEARCH`/`RETRY_SAME` 12,
`SWEEP_ITEMS` 3. The top pick is *wait for a body to wander off* — a cheap physical move against
the running game.

## The ledger

**Crew delivered:** badge 6 (CARD KEY → Giovanni → Sabrina); the deepest progress on the sea route
(map 31, x=87 → x=52 of 100); the crossing geometry that explained four failures (map 30's west
edge opens on **rows 40–52 only**, approach on row 10, solid notch at rows 38–39); Fuchsia's
Center found by interior template (map 154); the fainted-surfer diagnosis; the **BIKE VOUCHER**
from the Fan Club; and 14 written exhaustion records.

**Solo analysis delivered:** the lying arm boolean (`_arm_surf` returned True on a refusal and the
text box then froze all input — three legs had written the resulting frozen world into
`docs/learnings/` as a "water/rock checkerboard"); `knows_move()` (find the surfer by move id, not
a species literal); encounters-are-not-walls in `surf_cross`; the Investigator seat and the recon
step; `counter_stands` and the mart census below.

**Solo analysis lost time to:** a RAM-flag hunt that dead-ended (11 candidates, none flipped when
surfing; the live diff was 756 bytes of sprite shadow); hand-computed route chains that removed
the navigation problem from the navigation seat and pinned map 28, dragging a leg back to a hop
its own `_reroute_around` had correctly abandoned; a constant written from assumption
(`CURSOR_TILE`, right by luck); and a wrong figure propagated into a mission ("the island is six
cells" — it is 43).

## Why, structurally

1. **A leg is an experiment; an analysis is a hypothesis.** All 121 legs ran against the real
   cartridge and emitted measured facts whether they won or lost.
2. **The harness can lie, and only contact catches it.** Three legs' worth of "measured geography"
   was an artefact of one boolean. The check that caught it was physical: press a direction and
   see whether the world accepts input at all.
3. **Cheap physical moves beat expensive inference.** Which tile is water was settled by four
   button presses, after a ROM-table hunt and a RAM diff had both failed to answer it.

## The exemplar, end to end

The **counter** finding is the clearest instance of the division that works. The crew ran the
recon, got the voucher, reached the shop and reported `body (6,2) unreachable/no response`. That
observation — which only exists because someone was standing in the room — named a reusable engine
gap: you talk to a clerk *across* a counter, two tiles away, the geometry `center_counter` already
hard-coded for Pokémon Center nurses and nobody generalised. A census then sized it: 778 bodies
have a walkable neighbour, **15 have none but do have a walkable counter-stand**, and seven of
those sit at exactly (0,5) in an 8×8 tileset-2 room — one per city. It is the MART template, and
`quartermaster.buy()` had existed the whole time against **zero purchase events in the entire
telemetry history** and ₽92,360 unspent.

Neither mode gets there alone: the crew produced the observation and would not have written the
census; the analysis wrote the census and would never have been standing in the shop.

## What this is not

1. **Not a controlled A/B.** Silph is a sprite-dense interior; the sea route is open water with
   ten bodies across 54 rows. The 82-vs-0 split is a strong signal, not an isolated variable.
2. **The crew did not talk on the water arc either.** The zero belongs to everyone who worked it.
   The finding is about the mode of work, not about which model sat in the seat.
3. **Badges 7 and 8 are unwon.** Six of eight stand; "outperformed" is relative progress inside an
   unfinished job.
4. **Commit counts are not value.** 25 of 39 commits in the window carry the Claude session
   trailer, and several were corrections to its own errors.
5. **Seat rates are not head-to-head.** The Extractor is consulted only after navigation has failed
   twice, so it sees a strictly harder problem set.
