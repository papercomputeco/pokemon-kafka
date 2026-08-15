# Speedrun Summary — Route 1 → Mt. Moon (issue #70)

Harness/model: pi coding agent (Claude, Sonnet-class), operating the divide-and-conquer relay
(`scripts/relay.py`) against `rom/pokemon_red.gb`, driving up to 6 headless `scripts/agent.py`
lanes per segment. All Python invoked via `uv run`. No `paper`/`tapes` commands used; no pushes
or PRs opened.

## Segments reached

| Segment              | Result      | Winner lane | Turns | Notes |
|-----------------------|-------------|-------------|-------|-------|
| route1_to_forest      | ✅ conquered | `base`      | 750   | Fixed after a wild-battle RUN/menu-desync bug (see route2-battle-menu-desync-blackout.md); all 6 lanes then succeeded. |
| forest_to_pewter      | ✅ conquered | `base`      | 3253  | Failed at max_turns=6000 for all 6 lanes (turn-budget wall, not a decision bug); succeeded on relay's automatic 2x-turns retry (12000). |
| pewter_to_badge       | ❌ unresolved | —           | —     | Fixed a waypoint-index-reset bug that was replaying the whole early game after a whiteout, but the party still wedges at a fixed tile approaching the Pewter Gym door; see brock-approach-deadend-unresolved.md. No baton produced. |
| badge_to_mtmoon       | not attempted | —          | —     | Blocked upstream — needs a `pewter_to_badge` baton that was never produced. |

**Total game turns completed:** 750 (segment 1) + 3253 (segment 2) = **4003 turns** reaching
Pewter City with the Boulder Badge still unearned. Mt. Moon (map 59) was not reached.

