# Demo runs

Curated, replayable agent runs for the 12-beat talk demo. Committed so a fresh
clone can replay them without an emulator, ROM, or API key.

## Replay

```bash
uv run python -m viewer --runs-dir demo-runs   # http://localhost:8200
```

Each beat has a stable folder (`beat1-…` … `beat12-…`) and a label starting with
its beat number, so the viewer's beat routes resolve: open `/3` to jump straight
to beat 3.

Beats 7–9 are the "harder frontier" set — see the `forest-navigation-demo`,
`bug-catcher-demo`, and `discovery-signs-demo` skills:

- `beat7-forest-nav` — maps Viridian Forest under 9x10 visibility (navigation is hard)
- `beat8-bug-hunt` — type-effective bug battles on Route 2 into the forest
- `beat9-discovery` — decodes signs / dialogue / Pokedex flavor into `discovery` events

Beats 10–11 carry the run past the forest, where every earlier field had stalled:

- `beat10-gym-brock` — Brock falls in 11 turns and Badge 1 lands (`badges: 1`,
  `brock_won: true`). Recorded from `states/pre-brock.state`, the
  `--save-state-on-trainer` baton of a `pewter_to_badge` relay; `--frame-interval 1`
  because the whole beat is one fight.
- `beat11-mt-moon` — the road no lane had ever finished: out of the Gym with the
  badge, across Pewter, over all 70 tiles of Route 3, and into Mt. Moon 1F (map 59)
  in 364 turns. Recorded from `data/relay/gym-beat/batons/pewter_to_badge.state`
  with `--stop-on-map 59`.

- `beat12-mt-moon-clear` — **the first Mt. Moon clear**: 880 turns from the 1F entrance seed
  through all three floors — both springs defused, the fossil doorway opened by fighting the
  Super Nerd (turn 823), out the wLastMap exit door to Route 4's east side at 25 HP. Recorded
  from `states/mtmoon_seeds/mtmoon1f_entrance_hp42.state`; deterministic (re-running reproduces
  the same 880 turns). See `benchmarks/2026-08-22-skill-matrix.md` for how six models failed
  this leg and collectively wrote the fix.

