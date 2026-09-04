# Mission: the Cinnabar mansion's SECRET KEY — a switch-and-door catalog

You are the Extractor (puzzle seat). Use `uv run ...` for all Python. Print `date` at the start and
before any summary. Screenshot every refusal and look at it. Write every measured fact to the
journal as you go (`from memory_writer import append_observations`, `source_session: "extractor"`,
content starting `map=165 ...`). Do not write `docs/learnings/`.

## What is measured (journal: grep `map=165`, `map=215`, `map=216`)

- **Baton:** `data/local_runs/roster-bench/mansion_catalog_end.state` — map 165 (mansion 1F),
  door state B (see below). Six badges, all four HMs; Gyarados knows SURF+STRENGTH.
- **Goal:** the SECRET KEY. The ROM puts it in an item ball at **map 216 (5,13)**. 216 is entered
  only by the stairs at **165 (21,23)**. The Cinnabar gym (166) door says "The door is locked...".
- **165's switch** is tile `0x3d` at (2,5), pressed from (2,6) facing up: "A secret switch!" →
  "Press it?" → "Who wouldn't?". It toggles two states:
  - **A:** door (16,7) open, (24,13) shut, and the stands (20,16)/(21,16) unreachable.
  - **B:** (16,7) shut, (24,13) open, **(20,17)/(21,17) shut**.
  214's switch at (2,11) (stand (2,12) facing up) flips the same A/B.
- **The stairs pocket** (104 cells around (21,23)) is bounded ONLY by the doors (20,17)/(21,17)
  — ROM regions with the doors shut prove it; (16,7) and (24,13) do not matter for the stairs.
  Those two doors stayed shut after every press of 165's and 214's switches.
- **215's switch** (tile 0x3d at (10,5); stands (10,6) or (11,5)) has NOT been pressed: from the
  (7,11) landing (214's (7,10) stair) only 45 cells are reachable and no stand is among them —
  another secret door on 215. 214's other stairs to 215 are at (6,1) and (25,14); the static
  reachability of those landings is in the summary line below.
- **216's switches** are at (20,3) and (18,25) — inside the pocket you cannot enter yet.
- Tile `0x27` is a plaque ("Not quite yet!"). `0x22`/`0x12` are not involved here.
- A step survey (`supervisor.py survey`) never presses A; the switch was found by a **press
  survey**: face each distinct wall tile bordering the region and press A. Use both.

STATIC SUMMARY (computed from the ROM at launch):
214 from the (5,11) landing: 325 cells; beside (6,1) stair? [(6, 2), (7, 1)]; beside (25,14)? []; beside (7,10)? [(7, 11), (6, 10), (8, 10)]
215 from the (6, 1) landing: 240 cells; reaches the switch stand (10,6)? True; (11,5)? True
215 from the (25, 14) landing: 240 cells; reaches the switch stand (10,6)? True; (11,5)? True
214 switch (2,11) stands: [(2, 12), (1, 11), (3, 11)]

## The job

1. Build the catalog: for each switch you can reach (165 (2,5); 214 (2,11); 215 (10,5) via a
   landing that reaches its stand), press it and re-test each known door on 165 —
   (16,7) from (16,6) DOWN, (24,13) from (24,12) DOWN, (20,17)/(21,17) from (20,16)/(21,16) DOWN
   — and any new door you find. Record (switch, press count) → door states in the journal.
2. The verdict for "the stairs door is open" is the step from (20,16) or (21,16) moving DOWN.
3. When it opens: walk to (21,22), press DOWN through (21,23) → map 216. Sweep the ball at (5,13)
   (`rig.collect_item(5, 13)`; free a bag slot first with `rig.make_room()` if `rig.bag_full()`).
   The verdict is `SECRET KEY` in `rig.bag_named(full=True)`. Bank `secret_key`.
4. Then leave, walk to the gym door (map 8 warp (18,3)) and record what it says now.

## Discipline

- `rig.walk(map, {cell}, battle=rig.battle)` for walking; `rig.io.press(key, hold=16, release=16)`
  for a single decisive step; drain text after battles (press B until `rig.textbox()` is empty).
- Bank after every new state you reach (`rig.bank(name)`), so nothing is re-derived.
- Any driver you commit is `scripts/probe_<name>.py`. Commit as you go.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.

## Definition of done

`secret_key.state` banked with SECRET KEY in the bag, or the journal holding the full
switch→door catalog with the stairs door's controlling switch identified (or proven absent
among the reachable ones), with screenshots.

MEASURED LATER (after pressing 215's switch):
- 215 from (10,6): 240 cells; warps touching it: [[6, 1, 214, 3], [25, 14, 214, 2]]; (7,11) is NOT ROM-connected to (10,6) (a wall, not a door).
- 214 from the (6,1) landing with (9,4) shut: 324 cells; warps touching it: [[5, 10, 165, 4], [7, 10, 215, 0], [6, 1, 215, 1]]. The step (8,4)->(9,4) is REFUSED after 215's switch: 215's switch shut (9,4), which was open before, so the (6,1) pocket and 215's (10,6) region form a closed loop until 215's switch is pressed again.
- Untested: whether 215's switch group also includes 165's stairs door (20,17)/(21,17). It cannot be tested from inside the loop; the order of presses across floors is the puzzle.
wrote 1
