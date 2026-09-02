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

## Session update (later the same day, badge7 crew)

**Banked baton now: `b7_badge_clean.state`** — map 30 (6,7), on the land island, 6 badges
(0x3F), in_battle False. Party: Gyarados L20 73/73 (the ONLY SURF user, lead), Dugtrio L100
259, Primeape L99 300, Pidgeot L99 347, Hypno L99 341, Charizard L100 341. **Bag: 0 balls**
(measured, ids 1–4 all count 0). So any catch-gate must be fought; the Gyarados-surfer + the
strong team can handle a fight-gate.

**New measured facts (this session, not recalled):**

- **The "island" (map 30, x4–13, y6–9) is walkable LAND, not water.** The player walks it
  (grass-encounter steps). The SEA is the non-walkable ring *around* it: tile `1` = surf-able
  water, tile `4` = solid rock/cliff, laid out as a **checkerboard** (water/rock/water/rock). So
  surf navigation is a water/rock maze, not an open sea.
- **The island's west shore (x4) is blocked by a cliff** (x3 = tile `4` at y6–9), so there is no
  clean surf-out to the west on rows 6–9. Surrounding water tiles (`1`) are adjacent to the
  island's south (x4/x6/x8.., y10) and north (y5) and east (x14) shores — those are the
  surf-able edges.
- **SURF arming was the first failure, now fixed.** `use_field_move`/`menu_row_of` read the field
  submenu off the sticky window layer and returned `None` on a clean baton → stuck-on-edge. Replaced
  with `Rig.surf_facing()`: a fixed keystroke (START → POKeMON [row 1, the one nav, read off the
  trustworthy ADDR_MENU_CUR] → A/up → A/up → A), no window text. Measured fact it rests on: Gyarados
  is party index 0 and its field submenu opens on SURF (top of both menus). `surf_cross`'s water
  step is the real predicate. **Committed `0062e02`.** After the fix, surf arming works (water
  movement is observed); the remaining difficulty is the water/rock checkerboard navigation with
  encounter-canceled steps, not the arming.

**Remaining blockers (in order):**
1. **The Cinnabar crossing** — surf the water/rock checkerboard across map 30's sea → map 31 →
   Cinnabar (8), handling water encounters. This is the unsolved navigation; the arming no longer
   is.
2. **Blaine's gym (166)** — the Gengar in front is a fight (not a catch) gate; the strong team
   handles it. Blaine himself: strong team should win.
3. **The Viridian chain** — a *second* sea crossing (8 → 32/0/12/1) then Giovanni's gym (45).

**What the next attempt needs:** a robust surf driver that (a) picks a surf-able shore edge (tile
`1` adjacent to the island), (b) steps with SURF armed, (c) on an encounter-canceled step fights
and re-steps (not give-up — `surf_cross` still treats a cancelled step as "refused", which is the
open `road.py` bug), (d) navigates the water/rock maze to map 31. Then badges 7 and 8 are both
winnable by the existing strong team.

## Original open questions the leg must answer by measurement, not by memory

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
