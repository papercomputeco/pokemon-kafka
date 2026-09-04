# Map 92 (Vermilion) is a SURF-only island pocket — this baton cannot reach it (2026-09-03)

run_id 042a4c8 · baton `data/local_runs/roster-bench/bike_vermilion.state` · map 5 (Vermilion, `VERMILION_CITY_MAP = 5`, relay.py + agent.py) · party Charizard/Dugtrio/Gloom/Primeape/Pidgeot/Hypno, badges 63

## The question

Mission: enter **map 92** — "a building never entered in Vermilion City; warp at map 5 (12,19)" — engage all 5 bodies (4 trainers + 1 NPC), grab **FLY** (the mission label said "HM04 FLY"; in this ROM **FLY is HM02** — `fly_hunt` cites the cartridge: "received HM02! HM02 is FLY!" — while **HM04 is STRENGTH**, the Warden/Safari item. The *location* (map 92, door at map 5 (12,19)) matches the mission exactly; only the HM index was mis-stated.). Fallback: Route 16 (map 28) via `5→17→10→18→6→27→28`, with CUT.

## Numbering, so nobody re-trips on it (2026-09-03)

In this Red/Blue ROM the HMs are the official Gen 1 set: **HM01 CUT, HM02 FLY, HM03 SURF, HM04 STRENGTH.** FLY = HM02. If a later leg reports "HM04 FLY" it is mislabelled STRENGTH-as-FLY; check `Rig.bag_named()` for the actual item name before acting. The project's own `operator_prompt_fly_hunt.md` (the authoritative, cartridge-text-backed brief) names the FLY giver as the **"secret retreat ... over the water"** — which is exactly the SURF-island layout found here, and lists `Route 16 (map 28)` as the alternate, with **"a shrub you need CUT to clear."**

## Other FLY leads this project has (for routing, not verified as the same item)

- **Map 30, our own island** — `fly_hunt`: ten never-engaged trainer sprites; the "secret retreat" FLY text cluster. Baton `b8_BATON_island_gyarados_safe.state`.
- **Map 93 (5,2)** — `bike-sweep2` discovery 2026-09-02: *"I getting my PIDGEY to fly a letter to SAFFRON in the north!"* — a FLY/Pidgey clue in the same Vermilion cluster as map 92.
- **Route 16 (map 28)** — the designated fallback; the previous `fly-vermilion` run walked `5→17` and was **refused at the 17→10 cross** (a CUT shrub per `fly_hunt`), then called it **`fly_not_found`**.

## The verdict (measured, not recalled)

**The door (12,19)→map 92 sits in a 42-cell pocket that is walk-SEALED off the 363-cell road.** Its only non-solid boundary cells are `0x14`, which the engine classifies as water. The baton has **no Gyarados and no SURF user** (read from RAM). There is **exactly one warp in the whole ROM into map 92** — the (12,19) door — so there is no alternate entrance. Map 92 is a **secret island: SURF the `0x14`, step onto the `0x39` land, and the `0x1b` door is on the far (north) face.** Not enterable by this party.

So the primary objective (get FLY from map 92) is **not achievable with this baton**. The honest state is: *gated by SURF; the baton lacks a surfer.*

## The pocket, cell by cell (map 5, `.` = walkable grid, `#` = solid, D = door)

```
       x6  x7  x8  x9  x10 x11 x12 x13 x14 x15  x16
y17   39. 39. 15# 17# 17# 17# 17# 18# 39. 39.  39.
y18   39. 39. 0f# 22# 22# 22# 22# 22# 2c. 3d#  32#
y19   55# 56# 4e# 1a# 1a# 1a# 1bD 1a# 50# 2c.  32#
y20   39. 39. 39. 39. 39. 39. 39. 39. 39. 39.  32#
y21   39. 39. 39. 39. 39. 39. 39. 39. 39. 39.  32#
y22   39. 39. 39. 39. 39. 39. 39. 39. 39. 39.  32#
y23   39. 39. 39. 39. 39. 39. 39. 39. 39. 39.  32#
y24   14# 14# 14# 14# 14# 14# 14# 14# 14# 14#  14#
```

- **Land island** = `0x39` at x6–15, y20–23, plus the door `0x1b` at (12,19) and a `0x2c` at (15,19).
- **Seal ring** (every orthogonal neighbour that is not island): solid `0x55/0x56/0x4e/0x1a/0x1a/0x1a/0x1a/0x1a/0x50` (north), `0x22`/`0x3d` above the door, `0x32` (east), and **`0x14`** (west column + entire south row) — the only non-solid cells.
- Flood-fill on the collision grid: road-from-start = **363 cells**; island-from-door = **42 cells**; **intersection 0, zero orthogonal road↔island adjacency** → sealed. The live walker agrees: `walk→(12,20)` and `walk→(8,22)` both **no-path** (stayed at (19,0)); control `walk→(20,12)` **reached**.

