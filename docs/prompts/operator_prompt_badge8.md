# Mission: badge 8 (Giovanni, Viridian) — overland, no surfing

You are an autonomous operator on this repo. Use `uv run ...` for all Python (AGENTS.md). Print
`date` at the start and before any summary. Work the whole budget; do not stop early.

Six badges are won. **Get badge 8. Ignore badge 7 entirely** — Cinnabar is water-locked and has
consumed five legs. This one needs no SURF.

## You route. I do not.

**Goal: `BADGES` gains the eighth bit. Giovanni is in Viridian's gym — map 1, warp (32,7) -> 45.**
That is the objective. The route is yours to find; `scripts/supervisor.py run --goal 45` plans it,
and `_reroute_around` already bans a failed hop and re-plans, so a wall is a measurement, not a
dead end.

I previously handed over a hand-computed chain. That was wrong: it removed the navigation problem
from the navigation seat, and worse, pinning map 28 in the goal list dragged the leg back to a hop
it had already correctly rerouted around.

Measured constraints — facts to route *within*, not a path to walk:

- **The sea crossing is UNSOLVED.** Maps 30 / 31 / 8 / 32 are water (6% walkable vs 30-79% for
  land). `rom_truth.route` will offer a Fuchsia->Viridian path through them because it is fewer
  hops. Five legs have died there. **Treat any hop into 30/31/8/32 as banned and route by land.**
- **`29 -> 28` is refused `no-path`** (measured last leg). Ban it and re-plan; do not retry it.
- Land routes to Viridian exist heading **east** out of Fuchsia. Find one.
- The baton starts on the map-30 island, whose walkable region reaches **row 0**, and map 30
  connects `north -> 7`. One hop north puts you on the mainland. You never need SURF again.

## NEVER pkill -f a pattern your own command line contains

The last leg ended itself by running `pkill -f "supervisor.py run"`. Its own shell command
contained that string, so the pattern matched its own process and killed the whole run. This has
now cost three separate sessions.

- Kill by **PID**: `kill 12345`.
- If you must match, bracket it so the pattern cannot match itself: `pkill -f "supervisor[.]py"`.
- `pgrep -f pi-coding-agent` in the SAME command line will also make a later `pkill` match you.

## The baton

`data/local_runs/roster-bench/b8_BATON_island_gyarados_safe.state` — map 30 at (6,9), badges
`0b00111111`. Party: Gyarados L20 73/73, **Dugtrio L100, Charizard L100, Primeape L99,
Pidgeot L99, Hypno L99**. That team beats Giovanni comfortably; this is a navigation job.

The island's walkable region reaches **row 0**, and map 30 connects `north -> 7`, so the very
first hop puts you on the mainland at Fuchsia. **You never touch water on this mission.**

## The one genuine unknown — go and read it

**Viridian gym's opening condition is UNVERIFIED.** Nobody on this project has ever walked to
that door. Do not assume seven badges opens it, and do not assume it is shut.

**Walk to the warp at (32,7) on map 1 and read what the game says.** If a body blocks it, talk to
it and record the sentence. That single observation is worth more than any reasoning about it,
and it is the whole reason this mission is cheap: the route is known, only the door is not.

## Recon is a step, not advice

`LegRunner.recon` now runs before the first consult on any wall: it talks to the bodies the
cartridge lists for the map and the sentences reach the seats under `HEARD:`. Across four legs of
the badge-7 arc the crew engaged **zero** bodies and reasoned from failure codes alone — that is
what cost those legs.

- **When something refuses, read the screen before theorising.** `Rig.textbox()` returns what the
  game is saying, but the window layer is **sticky** — gate it on `probe_step()`, which is False
  exactly while a text box is up.
- **If a probe says nothing works in any direction, suspect the harness, not the cartridge.**
- Talk to NPCs on the way. Gyms and towns hand things over to people who speak to them.

## Discipline

- **Do not** re-derive tile tables, diff RAM, or hunt ROM addresses. Five legs died that way.
- World facts come from `references/rom_truth.json`, never recall. Query it; never `cat` it.
- The bag is **FULL (20/20)** — a full bag silently refuses gifts and purchases. `Rig.make_room()`
  tosses the largest stack if something needs a slot.
- Commit as you go; an uncommitted diff is a lost diff. `uv run pytest` and `uv run ruff check .`
  before any commit touching `scripts/`; this repo requires **100% coverage**.

## Definition of done

1. `BADGES` reads `0b10111111` or better — the eighth bit set — banked as `badge8.state`.
2. Events in `data/telemetry/game/<UTC-date>.jsonl`, and the tape exists.
3. **What the Viridian gym door actually said** is written down, whether it opened or not.
   A documented failure is worth more than an undocumented badge.
