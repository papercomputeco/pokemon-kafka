# Viridian (badge 8) and the Cycling-Road gate: both impossible from the current baton

Measured 2026-09-03, from `data/local_runs/roster-bench/m1_cerulean.state` (pos 3,13,26),
against `rom/pokemon_red.gb` via `scripts/rom_truth.py` and the live rig. Every claim below is
a measurement from this cartridge, extracted or observed this session — no recalled layout.

## Verdict

1. **Badge 8 (map 45, door (32,7) of map 1) is impossible from the current state.** Every entry
   into the Viridian cluster requires either Gate A (sealed in the collision table) or a SURF leg,
   and SURF is unobtainable in this cartridge: the only SURF-carrying Pokémon (Gyarados) is gone,
   no SURF machine exists anywhere in the world, and the party has no water type.
2. **The Cycling-Road gate test (29↔28) is also unreachable**: the road lies in a different
   connected component of the map graph than the baton's pocket.

## 1. The two gates into Viridian, both dead

Inbound edges/warps into cluster {1, 2, 12, 13, 14, 15, 45}, extracted in full:

- edges: `3 --west--> 15`, `0 --north--> 12`, `33 --east--> 1`;
- warps: **none** (no door into the cluster from any external map).

### Gate A — map 15: sealed in the collision table (re-confirmed, third measurement)

Map 3's baton pocket reaches only west-edge rows (0,18)/(0,19) of map 3. From there, map 15 is
five disconnected zones; only zone C (a 378-cell pocket) is crossable via rows 18/19, and zone C
has no exit to zone W — the one zone that holds the 15→14 door (11,5):

- pair `(44,58)` blocks (5,32)→(5,33); pair `(57,80)` blocks (13,27)→(13,28) — the only two
  candidate steps out of the pocket rows toward the door;
- `path_on_map((13,26), {(4,34)}) = None`, `path_on_map((13,26), {(0,21)}) = None`;
- live probe (route4_probe, baton m2_route4): every street west-edge row of map 15 was asked —
  rows 12,13 no-path; 21–35 all no-path; 18→(89,10) sealed, 19→(89,11) sealed.

Gate A is dead. Not a bug: the ROM's own pair table.

### Gate B — the water legs: SURF is unobtainable

The two water chains both start with the same three crossings:

```
7  --south--> 30 (20x54)  --west--> 31 (100x18)  --west--> 8 (Cinnabar land, 20x18)
   then either  8 --north--> 32 (20x90) --north--> 0 (island) --north--> 12 --north--> 1
   or           8 --?--> 9 (20x20) --?> 34 (20x144 corridor, 34 --south--> 33 --east--> 1)
```

(The 33/34 "overland to Viridian" chain is real but enters only from map 9, which is on the
Cinnabar (sea) side — it does not avoid the water; inbound to 33/34: `1.west`, `34.south`,
`9.south`, `33.north`, `34.south`, `35.east`, `36.west` — all cluster-internal or sea-side.)

SURF requires a water-type in the party that knows SURF (and, measured, a BICYCLE in the bag —
id 228, present). Status of each requirement:

- **Gyarados (the only SURF carrier, L21, SURF in moveset) is gone.** It is not in the 6-slot
  party (Charizard L100, Dugtrio L100, Gloom L99, Primeape L99, Pidgeot L99, Hypno L99).
  - Bill's PC: all 12 boxes read with confirmed footers `BOX No. 1…BOX No. 12` — every grid
    empty. (Verified with a live deposit/withdraw round trip: Dugtrio deposited into Box 1,
    read back, withdrawn; net party unchanged in the banked baton.)
  - `PROF.OAK's PC` is the POKéDEX rating screen ("91 POKéMON seen / 14 POKéMON owned —
    Get a FLASH HM from my AIDE!"), not a storage box. The "14 owned" counter disagrees with
    party(6) + boxes(0) = 6; unresolved mod-RAM quirk, noted here rather than trusted.
  - Last Gyarados telemetry: 2026-09-01 19:29 (EXP) and 2026-09-02 12:27–13:50 (three
    "No SURFing on GYARADOS here!" at 30/31 — it was in the party then). No RELEASE/TRADE
    event in the telemetry; it vanished between those runs and baton 20260902-204710.
    The PC menu carries a live RELEASE option; consistent with an accidental RELEASE,
    unprovable after the fact.
- **No SURF machine exists in the world.** `item_names` → HM03 = id 198; a scan of *every*
  item-ball sprite in the cartridge found **zero** id-198 balls. The bag (19/20) has no SURF.
  The PC item box (`AAAAAAA's PC`) is the bag — same list.
- **Wild catch cannot fill the gap.** Wild move sets are chosen from species pools; no party
  slot is a water type at all, so there is no one to even teach SURF to, and this engine
  teaches HMs nowhere (zero balls in the world).

SURF impossible ⇒ Gate B impossible ⇒ **no entry into the Viridian cluster exists**.

## 2. The baton pocket is a closed world

Engine walkable region (pairs + gates honoured) from (3,13,26) on map 3:

```
371 cells, x 0–34, y 0–28
boundary reachability:
  west  (x=0):  (0,18), (0,19)   -> map 15 -> zone C -> dead (Gate A above)
  north (y=0):  (20,0), (21,0)   -> map 35 {south:3, east:36}; map 36 {west:35} + warp (45,3)->88
  east  (x=39): none
  south (y=35): none
in-pocket warps: the buildings 62/63/64/65 — all of them warp only back to map 3 (255),
                 no external door; 64 (the Center) confirmed live (heal worked, PC works)
```

Maps 35 and 36 are a two-map peninsula attached to map 3's north edge; nothing else connects
to them (inbound to 35/36: `3.north`, `35.east`, `36.west` only). Everything outside
{3(K_west), 15, 35, 36, 88, buildings 62–65} is a different connected component of the map
graph: the routes 20/21/4/23/24/25/26, Fuchsia 7, the sea (30/31/8/32/0/12), Cinnabar's
overland (9/34/33), Viridian (1/2/12–15/45), and the Cycling Road (27/28/29).

Earlier campaign legs (badges 1–6) ran inside the *east* half of map 3 (the other side of the
same pair-sealed column at x≈34, out of this region's x≤34) and onto the routes; the baton
entered the west side via map 15 rows 18/19 — which only leads back here. The split is
measured, not recalled: the engine's own BFS with the ROM's pair table ends at x=34.

## 3. What this means for mission #11350

- Badge 8: **dead end on this cartridge state.** The two structural gates are both closed and
  neither is openable with anything this cartridge can still acquire. Reopening requires
  restoring Gyarados (a save/box that still holds it) or a session in which SURF + a water
  type are secured *before* Gyarados is lost, entering the water leg from map 7.
- Cycling-Road gate (29→28) with the bike: same component wall — unreachable from here.
  (BICYCLE is in the bag, id 228; the cross 3→20/3→16 from this pocket fails `no-path`
  in 0 s because the pocket never touches those edges.)

## 4. Open anomaly (do not trust, do not ship)

The POKéDEX rating screen claims 14 POKéMON owned while party(6) + all 12 boxes(0) + Oak(none)
accounts for 6. On a vanilla-generation cartridge ownership is party ∪ PC boxes; the discrepancy
is either released Pokémon being counted or a mod bookkeeping quirk. Recorded, not load-bearing.
