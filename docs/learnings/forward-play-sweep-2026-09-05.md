# Forward-play sweep into the no-save maps — 2026-09-05/06

Goal: hear the bodies on the 93 unheard maps that had no banked save (the Forger's thinnest
data), by walking there from healthy batons with `supervisor.py run --engage --sweep-items`.
Plan/rows/logs: `data/replay_arcs/forward_sweep*.json`, `forward_lane<N>.jsonl`, `logs/fwd_l<N>_<map>.log`.
Lane runner: `data/replay_arcs/forward_lane.sh` (one single-goal leg per map, banks on arrival, the
next leg boots the last *arrived* bank; `map@baton` tokens re-seed a leg from a named baton).

## Result

| | |
|---|---|
| target maps | 87 route-reachable (+6 with no route from any baton: 173, 69, 78, 75, 239, 240) |
| legs run / arrived | 140 / 65 maps reached |
| body dialogues recorded by the sweep | 983 on 73 maps |
| battle outcomes / items collected | 353 / 18 (no item tossed; bag-full skips with `store_at_pc`) |
| catalog after rebuild | 818 of 922 bodies have a sentence, on 167 of 213 maps (600 on 119 before) |
| unheard maps with no save left | 38 (was 93) |

Legs finish in 2–10 s when the route is clean (headless PyBoy is unthrottled); a wall costs the
whole 1000 s budget, and one consult to the Extractor can run past it (lane 4, map 81: the outer
`timeout 1300` cut a leg 300 s over budget — the budget is checked between hops, not inside a consult).

## Engine fixes shipped tonight (each measured live, each with tests, gate at 100 %)

- **7231b5c** — north/south WATER edges (32→0, Route 21→Pallet): `_water_cross` routes the edge
  row's columns; `_board_water` walks to the shore and arms before routing; surf_cross routes first.
- **2e7e920** — SHORE edges (8→31, Cinnabar→Route 20): land rows AND water rows on one edge line go
  to surf, not to "wall" (`edge_has_water`). ~50 legs routed through this hop.
- **bc5d8a4** — a wild drawn on the shore step is fought before the arm.
- **d5c120b** — `WATER_TILES = {0x14, 0x32}` by measurement: 0x32 surfs (probe_tile32, three
  steps on Route 21); 0x11 is a fenced pond, refused 103× on map 15; island hop in surf_cross;
  `Rig._arm_surf` fights a battle that opens under the arm (swimmer ambush at 31 (24,14)).
- **d0c0911 / 6223ddc / 13fdf57** — `road.region_route` + `LegRunner._next_hop`: once a wall on
  the map chain is measured, route by *reachable region* (the walk's flood fill, one-way ledges and
  door tiles included; LAST_MAP mats resolve by warp index); a "back out the way in" mat toward a
  map with a measured wall is routed the same way; `_reroute_around` asks the region router before
  it bans, and bans the hop's own pair. 214 region routings fired in the sweep.

## Walls that remain (measured, not guessed)

1. **31→30, Route 20 → Route 19 — SOLVED 2026-09-06 (branch seafoam-crossing).** The west sea
   stops at x=61, the east sea starts at x=63, and the island between is fenced from the west sea.
   The crossing is through the Seafoam cave, and the region router now finds and drives it live in
   one leg with no consults (run probe_seafoam_cross4, landed (30,0,41)): door (58,9) → 1F east
   pocket → hole → B1 → B2 → B3 east → the 0x15 launch at (23,9) → the conveyor → B4 (20,15) →
   the 0x15 shore at (23,5) → central land → stairs (11,7) → B3 west → (5,12) → B2 → B1 → 1F west
   → mat (4,17) → the NE shore → east sea → 30. What it took: surf-aware regions
   (`road.surf_region`), mats returning to the OUTDOOR map, entry over water at the aligned water
   cell, sticky region mode per leg, no sibling-door swaps in region mode, the tileset-17 shore
   rule (water↔land only through 0x15: `SHORE_TILES`) and measured currents
   (`references/measured_currents.json`) as hops. Lanes 3–8 of the sweep had been re-seeded from
   mainland batons to avoid this hop; the west-side batons can now route east.
2. **15→3, Route 15 → Fuchsia.** Route 15 is two halves joined through the gate (59) and its upper
   floor (60); the region router finds that. But Fuchsia's west entry is a 13-cell pocket in the
   model whose only exit is the door (4,11)→228; the town is not reachable from it. Either the
   grid is wrong there or the game gates it — read the screen at (3, 0..4, 12..13) next.
3. **13→46 on Route 13.** The north edge IS reachable from (3,44) (the leg crossed 13→2 after the
   ban) but the walk to the door at (12,9) is no-path from both halves: a door-approach problem,
   not a pocket one. Map 48 has no route from any healthy baton at all.
4. **Map 5 legs** (targets 95, 99, 100, 102–104): two lanes gave up at (5,18,29)/(5,15,6) from
   different batons — unread; the seats chose GIVE_UP on 5→? hops. Map 27 at (27,27,10) for 28/187,
   map 10 at (20,8) for 179, map 23 at (12,40) for 189: same shape, unread.

## What to do next

- Pocket-level crossing of Route 20 via the Seafoam cave (warps 31→192/…→31 east), then re-run
  the 6 west-side targets from `probe_r20-31.state`.
- Read the refusals at the four GIVE_UP cells above with a probe before writing any code.
- Re-index the batons (`probe_baton_index.py`, WITH settle) so `npc_catalog.py report` sees
  tonight's 60+ `fwd_l*` banks as "batons standing here".