## Why the door faces the wrong way to walk in

The door `0x1b` (12,19) has `0x22` (solid) directly above it and `0x1a` (solid) on both flanks; its only open neighbour is down, into the island (12,20). The island is ringed by `0x14` water (W/S) and solid (N/E). You cannot walk to it; you can only **surf onto it from the `0x14` and then step on the door**. Classic hidden-island door.

## The trap that almost flipped this (recorded so it is not walked twice)

My first "the pocket is reachable" conclusion was a **coordinate-swap misread**, not a real path. I targeted `walk(5, {(20,12)})` and read the settled `pos (5, 20, 12)` as "pocket (12,20)" — but `pos` is `(map, x, y)`, so `(5,20,12)` is **x=20, y=12, a road cell**, and the target tuple is `(x, y)`. Transposing them made three *road* cells look like *pocket* cells. The corrected probe — target the real pocket cell `(x=12, y=20)` — returns **no-path**. Lesson, stated plainly: **`walk` targets and `pos` are both `(x, y)`; do not read a settled position as `(y, x)`, and do not infer reachability from a mislabelled probe.** The flood-fill on the grid (which carries no human label) is the check that cannot be misread this way.

## The surfability caveat (do not overclaim)

`WATER_TILES = {0x11, 0x14}` in `road.py` is the engine's proposal, and the lesson `surf-is-armed-and-the-water-is-not-a-tile-id` is explicit that **surfability is not a tile id** — the same id can be a rock on one shore and water on another, decided only by the game's own "No SURFing on GYARADOS here!" refusal. So "the `0x14` ring is water" is the best supported reading (it is the only non-solid ring, and `0x14` is water on the other two water maps), but it is **not confirmed for these exact cells** because this baton has no surfer to probe it. If they are solid, the pocket is sealed outright (map 92 would be an unreachable/building-only room). Either way: **unreachable by this party.**

## How to actually enter (when a surfer is available)

1. A baton with an awake, non-lead **Gyarados** (see `badge7-8-checkpoint-on-the-water` / `b7_surfing.state` lineage) positioned in the `0x14` water west/south of the island.
2. `use_field_move("SURF", species="Gyarados")` facing the island; confirm by `settled_pos()` moving onto a `0x39` cell (the behavioural probe, not the tile id).
3. From the island, step onto the door (12,19) → warp to map 92, land near the exit mats (4,17)/(5,17)→LAST_MAP; the 5 bodies are up the room (trainers at (5,1),(9,6),(3,8),(0,10); the FLY NPC at (4,14), directly above the door).
4. `bank()` off the mat, not on it.

## Re-verify (cheap, no emulator needed for the geometry)

```python
import sys; sys.path.insert(0,'scripts'); import rom_truth as rt
m = rt.load_truth()['maps']['5']
# door and island
m['grid'][19][12]                     # '1'  (walkable door into map 92)
# island neighbours that are the ONLY route:
[( (x,y), m['tiles'][y][2*x:2*x+2]) for (x,y) in ((5,20),(6,24),(16,20),(12,18))]
# -> ('14','14','32','22'): the ring is 0x14 water on W/S and solid N/E
```

## Artifacts

- Driver: `data/local_runs/roster-bench/fly_vermilion.py`
- Restore-point baton (road beside the island, before the door): `data/local_runs/roster-bench/fly92_entrance.state` @ (5,14,16)
- Screens at the island edge: `data/telemetry/screens/fly-geom/near_pocket_{west,east}.png`
- Map 92 ground truth: 10×18, tileset 7, warps `[4,17,255,3]`,`[5,17,255,3]`; sprites 4 trainer + 1 npc.

## Bottom line

Not a failure to retry this baton — it lacks the one thing the door needs. The gate is real and measured (sealed grid + only-water ring + single ROM entrance + no SURF in party). The previous `fly-vermilion` run hit the same wall: it was refused at the map 92 door *and* refused at the Route 16 `17→10` cross, then finished **`fly_not_found`**.

The move that finishes the mission is one of:

1. **A surfer-capable baton** (e.g. the `b8_BATON_island_gyarados_safe.state` Gyarados line, or any baton holding an awake Gyarados) brought to the `0x14` water west/south of the (12,19) island, SURF onto the `0x39` land, then step on the door → map 92 → engage the 5 bodies and read FLY.
2. **Route 16 fallback, correctly played**: the `17→10` refusal is a **CUT shrub**, not a dead hop (`fly_hunt` says this explicitly; Charizard already knows CUT). Approach it facing the shrub, `use_field_move("CUT")`, read the follow-up text, then continue `10→18→6→27→28` and look for the FLY — the warp list shows zero doors on map 28, so the FLY there (if it is there) is an unregistered building or a body, per `fly_hunt`.
3. **Mission-level**: if the FLY giver is actually the map 30 island retreat or the map 93 Pidgey (same FLY, different shore), switch batons to the one already on that ground rather than hauling this party across the map.
