# Mission: stop the Seafoam current with STRENGTH, cross B3, exit the east door, reach Cinnabar

You are the Extractor (puzzle seat). Use `uv run ...` for all Python. Print `date` at the start
and before any summary. Screenshot every refusal (`Rig.screenshot(tag)`) and look at it.

## Ground truth already measured today (journal: `pokedex/memory/observations.md`, grep `map=161`)

- Baton `data/local_runs/roster-bench/seafoam_loop_stuck_3.state`: Seafoam **B3 = map 161 at
  (18,12)**. Gyarados (party index 5, 73/73) knows **SURF and STRENGTH**. Six badges.
- The loop out of Seafoam (tile pairs honoured, boulders solid) is
  `161: surf to the stair (25,14) -> 160 stair (25,11) -> 159 stair (23,15) -> 192 east region
  -> east door (26,17) -> map 31 (58,9) -> step DOWN onto the south shore -> surf west to Cinnabar`.
- On B3, SURF is **refused** from every row-12 cell facing UP into the water ("No SURFing on
  GYARADOS here!") and **accepted at (15,7) facing DOWN** into (15,8). The moment the surfer is
  on the water a **current** sweeps it off B3 and drops it onto **B4 (map 162) at (20,15)**.
- B3's boulders (`pic == 63` sprites, the cartridge calls them "npc") are at
  `(3,15) (5,14) (8,14) (9,14) (18,6) (19,6)`. The tile map around the water:
  row 8 x=14..19 water; rows 10-11 x=14..23 water; rows 12-14 x=14..18 land (0x05), x=19 0x17,
  x=20-21 water, x=22 0x04/0x31, x=23-24 land; row 15 x=16,17 land (0x15); row 16 x=14..17 land.
  Print your own view with `truth["maps"]["161"]["tiles"]` / `["grid"]` before deciding.

## The job

1. Figure out, by pushing and observing, which boulders drop into which holes and what that does
   to the current. `Rig.strength_push(face)` enables STRENGTH and shoves the boulder you face;
   it returns True when the boulder's tile opens. A boulder that will not move says so on screen
   -- read the sentence. `Rig.walk(161, {cell}, battle=rig.battle)` gets you next to one.
2. After each push, test the water again from (15,7) facing down (`rig.io.press("down",
   hold=4, release=8)` to face, then `rig._arm_surf()`), and see whether the current still
   carries you. If it drops you to B4, note where, and come back up (B4's (20,17)/(21,17) warp
   to B3's (20,17)/(21,17)).
3. When the current stops, surf to the (25,14) stair and follow the loop above. Bank
   `island_south` on map 31 at y >= 10, then `cinnabar` on map 8.

## Discipline

- Drain text after every battle: `ADDR_IN_BATTLE` clears before the EXP pages do, and a page
  blocks every step (press B until `rig.textbox()` is empty).
- Single steps are `rig.io.press(key, hold=8, release=8)`; a long hold moves several tiles.
- Wild battles: `rig.battle()`.
- Do not write `docs/learnings/`. Write what you measure into the journal:
  `from memory_writer import append_observations; append_observations("pokedex/memory", [{"referenced_time": "2026-09-04", "priority": "important", "source_session": "extractor", "content": "map=161 ..."}], dedupe=True)`
- Any one-off driver you commit is `scripts/probe_<name>.py`. Commit as you go.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.

## Definition of done

`cinnabar.state` banked on map 8, or the journal holding, per boulder, what happened when it was
pushed and what the current did afterwards -- with screenshots. That record is the deliverable if
the crossing is not.

## Measured since this brief was written (2026-09-04, later) — start from these

- **Activate first, every boot.** `rig.use_field_move("STRENGTH", species="Gyarados")` →
  "GYARADOS used STRENGTH." → "GYARADOS can move boulders." A push before that is answered
  "This requires STRENGTH to move!" — that was the refusal on the first attempt at (5,15).
- **Press length is the mechanic.** An 8-frame press never moves a boulder; a 16-frame hold does.
  `Rig.strength_push(face)` now does this and judges by the **sprite table** (`rig.bodies()`),
  not your position. Drain any page (B until `rig.textbox()` is empty) before every press.
- **Geometry (ROM tiles, map 161):** boulders at (5,14) (3,15) (8,14) (9,14); `0x12` HOLE tiles
  at (7,14) (4,15) (4,16) (9,16) — the dark squares in `push_9_14_left_40.png`. The row above
  (5,14) is solid `0x10`. Rows 12–13 at x=8..9 are a 2×2 pocket you cannot enter.
- **Two measured pushes:** (9,14) pushed UP from (9,15) moved → sprite at (9,13), i.e. into the
  pocket — a dead end, do not repeat. (8,14) pushed LEFT from (9,14) *toward the hole* at (7,14)
  was **refused** at 16 and 40 frames. That contradiction is the puzzle: find out what a boulder
  needs to enter a hole (approach direction? a specific boulder? a different hole?) by pushing
  and screenshotting, one press at a time. Boulders reset when you leave and re-enter the floor
  (`seafoam_loop_stuck_3.state` is the clean floor).
- Batons: `b3_push_9_15_up.state` (after the pocket push, for contrast).
- Write every push's outcome to the journal as you go, as instructed above.
