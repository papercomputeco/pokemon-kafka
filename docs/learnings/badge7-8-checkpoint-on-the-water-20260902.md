# Badge 7+8 leg: checkpoint on the water (2026-09-02)

Operator: badge7 crew (pi, session 56e38c2a). Written mid-leg; the loop continues from the
facts below rather than from memory of this document.

## Measured world (rom_truth queries, this session)

- **Route to the target, extracted from this cartridge:** 30 --west edge--> 31 --west edge-->
  8 --warp (18,3)--> 166.
- **Map 30** (20 wide x 54 tall, tileset 0): connections `north -> 7` (Fuchsia) and `west -> 31`.
  No warps. Trainers on screen: (8,7), (13,7), (9,11), (13,25), (4,27), (16,31), (8..11, 42..44).
- **Map 31** (100 x 18, tileset 0): connections `west -> 8`, `east -> 30`. Its warps `[48,5 ->
  192]`, `[58,9 -> 192]` are the route-12 gate pair (an interior, not our goal). The land plaza
  sits mid-map (~cols 68-81, rows 3-13); everything else is deep water.
- **Map 8** (Cinnabar, 20 x 18): connections `north -> 32`, `east -> 31`. Warps: `[6,3 -> 165]`
  (center, presumably), `[18,3 -> 166]`, `[6,9 -> 167]`, `[11,11 -> 171]`, `[15,11 -> 172]`.
- **Map 166** (20 x 18, tileset 22, no edges): 9 trainer sprites — leader candidate (3,3) pic 10,
  six more pic 12 at (17,2), (17,8), (11,4), (11,8), (11,14), (3,8), (3,14) — plus one npc (16,13).
  Exit warps (16,17) and (17,17) -> map 255. **This is Blaine's gym; badge 7 is inside.**
- Map 255: not yet queried (the gym's exit target).
- Viridian (map 1) gym door condition still UNVERIFIED — measure the door sentence, don't assume.

## Party / roles (per the baton, `b7_surfing.state`, map 30 at (6,7), on the water)

Gyarados L20 73/73 (the SURFER, off lead), Dugtrio L100 (the fighter, the LEAD), Primeape L99,
Pidgeot L99, Hypno L99, Charizard L100. Bag: HM03 SURF, HM01 CUT, OLD ROD, CARD KEY, SILPH SCOPE,
POKe FLUTE, S.S.TICKET. **No balls in bag** — any "catch it to open the gate" gate cannot be
solved by capture this leg; it must be fought or read around.

Roles doctrine (measured, from the last leg's own failure): the lead takes the crossing
encounters; Gyarados stays awake and off the lead; SURF is armed with
`use_field_move("SURF", species="Gyarados")`. Commit ec1200e made `_arm_surf` ask by species
and remember the answerer; `surf_cross` and `cross()` route through it.

## What already failed, and why (so the leg does not repeat it)

1. The 05:19 run reached map 30 (6,0) from the (6,7) baton and then returned
   `surfmoved-failed` on the hop 30 -> 31 ("OPEN EDGE CELLS toward 31 (step left): []"). The
   planner asks for *walkable* edge cells; the cells to the west on that row are deep water,
   so a walk plan is never found and the surf plan is never reached. See
   `map30-to-166-stuck-20260902-051959-8041.md`.
2. The leg before that put Gyarados on the lead to win the crossing fights; it lost at L20,
   fainted, and became unselectable in the POKeMON menu — the only surfer gone.

## Open questions the leg must answer by measurement, not by memory

- How does `cross()`/`surf_cross` decide that an edge hop is surfable? (road.py + rig.cross)
- Can map 31's land plaza be reached from the water (surf onto shore tiles, or the water is
  continuous across it)?
- What does map 8's north edge look like after surf landing from map 31? Where is the (18,3)
  gym-door warp relative to where the surfer comes in from?
- Does the Cinnabar gym (166) open with 6 badges, or is there a named gate (read the door)?
- From 255 (gym exit) or map 8, what is the chain to map 1 (Viridian)?

## Plan for the rest of the budget

1. Read `road.surf_cross`, `rig.cross`, `rig._surf_or_fail` and the 05:19 supervisor log for the
   exact failure site.
2. Fix the edge-hop surf path so 30 (land strip) -> 31 (water) -> 8 (Cinnabar) completes.
3. Engage Blaine at (3,3) of 166 (door at 8's (18,3)); win badge 7 (BADGES -> 0b01111111).
4. Chain to map 1, measure the gym door, engage Giovanni, win badge 8 (BADGES -> 0b11111111).
5. Bank badges, tape, learnings. Commit as each lands.