- `beat13-oddish-recruit` — **the first recruit, on camera**: 17 turns in the Route 24
  grass pocket, a wild L12 Oddish (the roster optimizer's #2 water counter), three Poke Balls,
  and the party grows to two — carrying the new labeled `encounter` events (`disposition:
  "caught"`) in its committed stream. Recorded from the badge-2 lineage
  (`--stop-on-party 2 --catch Oddish`); the roam driver walks the ROM's own extracted grass
  cells. The Paras twin
  came from starting EARLIER instead (the operator's call): the badge-1 lineage still stands
  west of the one-way ledges.

- `beat14-paras-recruit` — **the Paras hunt**: the roster optimizer's #1 water counter,
  caught where the ROM's own wild tables put it. From the Brock-victory seed: Pewter Mart
  errand (6 balls), Route 3, into Mt. Moon, and the recruit patrol walks ladder-to-ladder
  until a wild L10 Paras appears on B1F — two balls, turn 555, sixteen fights of XP on the
  way. The patrol's three measured lessons (never anchor ON a warp, never yield a roamable
  floor to the ladder-hunter, never answer a standstill with "a") are in the agent.

- `beat17-articuno` — **the legendary**: Seafoam Islands B3 to B4 on the 7-badge run, every step
  measured rather than recalled. The twelve STRENGTH pushes that fill both floor holes (the twelfth is
  the push the boulder oracle had logged "unreachable" for a day — the tile-pair model's verdict, not
  the game's), the fall through (6,16) into B4's west water, the shore at (7,11) that now accepts SURF
  ("The current is much too fast!" is gone), the left channel to the platform, "Gyaoo!", and the catch:
  Dugtrio SAND-ATTACK x2, Hypno POISON GAS, then an ULTRA BALL every turn — Articuno L50 on the 12th
  ball, "transferred to BILL's PC". Recorded from `states/seafoam_seeds/seafoam_b3_main.state` with
  `frame_interval=1`. The catch is a race against the poison tick (~9 HP a turn); the recipe that
  loses is the one that also SCRATCHes first.

### Why beat 11 needed a fix first

`badge_to_mtmoon` had never landed — six genome lanes × 12,000 turns all wedged on
Route 3 at (3,10), byte-identical. Route 3's warp table is empty, so the leg was
owned by a blind heuristic march that pressed **east**; the map's east edge is solid
for all 18 rows and its only exit is the **north** edge at x 57–63, so no amount of
turns could finish it. `agent.py:_truth_step` now plans that leg over the extracted
ROM collision grid instead. Three things it has to get right, each of which cost a
run to find:

- **Bodies aren't in the grid.** A defeated Gen 1 trainer keeps standing on its tile
  (`rom_truth.sprite_tiles`).
- **A stall is not a wall.** Walking into a trainer's line of sight freezes the lane
  with its dialogue up and `text_box_active` reading False. Truth presses A to clear
  the challenge and only calls a tile a wall after it keeps failing with nothing left
  to dismiss — scoring the freeze as a refusal sealed the crossing at (11,6).
- **An edge hop fires no warp.** The engine hands the player over only when they walk
  *off* the side, so arriving on the exit tile is not arriving. The first crossing to
  survive Route 3 ended standing on (57,0) and stalled there for the rest of the run.

Two things this leg exposed, both now fixed:

- **The NAV spread was inert here.** `stuck_threshold` and `waypoint_skip_distance` are
  read by the waypoint `Navigator`, and `axis_preference_map_0` is map 0 only — none of
  which this leg consults, so all six lanes returned byte-identical fitness: six lanes'
  compute for one lane's information. The strike count that decides when a stalled step
  is called a wall is now evolvable (`truth_refuse_strikes`) and the spread varies it, so
  the lanes diverge on something real — `fast_stuck` at 12 strikes now *fails* the
  crossing, which is the finding the six identical lanes could never have produced.
  `relay.report_inert_spread` also says so out loud whenever every lane of a spread comes
  back identical, so the waste is never paid silently again.
- **`brock_won` false-positived after the badge.** `is_brock` falls back to "trainer at
  level >= 12", and `_resolve_brock_badge` reads the badge bit — which a seeded post-badge
  leg already holds. Beat 11's first recording claimed `brock_won: true, brock_turns: 4`
  off a Route 3 trainer, on a badge won by a different run. Brock is the fight that
  *earns* the badge, so holding it first now disqualifies the fight.

Beat 15 is the first *blocker* beat — a wall that stood for a whole session, resolved by
reading the cartridge instead of the map:

- `beat15-surf-unblocked` — badges 7-8 need SURF, and the TM/HM bitfield says **no member of the
  party can learn HM03** (Charizard has Cut+Strength, Pidgeot Fly, Hypno Flash, Dugtrio none).
  HM03 sits in no item ball on any map, so it is an NPC's to give. The ROM's own text names the
  place — "FISHING GURU in VERMILION CITY!" — and the beat walks it: find him in map 163 (three
  decoy houses first: a Farfetch'd trader, a letter to PIPPI, the Fan Club chair), take the OLD
  ROD, cast off the dock at (18,29), and land the Magikarp that becomes a Gyarados — which learns
  Surf *and* Strength. 241 turns, one cast.

- `beat16-bicycle` — **the counter: one fix, two doors**. 191 frames. The badge-8 overland
  route is blocked at `29 -> 28` and the cartridge says why in its own words: *"You need a
  BICYCLE for CYCLING ROAD!"* `BICYCLE` is item 6 and `BIKE VOUCHER` is item 45, and **neither
  is an item ball on any map** — both come from a person, which makes it a talking problem. The
  shop rules money out: *"Sorry! You can't afford it!"*

  A recon leg reached that shop holding the voucher and reported `body (6,2) unreachable/no
  response`. It was right that (6,2) has no walkable neighbour and wrong that the clerk was
  unreachable — **you talk across the counter**, from (4,2) facing right, the geometry
  `center_counter` already hard-coded for Center nurses and nobody generalised. The beat runs
  the exchange (*"Oh, that's… A BIKE VOUCHER!"* → *"exchanged the BIKE VOUCHER for a
  BICYCLE"*), then walks straight to Cerulean's MART (map 67, clerk at (0,5)) and opens that
  too: *"Hi there! May I help you?"* … *"POKé BALL? That will be ₽200. OK?"*

  That second door is the point. 778 bodies have a walkable neighbour, **15 do not but sit
  behind a counter, and seven of those are the mart template — one per city.** Every shop in
  the game was closed to this project since the first run, with `quartermaster.buy()` already
  written and ₽92,360 unspent. Recorded from `cerulean_bike.state`;
  `benchmarks/2026-09-02-crew-vs-solo.md` has the census.

## Grid order## Grid order

`viewer/store.py` sorts run folders reverse-alphabetically, so `beat10`/`beat11`
land between `beat2` and `beat1` in the grid. The deep links `/10` and `/11` —
which is how the talk actually navigates — are unaffected. Zero-padding every
folder to `beat01…beat12` would fix the order but churns all 12 folders plus the
skills that reference them by name.

## Not committed

`demo-runs/states/` holds the PyBoy savestates used to record beats 3–12. They
are gitignored (binary, regenerable) — recording is a local/presenter step, the
frames are the shipped artifact. `states/mtmoon_seeds/MANIFEST.md` records where
each seed came from.
