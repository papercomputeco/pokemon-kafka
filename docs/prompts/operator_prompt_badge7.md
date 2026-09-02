# Mission: badges 7 and 8

You are an autonomous operator on this repo. Use `uv run ...` for all Python (AGENTS.md). Print
`date` at the start and before any summary. Work for the whole budget; do not stop early.

Six badges are won and **SURF is taught**. What remains is Cinnabar (Blaine, badge 7) and
Viridian (Giovanni, badge 8).

## START HERE — the last three legs were misdiagnosed. Read this before anything.

The "water/rock checkerboard" and the "unreliable surf position-tracking" in the earlier
learnings docs are **NOT REAL**. They were an engine bug, now fixed (`51b8290`), and treating
them as world facts is what cost three legs. Measured on map 30 (6,9):

- `_arm_surf` sent its keystrokes and **returned True even when the game refused** with
  *"No SURFing on GYARADOS here!"*.
- The refusal text box then **swallowed every input** — `probe_step()` was False in all four
  directions. The world was *frozen*, not blocked. Six B presses restored it instantly.
- So "I surfed and then nothing moved anywhere" was never geography. It was this.

`_arm_surf` now judges by the **position** (using SURF carries you onto the water), clears the
text first, and emits a `surf.refused` event carrying the sentence. `Rig.textbox()` reads what
the game is saying. **A False from `_arm_surf` now means the game genuinely refused that cell.**

**Your job:** SURF is refused at (6,9). Find a cell where it is not. Walk the island's six-cell
strip, try `_arm_surf()` from each cell and each facing, and read `Rig.textbox()` on refusal —
the game distinguishes *"No SURFing here!"* from *"There's no place to get off!"*, and those are
two different problems. Then chain hops to the map-31 boundary and on to Cinnabar (map 8), gym
warp (18,3) -> map 166 for Blaine.

**Do not** re-derive tile tables, diff RAM, or hunt ROM addresses — three legs have now been lost
that way. If a probe says *nothing works in any direction*, suspect the harness, not the
cartridge. Baton: `data/local_runs/roster-bench/b8_BATON_island_gyarados_safe.state`
(map 30 (6,9), 6 badges, party whole: Gyarados L20 73/73 + five L99/100 heavies).

## START HERE — the two bugs that ended the last leg are FIXED. Go and cross.

Baton: **`data/local_runs/roster-bench/b7_badge_clean.state`** (map 30 at (6,7), 6 badges, party
whole). Fixed since your last run, both with tests, both verified live — do not re-derive them:

1. **`road.surf_cross` no longer reads a wild encounter as a wall.** An encounter *cancels* the
   step, so the position is unchanged — identical bytes to walking into a wall. That is what
   produced `stuck-on-edge` in the middle of open water. Both the outward step and the armed
   re-step now check `ADDR_IN_BATTLE` first, fight, and re-step from the same cell.
2. **`Rig.knows_move(name)` finds the surfer by move id, not by species name.** The engine briefly
   carried `if lead in ("Gyarados", ...)`; that literal is gone. Verified live on this baton:
   SURF -> party index 0, CUT -> index 5. `_arm_surf` uses it, and `surf_facing` (your fixed
   keystroke path) still handles the lead.

**Your job this leg is navigation, not engine work.** Cross map 31 and reach Cinnabar (map 8),
then the gym warp at (18,3) -> map 166 for Blaine. If you find yourself reading ROM addresses or
diffing RAM, you are on the wrong thread — that has now cost two legs.

One measured thing still unexplained and worth your attention: after surfing to (6,6)/(6,7),
**further `down` presses do not move the player**. The straight-line run `surf_cross` does may
simply be the wrong shape for this water. Measure where it *can* move (try all four directions
and read `settled_pos()` each time) before assuming a direction is blocked.

## Background — SURF is proven working, and the baton is already on the water

Read `docs/learnings/surf-is-armed-and-the-water-is-not-a-tile-id.md`. Measured 2026-09-02:

- **`Rig.use_field_move("SURF", species="Gyarados")` arms and MOVES the player.** Verified live on
  map 30: (6,4) -> (6,6) -> (6,7). The menu path is not broken. Do not debug it again.
- **Your baton is `data/local_runs/roster-bench/b7_surfing.state`** — map 30 at **(6,7), already
  surfing**, whole party healthy (Gyarados L20 73/73, Dugtrio 100, Primeape 99, Pidgeot 99,
  Hypno 99, Charizard 100). Start from this, not from `b7_badge.state`.
- **There is no water-tile constant and you must not go looking for one.** The last leg spent an
  hour hunting a tileset movement-flags table. It is not needed and it does not answer the
  question: `(6,3)` and `(6,5)` are the *same* tile id `0x36`, yet facing up refuses
  **"No SURFing on GYARADOS here!"** and facing down surfs. The `0x14` histogram does not predict
  this either.
- **The probe is the game's own sentence.** Arm SURF facing a direction, read the text box, and
  check whether `settled_pos()` changed. Four presses answer what an address hunt did not. If you
  find yourself typing a hex offset into a probe, stop — `rom_truth` locates every table by
  signature already (`TILESETS = 0xC7BE`), and re-deriving one is the largest measured waste in
  this project.
- A water route's walkable region is tiny and proves nothing: on map 30 it is **six cells**,
  (6,4)..(11,4), a one-tile strip touching no water at all. "Cannot walk to water" is the normal
  reading, not a wall. You cross by surfing off the strip.

Spend the budget **driving toward Cinnabar (map 8)**, not on ROM archaeology.

## Where the earlier run got to

