# Pewter (Badge 1) → Mt. Moon 1F via Route 3

Mission: from the seed `demo-runs/states/mtmoon_seeds/badge1_gym_hp6.state` (standing on Brock's
tile (5,1) in Pewter Gym, map 54, Badge 1 in hand, one Charmeleon L16 at 6/48 HP), get a
`badge_to_mtmoon` lane to `final_map_id: 59` and leave the baton
`<run>/batons/badge_to_mtmoon.state`.

| field | value |
|---|---|
| start | 2026-08-18 07:49 PDT (`date`) |
| harness | relay.py `--segments badge_to_mtmoon --sideloop-every 300`, NAV_SPREAD (6 lanes) |
| seed | badge1_gym_hp6.state (Pewter Gym, badge 1, hp 6/48) |

Obstacle files (written as they clear):

- `route3-heal-gating.md` — the 6/48 HP start with the heal trip gated off (it requires *not*
  having the badge): a faint on Route 3 is the only heal path, and it must land where the leg
  can be re-run.
- `route3-gym-exit.md` — leaving the gym west out the door with the badge (the map-54 waypoints
  are aimed at Brock, the map-2 waypoints are aimed at the gym door: both point the wrong way
  for this leg).
- `route3-crossing.md` — the Route 3 leg: Pewter east exit → Bikers / grass → Mt. Moon warps.

Outcome: **partial — best lane `final_map_id: 14`** (Route 3, progress 11 vs seed 9). The leg
reliably exits the gym, heals, dead-ends 55/57, and crosses into Route 3 via the city's east
door, then lives in the 2 <-> 14 pocket: probes confirmed 14's four edges are
west/south/north -> city and east -> solid, so **map 59 is unreachable from this seed through
any probed warp or edge** (see the 2026-08-18 probe campaign section below). Relay run
`data/relay/260818-162155`: all six lanes end `final_map_id: 14` at 6000 turns.

## 2026-08-18 probe campaign (probes 14-27, pokedex/log44-log56)

What the probes proved, in order:

1. **The gym door is a LAST_MAP mat, not a warp to map 2** (log44): pressing the (16,17)-side
   door with a strict `dest == 2` filter matches nothing; the door warps back "where we came
   from" and the lane loops 54 <-> 2.
2. **City (2) warps**: (13,25)->58 Center, (16,17)->54 Gym, (14,7)/(19,5)->52 Museum,
   (23,17)->56 Mart, (29,13)->55, (7,29)->57 (log18-20 era).
3. **55 and 57 are indoor dead-ends**: their only warp is the door back (LAST_MAP), confirmed
   under the settle gate (every probe re-confirms: enter, one door press, back).
4. **The city's east edge IS Route 3**: pressing off (39,16)-class rows drops the lane onto
   map 14 at (0,8) or (0,11); from 14, presses on the west/south/north edges land back in city
   at (13,26), (39,16) or (39,19) (log47/50/51/52, 54/55/56).
5. **Route 3 (14) is a CITY POCKET.** Its warp table is empty (engine-native adjacency), the
   entry pocket seals rows 9-11, the x=14/15 and x=22/23 wall columns open only at scattered
   rows (log49/51), and all four edges were swept:
   - west -> city (2), south -> city (2), north -> city (2) (log50/51/56: 47/900-turn
     bounce rate on the north edge alone), east -> SOLID wall (x>=23 never opens, probes
     twenty/twenty-two/twenty-five).
   Consequence: **map 59 (Mt. Moon 1F) is unreachable from this seed state through every
   edge and warp probed** (2, 13-via-city, 14, 55, 57, 58, 54). The best the leg can do is
   live in the 2 <-> 14 pocket (progress 10-11 vs seed 9).
6. **The A* pilot wedges on 14** (log44/46/47): mid-route wall columns defeat it; the
   row-by-row scan march (agent.py `_route_march`) is the only crossing that even makes
   x-progress, and it still ends in the pocket.

### Self-healing observations (captured from the lane logs this session)

- `MTMOON-HEAL ... door (13,25)` then `MAP CHANGE 2 -> 58` and `58 -> 2`: the one-shot heal
  gate + deferring the Center to the canonical heal flow works; the lane re-enters the city at
  (39,19) and the spring re-arms the east door within one visit.
- `BATTLE ... won=3` in probe23 (Pidgey on Route 3 tall grass at L9 against Charmeleon L16,
  HP 6 start): battles win when the lane survives the first hit; they are not the blocker.
- `MTMOON-MARCH | 14 pos=(22,12) east blocked, scanning rows` repeating without a "wall
  crossed": the x=22/23 column is the pocket's far wall, not a gate (scan exhausted all 18
  rows).
- `MTMOON-DEADEND | map=55 ... back to the door` / `map=57 ...`: dead-end backtracking fires
  exactly once per map per heal cycle, as designed.

### Code state at handoff

- `scripts/agent.py`: badge-gated `_mtmoon_action` (gym door -> city -> 55/57 dead-end
  backtracking -> east road door -> 14 march), the `_route_march` 3-stage march (south /
  north / east) with row-by-row wall scanning and edge sweeps, the city-spring re-arm, the
  one-shot heal-first gate, and the settle gate (first turn after any map change: defer).
- `scripts/evolve.py`: `MAP_PROGRESS` extended with 54:9, 14:10, 59:11.
- `scripts/relay.py`: `--seed-worldmap` argument for the pocket seed.
- `tests/test_agent_mtmoon.py`: 21 cases (gym door, city candidates, dead-end backtrack,
  heal-first, march scan/sweep/stage-advance, edge-hunt wrap, settle gate). 168 total green.
