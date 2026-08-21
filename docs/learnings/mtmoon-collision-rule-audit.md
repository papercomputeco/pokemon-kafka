# Mt. Moon "unreachable" verdict: the parser was right, the audit was wrong

Supervisor audit, 2026-08-21, of the qwen38-27b fix-first expedition
(`speedrun/pi-exp-qwen38-27b-mtmoon2`, commits `810139d`..`132700c`).

## What the expedition claimed

1. `scripts/rom_truth.py`'s collision rule is wrong for the cavern tileset — **842 of 1,440
   cells wrong on Mt. Moon 1F** (map 59).
2. The true rule is "a cell is walkable iff **≥3 of its 4 sub-tiles** are walkable" (committed
   as the fix, with a test and a re-extracted `rom_truth.json`).
3. With the corrected map, the mission goal (map 3, or map 15 at x≥30 having visited 60/61) is
   **statically unreachable from the seed** — six candidate bridges all measured dead.

Claim 3 was published in `benchmarks/2026-08-20-mtmoon2-local-batch.md` and PR #100 as
"nobody exited Mt. Moon because the map I gave them was wrong."

## What is actually true

**The main-repo rule was already correct and remains so.** `scripts/rom_truth.py:116` reads the
**bottom-left** 8x8 tile of each 2x2 quad — the canonical pokered convention (the tileset's
collision list holds bottom-left tile ids). No source change was needed; the expedition's ≥3-of-4
rule is a **regression**, and it is confined to its own branch. Do not merge it.

### Three independent falsifications of the ≥3-of-4 rule

| evidence | bottom-left (main) | ≥3-of-4 (expedition) |
|---|---|---|
| Warp-tile invariant: every warp destination must be standable (the engine puts the player there), 816 warps over all 248 maps | **801/816 (98.2 %)** | 256/816 (31.4 %) |
| Same, cavern tileset only | **4/4** | 0/4 |
| Live: player stands on map 61 (25,9) after the B1F ladder | consistent | calls that cell **solid** |

The 15 remaining bottom-left misses are all overworld building doors, where the door tile is
genuinely non-walkable and the warp fires on the step into it — expected, not error.

### Why the expedition's own dataset does not support its rule

Its 158-cell live sweep of map 59 (`demo-runs/sweep_map59.json` on that branch), scored fairly:

| rule | correct | **false-SOLID** (calls a walkable cell a wall — closes real corridors) | false-OPEN (engine refused for another reason) |
|---|---|---|---|
| bottom-left | 99/145 | **0** | 46 |
| ≥3-of-4 | 118/145 | **0** | 27 |

Neither rule ever closed a corridor the engine actually walks. The sweep's own summary field
`audit_grid0_live_walk` is **empty** — zero cells where the committed grid said wall and the
engine walked. The ≥3 rule's better raw score comes entirely from being more conservative about
**false-OPEN** cells, and those refusals are NPC/sprite occupancy and unreachable pockets, not
tile collision. The rule was fit to sprite noise: it bought ~19 cells on 1F and paid by closing
69 % of the game's warp tiles, including the B2F corridor the exit depends on.

The "842 of 1,440 cells wrong" figure counts 1,282 cells the sweep marks `unreachable` — never
measured at all.

## The route is open, and it is the real game's route

Flood-fill on the **committed main-repo** `references/rom_truth.json`:

```
59 seed (14,35) -> ladders (5,5) / (17,11) / (25,15) all reachable
59 (17,11) --ladder--> 60 (25,9)  --ladder (17,11)-->  61 (25,9)
61 (25,9) -> (5,7)          553-cell component, key reachable      <- CLOSED by the ≥3 rule
61 (5,7)  --ladder-->       60 (23,3) far-door pocket (16 cells)
60 (27,3) --mat (255,2)-->  15 (24,5)                               <- Route 4, goal side
15 (24,5) -> x>=30          353-cell component                      GOAL
```

The "far door is circular" argument also fails. `(27,3)` is warp `(255, 2)` = *previous map's
warp index 2*, and map 15's index 2 is `(24,5)` — the east cave door. Last-map becomes 15 the
moment a lane uses the **west** mat and re-enters 59 through `15 (18,5)`, which the expedition's
own evidence lane already did. Entering from the east is not required.

## The real obstacle is the party, not the map

Live supervisor probe (seed → 1F ladder → B1F → B2F, engine deciding every step): the walk
reached B2F and then **blacked out to Pewter** on trainer attrition — Charmeleon 42/55 at the
seed, versus 7 trainers on 1F and 5 trainers + 2 fossil NPCs on B2F, with no heal between them.
Every battle is fought to completion by the probe's battle handler; trainers cannot be fled.

So the next Mt. Moon mission should treat **survivability through the B2F trainer gauntlet** as
the obstacle to solve (heal/route/level plan), and treat the map as trustworthy.

## Do not

- Merge or cherry-pick `810139d` (the ≥3-of-4 rule) into main.
- Cite PR #100's "the map was wrong" conclusion without this correction.
- Fit a collision rule to live-refusal data without separating **false-SOLID** from
  **false-OPEN** errors: sprites, NPCs, and ledges produce refusals that no tile rule should
  ever try to explain, and fitting to them silently deletes corridors on maps you never probed.
- Trust a reachability verdict that was never live-walked to the disputed cells: the disputed
  B2F corridor was declared dead from a parse of the very grid under audit.
