# Mission: badge 8 (Giovanni, Viridian) — overland, no surfing

You are an autonomous operator on this repo. Use `uv run ...` for all Python (AGENTS.md). Print
`date` at the start and before any summary. Work the whole budget; do not stop early.

Six badges are won. **Get badge 8. Ignore badge 7 entirely** — Cinnabar is water-locked and has
consumed five legs. This one needs no SURF.

## The route is overland and it is a lookup

`rom_truth.route` returns a *sea* path Fuchsia→Viridian because it is fewer hops. **Do not use
it.** A land path exists and avoids maps 30/31/8/32 completely:

    7 -> 29 -> 28 -> 27 -> 6 -> 18 -> 10 -> 16 -> 3 -> 15 -> 14 -> 2 -> 13 -> 1

Then Viridian's gym is a **warp at (32,7) on map 1 -> map 45**. Verified from
`references/rom_truth.json` this run.

Pass the chain explicitly so the router cannot pick the sea:

    uv run python scripts/supervisor.py run \
        --state data/local_runs/roster-bench/b8_BATON_island_gyarados_safe.state \
        --goal 7,29,28,27,6,18,10,16,3,15,14,2,13,1 \
        --budget 2400 --heal --engage --bank vir_approach \
        --live-label "badge 8 — overland to Viridian"

Then a second leg for the gym itself (`--goal 45 --engage`), which fights until `BADGES` changes.

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
