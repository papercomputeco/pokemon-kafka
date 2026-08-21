# Demo runs

Curated, replayable agent runs for the 11-beat talk demo. Committed so a fresh
clone can replay them without an emulator, ROM, or API key.

## Replay

```bash
uv run python -m viewer --runs-dir demo-runs   # http://localhost:8200
```

Each beat has a stable folder (`beat1-…` … `beat11-…`) and a label starting with
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

## Grid order

`viewer/store.py` sorts run folders reverse-alphabetically, so `beat10`/`beat11`
land between `beat2` and `beat1` in the grid. The deep links `/10` and `/11` —
which is how the talk actually navigates — are unaffected. Zero-padding every
folder to `beat01…beat11` would fix the order but churns all 11 folders plus the
skills that reference them by name.

## Not committed

`demo-runs/states/` holds the PyBoy savestates used to record beats 3–11. They
are gitignored (binary, regenerable) — recording is a local/presenter step, the
frames are the shipped artifact. `states/mtmoon_seeds/MANIFEST.md` records where
each seed came from.
