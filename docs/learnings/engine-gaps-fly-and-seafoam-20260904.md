# Fly and Seafoam legs: six engine gaps measured and closed in one day (2026-09-04)

All runs under `scripts/supervisor.py run` with the crew (tapes proxy on :42345). Hand-driving
was used only to measure a flow the engine lacked; every fix landed in `scripts/` with a test.

## Facts the cartridge gave up today

| where | what the game said / did | consequence |
|---|---|---|
| Fuchsia map 155 (2,3) | "gave the GOLD TEETH to the WARDEN!" -> HM04 in the bag | Strength won; `strength_won.state`, taught to Gyarados: `strength_taught.state` |
| Route 7 (map 18) | door (18,9) is dead; (18,10) is a threshold warp into gate 76 when stepping LEFT off it; west edge to Celadon opens on rows 2-3 only, beyond the gate | `celadon_from_route7.state`; a `--no-consult` leg from Saffron now crosses cleanly |
| Route 16 (map 27) (26,10) | "A sleeping POKéMON blocks the way!" -> POKé FLUTE -> "SNORLAX returned to the mountains!" | the sprite slot stays populated after it leaves (phantom body in `bodies()`), but it no longer blocks |
| Route 16 gate (186), from the lower east door | survey: 18 cells, exits only back east and up the stairs to 187; the guard at (4,7): "Excuse me! Wait up please" | the upper corridor (rows 2-3) is sealed from the lower one; the Fly house strip is not entered through the gate's inside |
| Route 16 tree row 9 | tile 0x3D at (34,9) -- the one Cut bush in the row | the entrance to the upper level from the lower road; nothing else on the map is cuttable |
| Route 19 (map 30) beach | three ledge rows between the beach strip (row 0) and the plaza (rows 6-9); the plaza touches the sea on row 10 | a flood fill without ledge hops called the shore unreachable |
| Strength lineage party | Gyarados' moves are Splash / Tackle / Bite / Strength; no HM03 in the bag | **this branch cannot surf**; the surfing Gyarados belongs to the Seafoam branch (`m31_manual`, `seafoam_*`) |
| Safari Center (220) | the pond row 9 cuts the east side: the entry region (rows 10-25) reaches 217/221/156 only; 218's door (14,0) is in the north half, 219's (0,10) in the sealed west half | the way to Safari West is 220 -> 217 -> 218 -> 219 (worked as far as 218) |
| Safari step limit | ejected to 156 mid-leg; re-entry then refused at 156 -> 220 | a leg into the Safari must be short, or the entry flow (pay, "join the hunt?") needs an engine verb |

## What was added to the engine

- `supervisor --hunt-item NAME`: judge a leg on a body handing over an item; the goal chain is the doors it might be behind.
- `Rig.teach(machine, species)`: the measured TM/HM flow; `Rig.cursor_to` for non-scrolling menus (the scroll register keeps the bag's offset in a banked state and broke `lead_swap` and the roster).
- `road.shore_stand` + `surf_cross` arming from a land cell that touches edge-reaching water, not wherever the straight line stopped ("There's no place to get off!").
- `road.reachable` hops one-way ledges like `rom_truth.path_on_map` already did.
- `_wake_sleeper`: a blocker whose line says "sleeping" gets the flute from the bag; `_menu_key` folds the screen's "POKé" onto the decoder's "POKe" (the flute was "not in the bag" before that).
- Gate pass for WARP hops severed by the map's own gate building, and `traverse_interior` tries every door on a side (a gate can carry two corridors).
- `_cut_through`: a 0x3D / 0x50 growth touching our region whose far side reaches the target is cut from the nearest cell (`Rig.cut` -> `road.cut_until_open`), proved by the step.

## Still open

- Fly: the Route 16 leg from inside the gate must exit east, cut (34,9), enter the gate's upper east door and leave by its upper west door to the house at (7,5). Running at time of writing.
- Seafoam: this branch needs HM03 from the Secret House (222) and then the 30 -> 31 crossing; the lineage with a surfer is at Seafoam 4F beside the boulders but has no Strength.
- Vermilion's map 92 (the other Fly lead) needs a surfer in Vermilion; no branch has both.
- A gone sprite (Snorlax) still reads as a body; `live_bodies` should learn the hidden flag.
