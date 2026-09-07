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
2. **15→3, Route 15 → map 3 — SOLVED 2026-09-06.** The "13-cell pocket" was the model's, not the
   game's: the extraction dropped each connection's alignment byte, and the region router's
   nearest-open-cell guess entered map 3 at rows 12–13 while the game (measured: the leg stood at
   (3,0,18) after crossing from row 10) enters at row 18. `parse_map` now records
   `connection_offsets` (east/west: rows, north/south: columns, signed) — Route 15 → 3 is +8,
   Route 19 → 20 is −36, Cinnabar → Route 20 and Route 21 → Pallet are 0, all matching the
   measured crossings — and `region_route` enters the far map at the aligned cell. Live: Route 15's
   gate → 3 → map 63, both of its bodies heard (run fwd_l12_63).
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

## Map 3 after the alignment fix (2026-09-07, measured)

- The town's main region (378 cells, entered from Route 15 at rows 18–19) reaches the west edge,
  the north edge (35) and its doors. Its south and east sides are fenced: the tree line at row 28
  is 0x50 and the Cut flow there answers **"There isn't anything to CUT!"** (also at (25,9)); the
  two-cell gap at (16,28)/(17,28) leads onto 0x55/0x56 tiles that refuse the step silently; the
  x=32 column of 0x55 fences the east strip. So `CUT_TILES` is `{0x3D}` now — 0x50 was never
  measured cuttable (no `growth_cut` event ever recorded) and is measured not to be.
- The south edge (→16) belongs to the fenced SW strip (72 cells), entered from Route 15's rows
  13–17 (its south strip, 35 cells), which is not Route 15's main region either. Reaching 16/70 from
  the town means leaving by the west edge and coming back in through the other entry — the region
  router now emits one hop per far region an edge's aligned cells reach (#132), carrying the cell to
  cross at. Whether Route 15's south strip is reachable from anywhere but map 3's strip is the next
  measurement (the model says only via map 14's north edge at columns 57..63, which align to
  Route 15's columns 7..13, not to the strip).

## Route 15's south strip — measured 2026-09-07: no entry

- **Live from the south** (run 20260907-012441, `probe_strip`): map 10 → 16 at (11,35) → map 3 at
  (14,35) → Route 15 at (89,11). The leg came up through map 3's south/east part into the town and
  out at row 19 — the planner's own region from (14,35) is 632 cells and contains the town (378),
  while the town does not contain the south part: a one-way passage, town ← south part, that the
  grid's ledges explain. It never touched the SW strip: (0,21) is in neither region.
- **The only barrier into the SW strip** from the south part is the 0x50 tree column at x=10,
  rows 32–35. Cut at (10,35) from (11,35) and at (10,34) from (11,34): no change, no sentence
  (run 20260907-012649-aa79). Four 0x50 refusals on this map now.
- Route 15's south strip (x=81..89, rows 13–17, 35 cells) is sealed by rock (row 12, x=80) and a
  fenced pond; its south edge lands at x=136..139 on map 14, off the map. Its one neighbour is
  map 3's SW strip. **The pair has no entry.** Nothing routes to it and nothing is behind it.
- **The same shape holds for map 228's door** at map 3 (4,11): its pocket (rows 12–13) pairs with
  Route 15's north strip (row 4, x=76..89, plus rows 2–3/6 at x=76..79), which drains one-way over
  the row-5 ledge into Route 15's main region and is entered from nowhere else in the model. So
  228, and 226/227 behind it, are out of reach from any baton until a live entry is found — the
  candidates are tiles the extraction calls solid (0x11 pond, 0x55/0x56, 0x24 fence), none of which
  has opened under a press.
- Banks on an edge cell settle across the edge on reload (`probe_strip-3.state` at (3,14,35)
  boots on 16 at (4,0)); bank one step inside instead.

## Map 5's GIVE_UP cells — measured 2026-09-07: the ship has sailed

- Both cells, (5,15,6) and (5,18,29), are the same wall: the dock warps at (18,31)/(19,31) into
  map 94 (the S.S. Anne). The sailor at (19,30) says **"The ship set sail."** The six targets
  behind it (95, 99, 100, 102, 103, 104) are the ship's interior (94 → 95 → …).
- Every baton the sweep used carries HM01, and every one of them is told the same sentence: the
  ship is gone on that whole lineage. The seats' GIVE_UP was right.
- Batons from before the ship left do exist: `at_gym_v` (map 5 (11,4), two badges, S.S.TICKET,
  no HM01, Charmeleon L34 at 94 HP), `captain_room` (aboard, map 96) and `captain_done` (map
  101, HM01 in hand). Lane 13 ran the ship from `at_gym_v`: all six maps reached in 1–3 s each,
  50 bodies heard aboard (`forward_lane13.jsonl`).
- Do not record this door as dead: on a pre-HM01 run it is the way to HM01. It is a story state,
  and the sentence is the only honest marker until gates can carry a condition.

## Map 27's GIVE_UP cell — measured 2026-09-07: the Route 16 sleeper, then the road

- The cell (27,10) is beside the sleeper at (26,10): "A sleeping POKéMON blocks the way!" The
  lanes' batons (the 4-badge grind lineage) held no flute; the seats' GIVE_UP was right for them.
- With the flute (`fly_won-27`, `bicycle`): the wake path had three faults, each measured and fixed
  (branch `cycling-road`): the ITEM list remembers its scroll, so a second open started mid-list
  and reported "no bag item called 'POKe FLUTE'"; after "SNORLAX returned to the mountains!" the
  sprite table still listed the body while the step onto it went through (no single sprite byte
  separates a removed sprite from an off-screen one — `probe_r16_sprite_bytes`); and two
  equal-length region chains through a house door and its mat ping-ponged maps 19 and 80.
- Route 16's gate (186): "Excuse me! Wait up please! No pedestrians are allowed on CYCLING ROAD!"
  from the guard on row 5; the lower doors pass without it. A BICYCLE in the bag answers it.
- Cerulean's south side opens on the 0x3D bush at (19,28) — a cut works there — but the loaded
  model kept the cell solid and the next walk was no-path; a cut cell is floor now until the leg
  leaves the map.
- **Cycling Road (28) is a slope**: idle 120 frames carried the rider 13 rows; a sideways press
  steers one column; up is refused; column 1 ends in a dead end at (1,123) where every direction is
  refused with no box (and "You can't get off here." to the BICYCLE: the road puts you on it).
  `references/measured_slopes.json` + `road.safe_cells`: no step against the slide, and a plan may
  only stand where the goal is still reachable downhill. Live: (28,1,81) → map 29 in one hop.
- Reached: 28 (Cycling Road) and 29 (its south end). Map 187 is the gate's upper floor, reached
  from the lower floor's (6,12) - run from `r16_awake-28`.
