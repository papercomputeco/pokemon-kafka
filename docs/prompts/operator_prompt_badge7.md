# Mission: badges 7 and 8

You are an autonomous operator on this repo. Use `uv run ...` for all Python (AGENTS.md). Print
`date` at the start and before any summary. Work for the whole budget; do not stop early.

Six badges are won and **SURF is taught**. What remains is Cinnabar (Blaine, badge 7) and
Viridian (Giovanni, badge 8).

## Read this first: three legs were misdiagnosed, and the cause is fixed

Earlier learnings docs describe a **"water/rock checkerboard"** on map 30 and **"unreliable surf
position-tracking"** in the rig. **Both are wrong.** They were one engine bug, fixed in
`51b8290`. Do not plan around them, and do not trust any earlier doc's geography claims about
map 30's water. Measured at map 30 (6,9):

- `_arm_surf` sent its keystrokes and **returned True even when the game refused** with
  *"No SURFing on GYARADOS here!"*.
- The refusal text box then **swallowed every input** — `probe_step()` was False in all four
  directions. The world was *frozen*, not blocked. Six B presses restored it instantly.
- So "I surfed and then nothing moved anywhere" was never geography. It was this.

What is true now:

- `_arm_surf` judges by the **position** — using SURF carries the player onto the water, so the
  world is the predicate and the menu is not. **A False now means the game genuinely refused.**
- It clears the text box first, and emits a `surf.refused` event carrying the sentence.
- `Rig.textbox()` returns what the game is currently saying.
- `Rig.knows_move(name)` finds the surfer by **move id** from this cartridge's move table, not by
  species name. Verified live: SURF -> party index 0, CUT -> index 5.
- `road.surf_cross` treats a wild encounter as a fight, not a wall — an encounter *cancels* the
  step, which used to be indistinguishable from a refusal.

## Recon is a step now, and the crossing geometry is measured

**`LegRunner.recon` runs before the first consult on any wall** — it talks to the bodies the
cartridge lists and the sentences reach the seats under `HEARD:`. Across four legs this arc spoke
to nobody while treating ten `trainer` sprites as obstacles. Two of them, **(8,7) and (13,7)**,
are adjacent to walkable cells on map 30. Talking to (13,7) opens a battle your L99/L100 party
wins for free. **Engage them.**

The crossing geometry, measured by leg 5 and now in `road._water_cross`:

- **Map 30's west edge opens on rows 40..52 ONLY.** The island approach is on **row 10**, and the
  column between carries a **solid notch at rows 38..39**. A straight run west from the island
  can never cross — that is why four legs failed there, and why the west-edge cells (4,6)..(4,9)
  all refuse. **Go south to the rows 40..52 band first.**
- `road._water_cross` proposes a path on the water model and verifies it press-by-press, letting
  each refusal re-plan. A step cancelled by a wild is fought and re-stepped, not read as solid.
- The island is **43 cells** (x 4-13, y 0-9). An earlier doc says six; that is wrong.

Two refusals, and they mean different things — the sink records both:
`"No SURFing on GYARADOS here!"` (standing, that tile will not launch) and
`"There's no place to get off!"` (already on the water, that way is closed).

## The baton and the job

`data/local_runs/roster-bench/b8_BATON_island_gyarados_safe.state` — map 30 at **(6,9)**, badges
`0b00111111`, party whole: **Gyarados L20 73/73** (the only surfer, keep it off the lead and
awake) plus Dugtrio L100, Charizard L100, Primeape L99, Pidgeot L99, Hypno L99.

**SURF is refused at (6,9). Find a cell where it is not.** The island is a short walkable strip;
walk it, try `_arm_surf()` from each cell and each facing, and read `Rig.textbox()` on every
refusal. The game distinguishes *"No SURFing here!"* from *"There's no place to get off!"* —
those are two different problems and the sentence tells you which one you have.

Then chain hops west to the map-31 boundary, cross to **Cinnabar (map 8)**, and take the gym
warp at **(18,3) -> map 166** for Blaine. Badge 8 is Giovanni in Viridian; **the gym's opening
condition is UNVERIFIED — measure it, do not assume seven badges opens it.**

## Discipline — this is where the budget has been lost

- **Do not** re-derive tile tables, diff RAM, or hunt ROM addresses. Three legs died that way.
  `rom_truth` locates every table by content signature already (`TILESETS = 0xC7BE`).
- **If a probe says nothing works in any direction, suspect the harness, not the cartridge.**
  That single check would have saved three legs.
- What the game prints on screen is the instruction stream. Read the refusal before reasoning
  about it. `Rig.talk` and `Rig.say` record sentences into the sink.
- World facts come from `references/rom_truth.json`, never from recall — this cartridge differs
  from recollection and the cost is measured. Query that file; never `cat` it.
- The bag caps at **20 slots** and a full bag silently refuses gifts and purchases.
- Commit as you go; an uncommitted diff is a lost diff.

## The loop body is `scripts/supervisor.py`

    uv run python scripts/supervisor.py run --state <baton> --goal <map[,map,...]> \
        --budget 1800 --heal --engage --clear-floor --bank <name> --live-label "<what this is>"

`--heal` finds a Pokemon Center by interior template (14x8, tileset 6, nurse at (3,1)). Fuchsia's
is map **154**. `hunt`, `explore`, `survey` and `lift-tour` are the other subcommands; read
`--help` before inventing anything.

If the supervisor lacks a capability, add it there **with a test** (`tests/test_supervisor_leg.py`
drives the whole loop against a fake rig). A scratchpad script solves one leg and teaches the repo
nothing. `uv run pytest` and `uv run ruff check .` before any commit touching `scripts/`; this
repo requires **100% coverage**.

## Definition of done

1. `BADGES` reads `0b01111111` (badge 7) and then `0b11111111` (badge 8), banked as
   `badge7.state` / `badge8.state`.
2. Events landed in `data/telemetry/game/<UTC-date>.jsonl` and the tape exists.
3. What the next run needs is in the repo — engine fix, test, or `docs/learnings/`.
   Every wall you exhaust gets `docs/learnings/<leg>-stuck-<run_id>.md` with the facts and every
   action tried. A documented failure is worth more than an undocumented badge.
