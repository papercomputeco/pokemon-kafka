# Expedition stuck: map 1 (5, 5) -> goal 2

run_id: testrun00  •  goal: reach map 2

The ladder was exhausted: The Point Man (qwen38-27b-128k) then The Extractor (kimi-k2.6:cloud). Anthropic was NOT called — deciding whether Opus is worth it is the operator's call, made holding this record.

## Measured facts at the point of failure

```
GOAL: reach map 2. You are on map 1 at (5, 5).
MAP 1: 8x8, tileset 0 (tile-id meanings are per-tileset and may not be reused across tilesets).
ROUTED CHAIN (extracted from this cartridge): 1 --east edge--> 2
FAILED HOP: 1 --edge--> 2; the engine returned 'refused'.
OPEN EDGE CELLS toward 2 (step right): [(7, 0), (7, 1), (7, 2), (7, 3), (7, 4), (7, 5), (7, 6), (7, 7)]
LIVE BODIES (sprites on screen right now): []
Bodies are not walls — wanderers move if you wait, but trainers never move.
PARTY: [('CHARIZARD', 99, 337)]   BADGES byte: 0b00011111
ALREADY OBSERVED HERE: - [important] Flink alert [DOOR_STALL]: map=1 pos=(29,28) action=left (count=9) (session: flink)
ALREADY OBSERVED HERE: - [important] Flink alert [DOOR_STALL]: map=1 pos=(26,28) action=left (count=9) (session: flink)
ALREADY OBSERVED HERE: - [important] Flink alert [DOOR_STALL]: map=1 pos=(26,28) action=left (count=29) (session: flink)
ALREADY OBSERVED HERE: - [important] Flink alert [DOOR_STALL]: map=1 pos=(29,28) action=left (count=29) (session: flink)
ALREADY OBSERVED HERE: - [important] Flink alert [GAME_STUCK_LOOP]: map=1 streak=5 (count=66) (session: flink)
ALREADY OBSERVED HERE: - [important] Flink alert [DOOR_STALL]: map=1 pos=(18,6) action=up (count=27) (session: flink)
ALREADY OBSERVED HERE: - [important] Flink alert [DOOR_STALL]: map=1 pos=(17,6) action=up (count=15) (session: flink)
ALREADY OBSERVED HERE: - [important] Flink alert [GAME_STUCK_LOOP]: map=1 streak=2 (count=20) (session: flink)
OBSERVED: collected [64] from map 1's item balls
OBSERVED: both seats explain 1->2 the same way: scripted
OBSERVED: both seats explain 1->2 the same way: scripted
OBSERVED: both seats explain 1->2 the same way: scripted
OBSERVED: banning 1->2 leaves no chain to 2 at all

SCREENSHOT AT THE POINT OF FAILURE: <fake>/exhausted_map1.png
```

## Actions tried

- RETRY_SAME on map 1 at (5, 5)
- RETRY_SAME on map 1 at (5, 5)
- RETRY_SAME on map 1 at (5, 5)
- RETRY_SAME on map 1 at (5, 5)
