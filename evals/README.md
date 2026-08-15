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
`batons/` as documented in `docs/learnings/README.md`).

## Cases

| case | category | from | asserts |
|---|---|---|---|
| route1-flee-loop | battle | route1-navigation-flee-loop | reaches Viridian Forest (51) from `route1.state` in ≤2000 turns with lead HP ≥5 — fails on main until the flee-loop fix lands |
| forest-crossing-healthy | navigation · battle | viridian-forest-turn-385-blackout | from the 17-HP forest entrance, `very_cautious` reaches Pewter (2) in ≤3000 turns with lead HP ≥5 |
| forest-crossing-1hp | navigation · battle | viridian-forest-1hp-entry-unresolved | documents the known failure: from the 1-HP entrance the default genome does **not** reach Pewter in 3000 turns (expected_fail) |
| pewter-to-gym | navigation | brock-approach-deadend / pewter-corrupted-transition-save | from the forest→Pewter baton, reach Pewter Gym (54) in ≤4000 turns (expected_fail until the routes.json waypoint fix) |
