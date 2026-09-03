# Expedition stuck: map 3 (9, 26) -> goal 14

run_id: 484f451cdd1a  •  goal: reach map 14

The ladder was exhausted: The Point Man (qwen38-27b-128k) then The Extractor (kimi-k2.6:cloud). Anthropic was NOT called — deciding whether Opus is worth it is the operator's call, made holding this record.

## Measured facts at the point of failure

```
GOAL: reach map 14. You are on map 3 at (9, 26).
MAP 3: 40x36, tileset 0 (tile-id meanings are per-tileset and may not be reused across tilesets).
ROUTED CHAIN (extracted from this cartridge): 3 --west edge--> 15
15 --south edge--> 14
NO ROUTE: the extracted connection graph has no chain from map 3 to map 14.
LIVE BODIES (sprites on screen right now): [(4, 12), (6, 21), (10, 27), (15, 16), (20, 2), (27, 12), (28, 12), (28, 26), (29, 26), (30, 8), (31, 20)]
Bodies are not walls — wanderers move if you wait, but trainers never move.
PARTY: [('Gyarados', 21, 76), ('Dugtrio', 100, 153), ('Primeape', 99, 300), ('Pidgeot', 99, 347), ('Hypno', 99, 341), ('Charizard', 100, 341)]   BADGES byte: 0b00111111
TEXT ON SCREEN: "home, so it won't get dirty!"
OBSERVED: the hop 15->14 is structurally refused; rerouted around it
OBSERVED: the hop 3->16 is structurally refused; rerouted around it
OBSERVED: banning 3->20 leaves no chain to 14 at all
```

## Actions tried

- TRY_FAR_EDGE_CELL on map 3 at (9, 26)
