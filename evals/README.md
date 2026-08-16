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
| route1-flee-loop | battle | route1-navigation-flee-loop | reaches Viridian Forest (51) from `route1.state` in ≤2000 turns with lead HP ≥5. In a clean worktree the lane never enters the flee loop (916 turns, 9/9 battles, both before and after the 08-16 wedge watchdog + stall-run cap) but arrives at 2 HP, so it still FAILs on the health half. With the 08-16 battle-menu sync every fight turn lands (25/25, was 19/36) and it still arrives at 1-5 HP (FAIL 934 / hp 1; timing-sensitive): what is left is the fight-first run policy at hp_run_threshold=0.2, not menu timing |
| forest-crossing-healthy | navigation · battle | viridian-forest-turn-385-blackout | from the 17-HP forest entrance, `very_cautious` reaches Pewter (2) in ≤3000 turns with lead HP ≥5. Before 08-16 this row was a `PYTHONHASHSEED` coin flip (PASS 2270 / hp 13 or FAIL 3000 stuck in the Forest): `_pick_move` broke physical/special damage ties by set order. Ties now fall back to the best-scored move, and the lane is reproducible — FAIL 1251 turns / Pewter / hp 2 (reaches the city, misses min_lead_hp) before the 08-16 battle-menu sync; with it the battles are won cleanly (60/60, L16, full HP) but the lane thrashes at the (25,21) forest pocket — FAIL 3000 / 51 / hp 42, the navigation half |
| forest-crossing-1hp | navigation · battle | viridian-forest-1hp-entry-unresolved | documents the known failure: from the 1-HP entrance the default genome does **not** reach Pewter in 3000 turns (expected_fail) |
| pewter-to-gym | navigation | brock-approach-deadend / pewter-corrupted-transition-save | from the forest→Pewter baton, reach Pewter Gym (54) in ≤4000 turns. Passes since the Pewter routes.json fix (the old first waypoint (13,25) was the Pokémon Center door and the old "gym" waypoint (16,11) open ground; the door is (16,17), reached from the west via x=19 → y=13 → x=10 → y=18) plus the WorldMap planner for route waypoints — 44 turns |
| low-hp-wild-battle | battle | route1-navigation-flee-loop | from *inside* the Route 2 Weedle battle at 4/23 HP (the flee-loop state itself), reach the Forest (51) alive in ≤600 turns. `main` before 08-16: 600 turns, 3 encounters then frozen in the loop (3 low-HP runs, 10 fight turns that land nothing, run forever — the agent is stuck inside the battle's PKMN submenu). With the 08-16 wedge watchdog (B x8 recovery): PASS, 356 turns, 4/4 battles, 1 recovery; the stall-run cap alone does not break it. With the 08-16 battle-menu sync (nothing is pressed blind, so the PKMN submenu is never entered): PASS, 194 turns, 3/3, 0 recoveries. The `battles (won/enc)` column and `battle_wedge_recoveries` in fitness tell the cases apart |
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

## Advisors (`scripts/advisor.py`) — how new cases get in

Model-eval cases can also be *dreamed* from captured operator sessions instead of written by hand,
after the shape of `pcc-labs/inception` (session → dream → gate → heal):

```
uv run python scripts/advisor.py investigate ~/.pi/agent/sessions/<slug>/<id>.jsonl --worktree <run worktree>
uv run python scripts/advisor.py gate data/advisor/<date>/<id>.proposal.json --models laguna-xs-128k,gpt-oss-20b-128k
uv run python scripts/advisor.py promote data/advisor/<date>/<id>.proposal.json
uv run python scripts/advisor.py oracle "lanes stall on map 54 pressing up, stuck streak 2800"
```

* **Investigator** (write path; an investigator-class model, default `qwen38-27b-128k`) reads ONE session plus
  the run worktree's ground truth (relay reports, learnings written, code diff) and asks the Oracle what is
  already known, then dreams a proposal: tip, learning draft, a model-eval case (prompt + rubric), optional
  agent-eval hint. It repairs its own rubric until the rubric recognises the proposal's reference answer.
* **Gate**: the case is run control (no tip) vs treatment (tip in the system prompt) on fresh models; the tip is
  the only variable. PASS = mean lift ≥ 0.2 **and** at least one model reaches ≥ 0.6 with the tip. Results
  append to `evals/results/advisor-<date>.md`, FAIL rows included — a gate that can say no is what makes its
  yes worth acting on. First real run (2026-08-16, Laguna r2 session): the Investigator skipped the Gym bug
  the Oracle already knew and caught the *process* failure ("declared fixed after tests+lint; relay still
  None"); the gate rejected two self-inconsistent rubrics before passing the repaired one — Laguna 0.00 → 1.00.
* **Promote** writes `evals/model-cases/<name>.json`, `docs/learnings/<name>.md` (marked `source: advisor`)
  and appends the tip to `docs/prompts/tips.md`, which `scripts/local_relay_run.sh` appends to the mission.
  Only gated proposals can be promoted (`--force` to override, don't).
* **Oracle** (read path) is a knowledge bearer over learnings, eval cases/results, benchmarks and past tapes
  sessions; it cites (`path:line`, session id) or says `NO PRECEDENT`. The operator can call it at run time
  through the `consult` tool in `scripts/pi-ext/guardrails.ts`.
