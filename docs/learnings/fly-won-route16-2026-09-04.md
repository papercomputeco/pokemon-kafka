# HM02 FLY won — Route 16, 2026-09-04

**Baton:** `data/local_runs/roster-bench/fly_won_real.state` (map 188, the Route 16 house; bag holds
`HM01 CUT`, `HM02 FLY`). Verdict by bag growth (19 → 20) on the first talk, not by dialogue.

## The route, measured tile by tile

1. Route 16 (map 27) lower road, standing at (25,10) after Snorlax has gone.
2. **Walk east past (26,10) by hand** — the vacated Snorlax sprite slot still reads as a body, so
   `road.live_bodies` calls the road body-blocked while the cartridge lets you through.
3. **CUT the bush at (34,9)** (tile `0x3D`, the only cuttable thing on the map) from (34,10).
4. Upper road west to (25,4).
5. **Press INTO the gate** from (25,4)→(24,4)→(23,4): the warp sits on the path tile (`0x39`) in
   front of the wall (`0x4b`) and fires on the press into the wall, not on stepping onto the cell.
   → map 186 at (7,2).
6. Walk to (1,2); press into (0,2) → map 27 at (17,4), the upper strip.
7. West to (7,6); press up through the house door (7,5) → map 188.
8. Talk to the body at (2,3): *"Oh, you found my secret retreat! Please don't tell anyone I'm
   here."* → HM02 in the bag.

## Why every earlier Route 16 leg failed here

- The engine leg tried the gate's **lower** doors from the lower road twenty times; the upper
  doors are the ones that reach the house, and only after the Cut.
- Every door verdict was "no-path/refused" because the walker **stopped on the warp cell** and read
  the map. Route-gate doors need the second press.
- The branch was at the **20-stack bag cap**; the hand-over would have silently failed exactly as
  the Secret House did. The new bag engine (`room_plan` / `make_room`, called before every talk)
  freed a slot first — by tossing the NUGGET; the two stat-booster "use" attempts did not consume
  and are the next thing to measure.

## What this unlocks

Fly to Pallet + Surf down Route 21 is the short road to Cinnabar (never reached in 28 days),
bypassing Seafoam. This branch still needs HM03: Fly → Fuchsia → Secret House (map 222, NPC
(3,3)) → teach Surf → Fly → Pallet → Route 21. Each step is an existing engine leg.

## Engine gaps this measured (journal `map=27`)

- `live_bodies` needs the sprite hidden flag.
- A door/warp verb must press through the wall after stepping onto a route-gate warp tile.
- `make_room`'s "use" path (stat boosters) selected the item but the count did not drop.