Your own record: `docs/learnings/badge7-8-surf-gap-and-heal-20260901.md`. It got out of the Safari
Zone, healed at Fuchsia's Center (map **154**, found by interior template — it is not in the
hardcoded CENTERS table), added `surf_cross`, and **crossed the first water segment into map 30**.
Then it stopped on a wall it diagnosed exactly:

- **A water route is a land plaza with water edges**, not a lake. Map 30 is 63/1080 walkable, map
  31 is 100/1800, and neither plaza reaches the far edge — so the crossing is walk, then SURF,
  then walk, within one map.
- **Gyarados was the LEAD, so it auto-fought the crossing encounter, lost at L20, and fainted** —
  and Gen 1 **omits fainted members from the POKeMON menu**, so SURF became unusable. The only
  surfer in the party was the one that was down.

Two engine bugs from that leg are now FIXED (`9b314dc`), so do not re-derive them:
- `window_row` blanks the cursor glyph; `field_moves` no longer reads "AAAAAAAASURF" as SURF.
- `use_field_move(species="Gyarados")` picks by the name the menu prints, via `Rig.menu_row_of`,
  because a party index is not a menu index when anyone is fainted.

**So separate the roles, which is what your own record recommends:** put a level-99/100 mon in the
lead with `Rig.lead_swap` so it takes the crossing battles, keep **Gyarados awake and off the
lead**, and arm SURF with `species="Gyarados"`. Heal at map 154 whenever anything is down —
a fainted surfer is an unusable surfer.

Batons: `b7_healed.state` (map 154, Fuchsia Center) and `b7_badge.state` (map 30, one segment in).

## The baton

`data/local_runs/roster-bench/surf_taught.state` — map **222**, the Safari Zone's SECRET HOUSE,
badges `0b00111111`. Party: **Gyarados L20 (knows SURF, at 0 HP)**, Dugtrio 100, Primeape 99,
Pidgeot 99, Hypno 99, Charizard 100 (knows CUT). Bag holds **HM03 SURF**, HM01, OLD ROD, CARD KEY,
SILPH SCOPE, POKe FLUTE, S.S.TICKET.

**Heal first.** Gyarados is down; SURF is a field move so it works anyway, but do not walk into a
gym with a fainted party.

## Ground truth — look it up, never recall it

World facts come from `references/rom_truth.json` (`scripts/rom_truth.py`), never from memory.
This cartridge differs from recollection and the cost is measured. Never cat that file — query it.
Recalled lore may generate a hypothesis to test; it is never a conclusion to ship. **What the game
prints on screen is the instruction stream** — `Rig.talk` now records it into the sink as a
`discovery` event, so read it rather than assuming.

Measured facts, each cheap to re-verify:

- **Item balls carry their contents.** `Rig.ball_contents(map)` names them; `truth["machines"]`
  says what a TM/HM teaches (HM03 is SURF). The **SECRET KEY** is an item ball at **map 216,
  (5,13)** — a lookup, not a hunt.
- **Cinnabar is map 8** and connects only `north -> 32` and `east -> 31`. Both are water. That is
  what SURF is for.
- **`Rig.surf_onto(face)` has never been driven live.** It uses the field-move menu and judges
  success by *position*. Expect it to need fixing; measure what the screen says when it refuses.
- **Viridian's gym (map 1) opening condition is UNVERIFIED.** Do not assume seven badges opens it.
  Measure it: walk to the door and read what the game says.

## Getting out of the Safari Zone

The zone is a maze, not a fight, and its doors are **thresholds** — standing on one does nothing,
the step *through* fires it. Its encounters have **no FIGHT** (BALL / BAIT / THROW ROCK / RUN), so
the normal battle turn hangs; `Rig.battle_flee()` runs, and RUN sits where it always does.

Measured route out: house -> 219 (the (20,0) pocket) -> **(2,35) up** -> 218 -> walk the south
edge east -> **(20,35)/(21,35) down** -> 220 -> the south mats **(14,25)/(15,25)** -> 156 ->
Fuchsia (map 7). 219's two pockets are joined *through* 218; only the (20,0) landing reaches the
house.

## The loop body is `scripts/supervisor.py`

    uv run python scripts/supervisor.py run --state <baton> --goal <map[,map,...]> \
        --budget 1800 --heal --engage --clear-floor --bank <name> --live-label "<what this is>"

`--heal` finds a Pokemon Center by interior template (14x8, tileset 6, nurse at (3,1)) and talks
across the counter. `hunt`, `explore`, `survey` and `lift-tour` are the other subcommands; read
`--help` before inventing anything.

**If the supervisor lacks a capability, add it there with a test** (`tests/test_supervisor_leg.py`
drives the whole loop against a fake rig). A scratchpad script solves one leg and teaches the repo
nothing. Tests green (`uv run pytest`) and `uv run ruff check .` before any commit touching
`scripts/`; this repo requires **100% coverage**.

## Discipline

- Cite measured coordinates, never theories. Read the refusal before reasoning about it.
- A door no walk reaches may be a **ride** (`road.ride_pad`, `road.rides_to`, `road.pad_route`).
- The bag caps at **20 slots** and a full bag silently refuses gifts and purchases — that is why
  the SECRET HOUSE handed over nothing until a slot was freed. Check it before any errand.
- Commit as you go; an uncommitted diff is a lost diff.
- Every wall you exhaust gets `docs/learnings/<leg>-stuck-<run_id>.md` with the facts and every
  action tried. A documented failure is worth more than an undocumented badge.

## Definition of done

1. `BADGES` reads `0b01111111` (badge 7) and then `0b11111111` (badge 8), banked as
   `badge7.state` / `badge8.state`.
2. Events landed in `data/telemetry/game/<UTC-date>.jsonl` and the tape exists.
3. What the next run needs is in the repo — engine fix, test, or `docs/learnings/`.
