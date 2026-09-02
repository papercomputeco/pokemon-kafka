# Mission: badges 7 and 8

You are an autonomous operator on this repo. Use `uv run ...` for all Python (AGENTS.md). Print
`date` at the start and before any summary. Work for the whole budget; do not stop early.

Six badges are won and **SURF is taught**. What remains is Cinnabar (Blaine, badge 7) and
Viridian (Giovanni, badge 8).

## Where the last run got to (read this first)

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