**Wall clock spent:** approximately 55–65 minutes of the 2.5-hour budget (session ran from
~15:20 to ~16:10 local time), well under the stopping threshold. Stopped early because the
`pewter_to_badge` obstacle needed either better ground-truth map data (the routes.json Gym-door
coordinate could not be verified as correct or incorrect without visual access to the game) or a
non-trivial new feature (Pokemon Center interior interaction, which the codebase doesn't have at
all — compare the existing Oak's-Lab state machine, which has no analogue for a nurse visit), and
further coordinate-guessing was producing no forward progress (see failed attempts in
brock-approach-deadend-unresolved.md).

## What blocked us

1. **Fixed:** A wild-battle `RUN` action wasn't confirmed the way `FIGHT` already was, so a
   fixed-timing menu press could silently fail to register (eaten by an extra text box from a
   status move like String Shot), freezing HP and the loop for thousands of turns on Route 2
   before ever reaching Viridian Forest. Fixed in `scripts/agent.py` (retry-and-confirm loop for
   `run`, plus a periodic `unstick` in the wild-battle stall watchdog).
2. **Not a bug, a budget issue:** Viridian Forest + the rest of Route 2, crossed by a low-level,
   itemless, critical-HP party, takes several thousand turns of stuck-recovery and combat before
   reaching Pewter — relay's built-in 2x-turns retry handled it without any code change.
3. **Fixed:** `Navigator.current_waypoint` always reset to 0 on a fresh `agent.py` process
   (every relay segment after the first is a fresh process), which is the map's *entry door*
   waypoint — sending an already-deep-in-the-map party straight back out the way it came, into a
   full early-game replay once the parcel-quest phase logic (correctly, but expensively) decided
   the way back to Pewter is the whole original route. Fixed via
   `Navigator._initial_waypoint_index`, which picks the nearest non-entry waypoint by distance
   from the actual load-state position, only on the very first call.
4. **Unresolved:** After that fix, the party still gets wedged at (17,11) in Pewter City
   pressing "left" toward the routes.json-documented Gym door (16,11) forever — a real wall.
   Approaching from below (the standard Gen-1 building-door convention) moved the sprite onto
   the door tile but never triggered a warp, and continuing to press "up" just walked further
   north with no result; a generic whole-map frontier-exploration fallback also failed to
   route around the wedge from that exact position (every direction it suggested from there also
   failed to move the sprite). Either the routes.json coordinate for the Gym is wrong for this
   map, or the true approach requires routing around the building's footprint in a way neither
   the local 9x10 A* nor the whole-map planner discovered from the tested starting positions.
   Separately, we identified — but did not fix — that the party is likely already poisoned from
   the forest crossing (no potions/antidote, no Pokemon Center visit ever completed), which
   causes an independent whiteout mid-city; curing that requires new Pokemon-Center-interior
   interaction logic the codebase doesn't have yet.

## Exact commands run, in order

```
uv run python scripts/relay.py rom/pokemon_red.gb --dry-run

uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest \
  --max-turns-scale 0.5 --timeout 900
  # (first pass failed 0/6 — pre-fix; see route2-battle-menu-desync-blackout.md)

# fix: scripts/agent.py RUN-action confirm-and-retry + wild-battle unstick watchdog
uv run pytest -q -x tests/test_relay.py
uv run pytest -q -x tests/ -k "agent or relay"

uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest \
  --max-turns-scale 0.5 --timeout 900 --run-dir data/relay/seg1_smoke2
  # 6/6 lanes SUCCESS, winner base, turns=750

uv run python scripts/relay.py rom/pokemon_red.gb --segments forest_to_pewter \
  --seed-state data/relay/seg1_smoke2/batons/route1_to_forest.state --timeout 1200 \
  --run-dir data/relay/seg2
  # attempt 1 (max_turns=6000): 0/6 — turn-budget wall
  # attempt 2 (max_turns=12000, relay's automatic retry): winner base, turns=3253

uv run python scripts/relay.py rom/pokemon_red.gb --segments pewter_to_badge \
  --seed-state data/relay/seg2/batons/forest_to_pewter.state --timeout 1200 \
  --run-dir data/relay/seg3
  # 0/6 both attempts — full early-game replay loop (pre waypoint-index fix)

# fix: scripts/agent.py Navigator._initial_waypoint_index
uv run pytest -q -x tests/ -k "agent or relay"

uv run python scripts/relay.py rom/pokemon_red.gb --segments pewter_to_badge \
  --seed-state data/relay/seg2/batons/forest_to_pewter.state --timeout 1200 \
  --run-dir data/relay/seg3c
  # 0/6 both attempts — now wedges at (17,11) instead of replaying, lead_hp 0 (whiteout)

# manual single-lane probes (uv run python scripts/agent.py ... --load-state
# data/relay/seg2/batons/forest_to_pewter.state --max-turns <N> --stop-on-badge 1) to diagnose
# the (17,11) wedge: tried a below-door "up" approach (data/relay/seg3_probe4..6), tried a
# generic stuck>60-turns explore_step fallback with debug instrumentation — all inconclusive
# or regressive; reverted the Pewter/Gym-specific coordinate assumptions, kept the generic
# explore_step fallback (harmless, doesn't fix this case) and the two confirmed fixes above.

uv run pytest -q -x tests/ -k "agent or relay"   # 431 passed, final regression check

uv run python scripts/relay.py rom/pokemon_red.gb --segments pewter_to_badge \
  --seed-state data/relay/seg2/batons/forest_to_pewter.state --timeout 1200 \
  --run-dir data/relay/seg3d
  # 0/6 both attempts — confirms the (17,11) wedge persists; stopped here, documented unresolved

# regression check that segment 1 still passes with the final scripts/agent.py:
uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest \
  --max-turns-scale 0.5 --timeout 500 --run-dir data/relay/regression_check
  # 6/6 SUCCESS, winner base, turns=750 — confirms no regression
```

## Deliverables

- `docs/learnings/route2-battle-menu-desync-blackout.md` — battle, resolved.
- `docs/learnings/viridian-forest-turn-budget-wall.md` — navigation+battle, resolved (no code
  change needed, relay's automatic retry sufficed).
- `docs/learnings/pewter-waypoint-index-reset-loop.md` — navigation, resolved.
- `docs/learnings/brock-approach-deadend-unresolved.md` — navigation (blocking Brock), unresolved.
- `docs/learnings/route3-mtmoon-untested.md` — navigation, not attempted (blocked upstream).
- `docs/learnings/SPEEDRUN_SUMMARY.md` — this file.
- Code changes: `scripts/agent.py` (RUN-action confirm-and-retry, wild-battle stall `unstick`
  watchdog, `Navigator._initial_waypoint_index`, generic stuck-escape `explore_step` fallback).
  `uv run pytest -q -x tests/test_relay.py` and the full `agent`/`relay` test selection pass
  (431 passed) with these changes in place.
