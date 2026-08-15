# Learnings — durable obstacle records

Each file records one obstacle in the shape issue #70 asks for (`obstacle / category / symptom /
failed / winner / why it worked / generalizes / artifacts`). Before burning compute on a new
obstacle, query this directory by **category** first.

| obstacle | category | status | produced by | one-line lesson |
|---|---|---|---|---|
| [route1-navigation-flee-loop](route1-navigation-flee-loop.md) | navigation · battle | cleared | pi + kimi-k2.6 (2026-08-15) | the wild-battle stall guard returned `run` forever; cap recovery attempts and fall back to the best move |
| [viridian-forest-turn-385-blackout](viridian-forest-turn-385-blackout.md) | navigation · battle | cleared | pi + kimi-k2.6 (2026-08-15) | in high-encounter mazes survival beats leveling: flee/heal at 50% HP; a healthy entry (17 HP) crosses in ~2.3k turns |
| [viridian-forest-1hp-entry-unresolved](viridian-forest-1hp-entry-unresolved.md) | navigation · battle | unresolved | pi + claude-haiku-4.5 (2026-08-15) | entering the forest at 1 HP cannot be rescued by genome spreads alone — the baton's health is the lever, not the forest genome |

## The 1-HP forest lesson (why two entries)

Two operators hit the same wall from opposite sides. Kimi fixed the flee-loop bug upstream, so its
Route 1 baton entered the forest at **17 HP** and `very_cautious` (`hp_run_threshold=0.5`,
`hp_heal_threshold=0.5`) walked out to Pewter in 2270 turns with 13 HP. Haiku sidestepped the same
bug by swapping the seed state, arrived at **1 HP**, and no forest genome could save it. Same map,
same code paths — the only difference was the health of the party that walked in.

Generalization for the relay: a segment's baton is only as good as its `lead_hp`. The relay already
picks the healthiest winner; the operator should treat a low-HP baton as a failure of the *previous*
segment, not a tuning problem for the next one.

Artifacts (local, gitignored like every savestate): `demo-runs/states/forest-entry-healthy-17hp.state`,
`demo-runs/states/forest-entry-1hp.state`, `demo-runs/states/forest-very-cautious.genome.json`.
Operator traces are in tapes; game events in Kafka `agent.game.events`.

## Per-run originals (2026-08-15, five models on the pi harness)

Unedited entries from each operator run live under `by-run/2026-08-15-<model>/`; the table above is
the curated set. Highlights worth reading in the originals:

| model | notable entries |
|---|---|
| [sonnet-5](by-run/2026-08-15-sonnet-5/) | `route2-battle-menu-desync-blackout` (a second, compatible root cause for the Route 1 flee loop), `pewter-waypoint-index-reset-loop` (real nav bug: waypoint index starts at 0 when loading mid-map), `brock-approach-deadend-unresolved` (the (16,11) Gym waypoint is a wall) |
| [kimi-k2.6](by-run/2026-08-15-kimi-k2.6/) | `pewter-corrupted-transition-save` (`--stop-on-map` saves on the first frame after `wCurMap` flips) |
| [haiku-4.5](by-run/2026-08-15-haiku-4.5/) · [haiku-4.5-claude-code](by-run/2026-08-15-haiku-4.5-claude-code/) | tidy but partly wrong root causes — useful as a contrast; the Claude Code run's `NEXT_STEPS.md` hypothesised the transition-save bug before Kimi confirmed it |
| [qwen3.5-35b](by-run/2026-08-15-qwen3.5-35b/) | free-form (its context was silently truncated by Ollama's `num_ctx`) |
| [gemma4-8b](by-run/2026-08-15-gemma4-8b/) | follows the format; files the Route 1 flee loop under the forest obstacle's name |

Regression evals derived from these live in [`evals/`](../../evals/README.md); dated benchmark
tables in [`benchmarks/`](../../benchmarks/README.md).
