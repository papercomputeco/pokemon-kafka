# Badges 7 & 8 are unreachable from the `b7_first_setup` baton: the region is sealed (2026-09-03)

Goal: badge 7 (Cinnabar City / Blaine, map 8 / gym 166) then badge 8 (Viridian / gym 45), from
`data/local_runs/roster-bench/b7_first_setup.state` — map 30 at (6,9), 6 badges, party
[Charizard L100, Dugtrio L100, Primeape L99, Pidgeot L99, Hypno L99, Gyarados L20 73/73].

**Result: both badges are in a map region SEPARATE from the baton's, and all three boundary
crossings between them are blocked in-game. This was established by in-game play (SURF arming,
two full 30→31 crossings, a live `R.cross(31,8)` attempt) plus signature-located ROM geometry —
not recalled lore. The baton file was never modified (all runs boot fresh, then `R.finish`).**

## The region is a closed set

The baton's region (maps reachable by *traversal*, not just topology) is
**{7 Fuchsia, 26, 27, 28, 29, 30, 31, 184-deadend, 192-internal-rooms}**. The only edges that
leave it (from ROM `connections`, which is ground truth for what *exists*):

| crossing | to | what it is | why it's blocked (in-game) |
|---|---|---|---|
| **map 31 --west--> map 8** | Cinnabar City | SURF across the sea | The player lands on **rows 5–16**; that water component dead-ends at **x=63**; the Cinnabar crossing points `(0,0/14/15/16)` are **all unreachable**. |
| **map 26 --east--> map 25** | Violet→Viridian land | walk | map 26 is a **pocket** (measured this session): entering at (0,9) traps in rows 8–9, x=0–7; `walk` to the east edge (x=59) = **no-path**. |
| **map 27 --east--> map 6** | (behind) land | walk | map 27 sits **inside** the 28/29 pocket (29→28 blocked); map 27 itself is unreachable. |

A **warp scan of every region map found no escape**: all warps go to interior rooms (map7→152–164,
map26→184, map27→186/188, map29→190, map31→192). Nothing jumps to the badge cluster, no ship.

The badge targets and their (closed) links: map 8 `{north:32, east:31}` (166 is its interior),
map 1 `{north:13, south:12, west:33}` (45 its interior). The whole `{0,1,8,12,32,...25}` cluster
is reachable only through the three blocked edges above.

## The Cinnabar surf, measured, is the decisive block

### Map 31's water is TWO disconnected components, split by a solid row

```
row 0:  100 cells of 0x14  (a clean straight west-east corridor — the ONLY Cinnabar line)
row 1:  100 cells of 0x3a  (a SOLID 1-tile wall across the whole map — the divider)
rows 2-16: the maze component the player actually lands in
```

* **Component A** = row 0: 100 cells, reaches Cinnabar at (0,0). But its *only* east-edge entry
  is (99,0). You can only be on it if you land on row 0.
* **Component B** = rows 2–16: 555 cells from (99,5), **min x = 63** (a rock maze). It does NOT
  reach x=0, so it cannot reach *any* Cinnabar crossing point (0,0/14/15/16). (99,5) and (99,16)
  are the same component; neither touches x=0.

### The cross from map 30 only ever lands in Component B

Two full in-game crossings measured the landing row:

```
exit map 30 at row 40  ->  lands map 31 row 5
exit map 30 at row 52  ->  lands map 31 row 16
```

The exit band on map 30's west edge is rows 40–52 (the lower west water; the upper pocket at rows
6–8 is **enclosed by rock and land on all sides** — unreachable by water or foot). So every
30→31 landing is in rows **5–16 = Component B**, which cannot reach Cinnabar. Landing on row 0
(needed for Component A) is impossible: no reachable map-30 exit maps to it.

### The engine agrees

A live `R.cross(31,8)` (Gyarados surfing, 4 trials) also failed — same "the surf is a dead end":
it drifts in the x=80–90 pocket of Component B and never reaches x=0. This is the same geometry,
not an engine defect.

## What this is NOT

* Not a SURF-arming problem: `use_field_move("SURF")` arms and the player surfs (measured,
  (6,9)→(6,11)).
* Not a battle problem: Charizard L100 one-shots the L5 Tentacool water encounters; Gyarados
  survives every run at 73/73 (kept off the lead).
* Not a "the water is one giant lake" assumption: it is **not**. Tile-surfability (0x14) plus the
  solid row-1 wall make map 31 into two separated water bodies (verified against the game's
  accepted/rejected moves, per `surf-is-armed-and-the-water-is-not-a-tile-id.md`).

## Options for the operator (the geometry, not the agent, is the wall)

1. **Re-place the baton** on a map adjacent to the badge cluster (e.g., on map 7's Fuchsia water
   where the sea connects, on Cinnabar itself, or past the 26/27 pockets) — the agent will then
   surf/walk + fight the leaders fine.
2. **Confirm the intended route**: if Cinnabar is meant to be reached via a ship/SS or a specific
   strait that this baton is on the wrong side of, the *state* (position + flags) needs to be the
   one the game considers "west of Cinnabar in the connected sea."
3. **Accept the baton as a 6-badge checkpoint**: party is healthy, Gyarados keeps SURF, badges
   `0b00111111` — it is a valid save, just not one that can reach badges 7–8 by traversal.

## Reproduce

```
uv run python - <<'EOF'
# (a) map 31 component split + Cinnabar crossing-point reachability (BFS on 0x14 tiles)
# (b) map 30 west-edge open band = rows 40..52 (upper 6..8 pocket enclosed)
# (c) warp scan: every region warp -> interior rooms 152..192 (no escape)
EOF
```
Landing rows are live: arm SURF from (6,9), surf down to (1,52), press west → lands (31,99,16).
