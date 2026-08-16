# Evals

Regression evals distilled from `docs/learnings/` and `pokedex/memory/observations.md`. Each case
is one obstacle the operators actually hit, expressed as: a seed savestate, a stop condition, a
turn budget, and pass criteria on the lane's `fitness.json`. They run the real headless agent
(`scripts/agent.py`) — no LLM — so they are deterministic per (state, genome) and cheap
(a few thousand turns ≈ seconds).

```
uv run python scripts/run_evals.py                 # all cases in evals/cases/
uv run python scripts/run_evals.py --case route1-flee-loop
uv run python scripts/run_evals.py --dry-run       # print the agent commands only
```

Results land in `evals/results/<YYYY-MM-DD>.md` (append-only, dated like `benchmarks/`), one row per
case: pass/fail, turns, final map, lead HP. Run them before merging an agent/route change and after
promoting a genome into `notes.md`; a case flipping from pass to fail is the regression signal the
learnings were written to catch.

## Case format (`evals/cases/<name>.json`)

```json
{
  "name": "route1-flee-loop",
  "learning": "docs/learnings/route1-navigation-flee-loop.md",
  "category": "battle",
  "seed_state": "demo-runs/states/route1.state",
  "stop_on_map": 51,
  "max_turns": 2000,
  "genome": {},                       // EVOLVE_PARAMS overrides; {} = notes.md/default
  "pass": {"final_map_id": 51, "min_lead_hp": 5}
}
```

Savestates referenced here live in `demo-runs/states/` (gitignored — copy them from a run's
`batons/` as documented in `docs/learnings/README.md`). `route2-weedle-flee-loop.state` is a `--save-state-every 1` checkpoint at turn 1200 of the relay `base` lane
from `route1.state` in a *clean* worktree (the main checkout's `notes.md`/`pokedex/memory` change the
agent's path) — the flee loop is self-sustaining, so any turn after it starts is inside it.
`pewter-pokecenter.state` is captured from
any `forest_to_pewter` baton with
`uv run python scripts/agent.py rom/pokemon_red.gb --load-state <baton> --save-state-on-map 58:demo-runs/states/pewter-pokecenter.state --stop-on-map 58 --max-turns 1500 --no-self-heal --no-in-run-heal`.

## Cases

| case | category | from | asserts |
|---|---|---|---|
| route1-flee-loop | battle | route1-navigation-flee-loop | reaches Viridian Forest (51) from `route1.state` in ≤2000 turns with lead HP ≥5 — fails on main until the flee-loop fix lands |
| forest-crossing-healthy | navigation · battle | viridian-forest-turn-385-blackout | from the 17-HP forest entrance, `very_cautious` reaches Pewter (2) in ≤3000 turns with lead HP ≥5 |
| forest-crossing-1hp | navigation · battle | viridian-forest-1hp-entry-unresolved | documents the known failure: from the 1-HP entrance the default genome does **not** reach Pewter in 3000 turns (expected_fail) |
| pewter-to-gym | navigation | brock-approach-deadend / pewter-corrupted-transition-save | from the forest→Pewter baton, reach Pewter Gym (54) in ≤4000 turns. Passes since the Pewter routes.json fix (the old first waypoint (13,25) was the Pokémon Center door and the old "gym" waypoint (16,11) open ground; the door is (16,17), reached from the west via x=19 → y=13 → x=10 → y=18) plus the WorldMap planner for route waypoints — 44 turns |
| low-hp-wild-battle | battle | route1-navigation-flee-loop | from *inside* the Route 2 Weedle battle at 4/23 HP (the flee-loop state itself), reach the Forest (51) alive in ≤600 turns. `main`: 600 turns, 0 encounters — frozen in the loop. Qwen 3.8's wedge watchdog: 8 battles won, still 2 HP on Route 2 — loop broken, health not. The `battles (won/enc)` column tells the two apart |
| pewter-pokecenter-exit | navigation | 2026-08-16-local-relay-laguna-xs | from inside the Pewter **Pokémon Center** (map 58, healed party), reach the Gym (54) in ≤3000 turns — documents the wedge every 08-15/16 model hit at (11,3): the agent heals and then presses into the counter for thousands of turns. Map 58 was mislabelled "Pewter Gym" in the 08-15 Haiku learning; the Gym is 54. Passes since the building-exit rule (GO_NORTH no longer pilots north inside off-corridor buildings; the agent walks to the nearest warp from the map's own warp table and steps off the mat) — 44 turns |

## Model evals (`evals/model-cases/`)

The cases above score the *agent* — deterministic, no LLM. `evals/model-cases/` scores the
*operator model*: each case replays an obstacle from `docs/learnings/` as a question whose real
answer is on record, plus a rubric of the claims that answer has to contain.

```
uv run python scripts/run_model_evals.py                          # every local -128k variant
uv run python scripts/run_model_evals.py --models laguna-xs-128k  # explicit list
uv run python scripts/run_model_evals.py --case flee-loop-cap --show
```

Answers are saved under `data/evals/model/<date>/`; the table is appended to
`evals/results/models-<YYYY-MM-DD>.md`. Runs at temperature 0 with a fixed seed, so a rerun on the
same model reproduces.

| case | from | asks |
|---|---|---|
| flee-loop-cap | route1-navigation-flee-loop | given the real `choose_action` excerpt, why does the wild battle loop forever? |
| transition-save-corruption | kimi-k2.6/pewter-corrupted-transition-save | root-cause a baton saved on the first frame of a map change |
| pewter-waypoint-wall | haiku-4.5/pewter-gym-navigation | five models tuned genomes for hours against the same wall — what is actually wrong? |
| context-discipline | benchmarks/2026-08-15-mt-moon-relay | how do you search a 1.4 GB log under a 40 KB tool cap? |

Scoring caveats, because they decide how much the number is worth:

* **Rubric match, not a judge.** An item scores when any of its regex paraphrases appears. That
  rewards *saying the true thing*, so the score is a floor: a model can be right in words the rubric
  does not know. Read the saved answer before trusting a low score.
* **`anti` items subtract.** `flee-loop-cap` penalises fabricated code facts — gpt-oss-20b claimed
  wild battles are `battle_type == 0` when the excerpt in its own prompt shows `== 1`. Confident
  and wrong must rank below hedged and right.
* **No visible answer scores 0**, shown per-case as `trunc` with a `no answer` count. Thinking
  models routinely spend the whole output budget before answering; on the real harness that is a
  wasted turn, so it is a failure, not an excused absence. Raise `--num-predict` (or the case's own
  `num_predict`) if you want to measure quality rather than verbosity.

Adding a case: write the JSON, then add a reference answer to
`tests/test_run_model_evals.py::test_reference_answers_score_high` — if the learning's own wording
cannot clear the rubric, the rubric is wrong.
