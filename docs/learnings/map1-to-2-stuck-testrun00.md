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
ALREADY OBSERVED HERE: - [important] map=1 Viridian door (32,7) -> map 45 with 7 badges: (1, 32, 8)->(45, 16, 17), said 'OPTION EXIT' (session: extracto)
ALREADY OBSERVED HERE: - [important] map=1 exhausted at (6,6) reaching goal 2: no-path; tried nothing; screenshot <fake>/exhausted_map1.png; record map1-to-2-stuck-testrun00.md (session: supervis)
ALREADY OBSERVED HERE: - [important] map=1 exhausted at (0,8) reaching goal 2: cap; tried door (7,8) to 2: cap; screenshot <fake>/exhausted_map1.png; record map1-to-2-stuck-testrun00.md (session: supervis)
ALREADY OBSERVED HERE: - [important] map=1 exhausted at (2,0) reaching goal 2: no-path; tried nothing; screenshot <fake>/exhausted_map1.png; record map1-to-2-stuck-testrun00.md (session: supervis)
ALREADY OBSERVED HERE: - [important] map=1 exhausted at (0,0) reaching goal 2: no-path; tried nothing; screenshot <fake>/exhausted_map1.png; record map1-to-2-stuck-testrun00.md (session: supervis)
ALREADY OBSERVED HERE: - [important] map=1 exhausted at (3,3) reaching goal 2: no-path; tried engaged the blocking body at (3, 2); screenshot <fake>/exhausted_map1.png; record map1-to-2-stuck-testrun00.md (session: supervis)
ALREADY OBSERVED HERE: - [important] map=1 exhausted at (5,5) reaching goal 2: no-path; tried nothing; screenshot <fake>/exhausted_map1.png; record map1-to-2-stuck-testrun00.md (session: supervis)
ALREADY OBSERVED HERE: - [important] map=1 exhausted at (5,5) reaching goal 2: refused; tried BACK_OUT_AND_REENTER on map 1 at (5, 5), BACK_OUT_AND_REENTER on map 1 at (5, 5), BACK_OUT_AND_REENTER on map 1 at (5, 5), BACK_OUT_AND_REENTER on map 1 at (5, 5); screenshot <fake>/exhausted_map1.png; record map1-to-2-stuck-testrun00.md (session: supervis)
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
