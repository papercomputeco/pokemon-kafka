# Expedition stuck: map 30 (4, 9) -> goal 31

run_id: 12fc80ba43fa  •  goal: reach map 31

The ladder was exhausted: The Point Man (qwen38-27b-128k) then The Extractor (kimi-k2.6:cloud). Anthropic was NOT called — deciding whether Opus is worth it is the operator's call, made holding this record.

## Measured facts at the point of failure

```
GOAL: reach map 31. You are on map 30 at (4, 9).
MAP 30: 20x54, tileset 0 (tile-id meanings are per-tileset and may not be reused across tilesets).
ROUTED CHAIN (extracted from this cartridge): 30 --west edge--> 31
FAILED HOP: 30 --edge--> 31; the engine returned 'surfmoved-failed'.
OPEN EDGE CELLS toward 31 (step left): []
LIVE BODIES (sprites on screen right now): [(4, 27), (8, 7), (8, 43), (9, 11), (9, 42), (10, 44), (11, 43), (13, 7), (13, 25), (16, 31)]
Bodies are not walls — wanderers move if you wait, but trainers never move.
PARTY: [('Charizard', 100, 341), ('Dugtrio', 100, 259), ('Primeape', 99, 300), ('Pidgeot', 99, 347), ('Hypno', 99, 341), ('Gyarados', 20, 73)]   BADGES byte: 0b00111111
TEXT ON SCREEN: 'AAAAAAA got 145 for winning!'
OBSERVED: map 30 has no warps to back out through

SCREENSHOT AT THE POINT OF FAILURE: /home/bdougie/code/pcc-labs/pokemon-kafka/data/telemetry/screens/12fc80ba43fa/exhausted_map30.png
```

## Actions tried

- BACK_OUT_AND_REENTER on map 30 at (9, 9)
