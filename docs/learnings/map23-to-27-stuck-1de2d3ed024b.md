# Expedition stuck: map 23 (10, 61) -> goal 27

run_id: 1de2d3ed024b  •  goal: reach map 27

The ladder was exhausted: The Point Man (qwen38-27b-128k) then The Extractor (kimi-k2.6:cloud). Anthropic was NOT called — deciding whether Opus is worth it is the operator's call, made holding this record.

## Measured facts at the point of failure

```
GOAL: reach map 27. You are on map 23 at (10, 61).
MAP 23: 20x108, tileset 0 (tile-id meanings are per-tileset and may not be reused across tilesets).
ROUTED CHAIN (extracted from this cartridge): 23 --north edge--> 4
4 --west edge--> 19
19 --west edge--> 10
10 --west edge--> 18
18 --west edge--> 6
6 --west edge--> 27
FAILED HOP: 23 --edge--> 22; the engine returned 'body-blocked'.
OPEN EDGE CELLS toward 22 (step left): [(0, 61), (0, 62), (0, 72), (0, 73), (0, 74), (0, 75), (0, 76), (0, 77), (0, 78), (0, 79), (0, 80), (0, 81), (0, 82), (0, 83)] ...
LIVE BODIES (sprites on screen right now): [(5, 39), (5, 89), (6, 87), (9, 52), (10, 62), (11, 92), (12, 40), (14, 31), (14, 35), (14, 76)]
Bodies are not walls — wanderers move if you wait, but trainers never move.
THE BLOCKING BODY IS (10, 62): removing that one sprite reconnects this hop, and no other body does. Any body you are standing next to is a bystander unless it is this one.
PARTY: [('Charizard', 100, 341), ('Dugtrio', 100, 259), ('Gloom', 99, 313), ('Primeape', 99, 300), ('Pidgeot', 99, 347), ('Hypno', 99, 341)]   BADGES byte: 0b00111111
TEXT ON SCREEN: 'my POKéMON evolve with MOON STONE!'
OBSERVED: the hop 18->6 is structurally refused; rerouted around it
OBSERVED: the body at (10, 62) was engaged and did not clear; it is terrain
OBSERVED: the body at (10, 62) (which alone severs this hop) says: AAAAAAA got 945 for winning!
OBSERVED: the body at (15, 6) was engaged and did not clear; it is terrain
OBSERVED: the body at (15, 6) (which alone severs this hop) says: They need to learn bet | They need to learn bett | They need to learn better moves. | They need
OBSERVED: the hop 25->26 is structurally refused; rerouted around it

SCREENSHOT AT THE POINT OF FAILURE: /home/bdougie/code/pcc-labs/pokemon-kafka/data/telemetry/screens/1de2d3ed024b/exhausted_map23.png
```

## Actions tried

- engaged the blocking body at (10, 62)
- engaged the blocking body at (15, 6)
- TRY_FAR_EDGE_CELL on map 25 at (16, 6)
- TRY_FAR_EDGE_CELL on map 25 at (16, 6)
- TRY_FAR_EDGE_CELL on map 25 at (16, 6)
