# Mission: badge 7 first — Cinnabar is on the road to Viridian

You are an autonomous operator on this repo. Use `uv run ...` for all Python (AGENTS.md). Print
`date` at the start and before any summary. Work the whole budget; do not stop early.

Six badges are won. **Badge 7 comes before badge 8, and it is not a preference — it is the
topology.** Extracted from this cartridge:

    Fuchsia(7) --south--> 30 --west--> 31 --west--> Cinnabar(8)     badge 7: gym map 166 via warp (18,3)
    Cinnabar(8) --north--> 32 --north--> 0 --north--> 12 --north--> Viridian(1)   badge 8: gym map 45 via (32,7)

**Cinnabar is the waypoint between Fuchsia and Viridian.** Every previous badge-8 leg tried to
reach Viridian overland round the east side and died in map 15's sealed pocket. That pocket is
real (`survey_pocket`: 114 cells, x 63..89, y 10..15, 0 talking walls, nothing on the exit row 17)
— but it was never the road. **The road is water, and it serves both badges.**

## The baton — this one has the surfer

`data/local_runs/roster-bench/b8_BATON_island_gyarados_safe.state` — map **30 at (6,9)**, badges
`0b00111111`, **already on the water route**. Party: **Gyarados L20 73/73** (`knows_move("SURF")`
returns index 0), Dugtrio L100, Primeape L99, Pidgeot L99, Hypno L99, Charizard L100. Bag holds
**HM03**, HM01, OLD ROD, CARD KEY, SILPH SCOPE, POKe FLUTE, S.S.TICKET — 20/20, so `make_room()`
before any pickup.

**Do not use `bicycle.state` or any `v8*`/`cerulean_bike` baton.** A badge-8 leg traded Gyarados
away there — those saves have Gloom in its slot and have lost **HM03 and the OLD ROD**. The bicycle
is not needed for this route: Cycling Road (map 28) sits between 27 and 29 on the east side and is
not on the way to either remaining badge.

## Four surf bugs are fixed since the last crossing attempt — do not re-derive them

The last time anyone tried this crossing, all four of these were broken:

1. **`_arm_surf` judges the world, not the menu.** It used to return True on a refusal, and the
   refusal text box then swallowed every input — `probe_step()` False in all four directions. Three
   legs read that frozen world as a "water/rock checkerboard" and wrote it into `docs/learnings/`
   as measured geography. **It is fiction; ignore any doc that says it.** A False from `_arm_surf`
   now means the game genuinely refused, and the sentence is emitted as a `surf.refused` event.
2. **`knows_move(name)`** finds the surfer by move id from the cartridge, not a species literal.
3. **`road.surf_cross` treats a wild encounter as a fight, not a wall.** An encounter *cancels* the
   step, which is byte-identical to a refusal; reading it as solid is what produced `stuck-on-edge`
   in open water.
4. **`road._water_cross` routes the water** instead of sliding along it, because the geometry is
   measured: **map 30's west edge opens on rows 40..52 ONLY**, the island approach is row 10, and
   the column between carries a solid notch at rows 38..39. A straight run west can never cross.

Keep **Gyarados off the lead and awake** — Gen 1 omits fainted members from the POKéMON menu, so a
fainted surfer is an unusable one, and that ended a leg. Put an L99/L100 in front to take the
crossing encounters.

## The job

1. **Cross to Cinnabar (map 8)** and bank it. This is the hard part and it is the whole unlock.
2. **Badge 7**: gym warp (18,3) -> map 166, Blaine. Your party outclasses it by ~80 levels.
3. **Then keep going north**: `8 -> 32 -> 0 -> 12 -> 1`, and try Viridian's gym (map 1, warp
   (32,7) -> map 45). **Its opening condition is UNVERIFIED** — nobody has ever walked to that
   door. Read what it says, badge or no badge.

## How to work

- **You route.** `supervisor.py run --goal 8` plans it and `_reroute_around` re-plans on failure.
  Do not accept a hand-written hop chain from anyone, including this file — the chains above are
  the connection graph, not instructions.
- **Recon is a step**: `LegRunner.recon` talks to the bodies the cartridge lists before the first
  consult, and the Investigator picks which body is worth the budget. **Talk to things.** The arc
  that engaged 82 bodies won its badge; the arc that engaged 0 lost five legs.
- **The window layer is sticky** — gate every dialogue read on `talking = not r.probe_step()`.
- **A body with no walkable neighbour is not unreachable** — `road.counter_stands` talks across a
  counter. Every mart in the game is reachable now, you have ₽92,360 and **no Poké Balls**.
- **Never `pkill -f <pattern>` matching your own command line** — two legs killed themselves that
  way; the harness blocks it now. Kill by PID.
- **Do not emit a `discovery` event per frame.** Two legs wrote 221k and 1.25M events. Record each
  distinct sentence once.
- Do not diff RAM or hunt ROM addresses. Five legs died that way.

## Definition of done

1. `BADGES` reads the seventh bit, banked `badge7.state`. Then the eighth if you get there.
2. **What the Viridian gym door said**, written down, whether or not you reach it.
3. `docs/learnings/badge7-first-<run_id>.md` — the crossing route that worked (or every row of the
   40..52 band that refused), every body spoken to, and what the next run needs.
