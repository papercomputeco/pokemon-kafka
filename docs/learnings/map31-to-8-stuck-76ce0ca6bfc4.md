# Expedition stuck: map 31 (55, 9) -> goal 8

run_id: 76ce0ca6bfc4  •  goal: reach map 8

The ladder was exhausted: The Point Man (qwen38-27b-128k) then The Extractor (kimi-k2.6:cloud). Anthropic was NOT called — deciding whether Opus is worth it is the operator's call, made holding this record.

## Measured facts at the point of failure

```
GOAL: reach map 8. You are on map 31 at (55, 9).
MAP 31: 100x18, tileset 0 (tile-id meanings are per-tileset and may not be reused across tilesets).
ROUTED CHAIN (extracted from this cartridge): 31 --west edge--> 8
FAILED HOP: 31 --edge--> 30; the engine returned 'surfmoved-failed'.
OPEN EDGE CELLS toward 30 (step right): []
LIVE BODIES (sprites on screen right now): [(15, 8), (24, 12), (25, 7), (34, 9), (38, 13), (45, 11), (55, 14), (68, 11), (87, 5), (87, 13)]
Bodies are not walls — wanderers move if you wait, but trainers never move.
PARTY: [('Charizard', 100, 335), ('Dugtrio', 100, 247), ('Primeape', 99, 300), ('Pidgeot', 99, 347), ('Hypno', 99, 341), ('Gyarados', 20, 73)]   BADGES byte: 0b00111111
TEXT ON SCREEN: 'OPTION EXIT'
ALREADY OBSERVED HERE: - [important] map=31 Route 20 water is PARTITIONED and Seafoam is the through-passage, not a detour. Arrival water from Route 19 is 555 cells x=63..99; the water reaching the Cinnabar edge (x=0) is a separate 694-cell body x=0..61. They do not connect. The only links are the two Seafoam cave mouths at (58,9) and (48,5), each in its own 12-cell pocket. A direct west surf hop 31->8 fails 'surfmoved-failed' every time. (session: expediti)
OBSERVED: the navigation seat returned no menu action; retrying the hop unchanged
OBSERVED: both seats explain 31->8 the same way: consults disabled
OBSERVED: the navigation seat returned no menu action; retrying the hop unchanged
OBSERVED: both seats explain 31->8 the same way: consults disabled
OBSERVED: the puzzle seat returned no menu action; retrying the hop unchanged
OBSERVED: both seats explain 31->8 the same way: consults disabled
OBSERVED: the puzzle seat returned no menu action; retrying the hop unchanged
OBSERVED: the hop 31->8 is structurally refused; rerouted around it
OBSERVED: the navigation seat returned no menu action; retrying the hop unchanged
OBSERVED: both seats explain 31->30 the same way: consults disabled
OBSERVED: the navigation seat returned no menu action; retrying the hop unchanged
OBSERVED: both seats explain 31->30 the same way: consults disabled
OBSERVED: the puzzle seat returned no menu action; retrying the hop unchanged
OBSERVED: both seats explain 31->30 the same way: consults disabled
OBSERVED: the puzzle seat returned no menu action; retrying the hop unchanged
OBSERVED: banning 31->30 leaves no chain to 8 at all

SCREENSHOT AT THE POINT OF FAILURE: /home/bdougie/code/pcc-labs/pokemon-kafka/data/telemetry/screens/76ce0ca6bfc4/exhausted_map31.png
```

## Actions tried

