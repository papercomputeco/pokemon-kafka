You are the operator for a Pokemon Red speedrun experiment. Work ONLY inside the current git worktree (your cwd); never cd to a sibling repo. Do not push, do not open PRs, do not run `paper` or `tapes` commands. Use `uv run ...` for all Python (see AGENTS.md).

## Mission (GitHub issue #70 of pcc-labs/pokemon-kafka)

Use the divide-and-conquer relay `scripts/relay.py` to complete the baton chain from Route 1 to the Mt. Moon entrance (map id 59):

    route1_to_forest -> forest_to_pewter -> pewter_to_badge -> badge_to_mtmoon

The ROM is at `rom/pokemon_red.gb` — ALWAYS pass it explicitly as the first positional arg (the script's default ROM filename is wrong). The seed state `demo-runs/states/route1.state` exists.

Reaching Mt. Moon is only half the job. Every obstacle you clear must be recorded as a durable learning file in `docs/learnings/<obstacle>.md` with exactly this shape:

    obstacle:      <name, e.g. viridian-forest-turn-385-blackout>
    category:      battle | navigation | puzzle
    symptom:       <reproducible signature>
    failed:        <variants/approaches tried and how each failed>
    winner:        <the variant or change that cleared it, with the genome diff>
    why it worked: <the causal explanation, not just the diff>
    generalizes:   <what to reach for when the next obstacle in this category appears>
    artifacts:     <baton paths, report.json, relevant logs>

Known obstacles: (1) Viridian Forest turn-~385 blackout wall (navigation+battle) — `notes.md` says a healthy L13 party with potions crosses in ~31 steps, so heal/flee earlier is the known lever; (2) Brock (battle); (3) Pewter -> Mt. Moon via Route 3 (navigation, untraveled).

## Suggested sequence

1. `uv run python scripts/relay.py rom/pokemon_red.gb --dry-run` sanity pass.
2. Segment 1 smoke: `uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest --max-turns-scale 0.5 --timeout 900`
3. Forest campaign: iterate `forest_to_pewter` (use `--seed-state <winning baton>` from the previous segment's `data/relay/<run>/batons/`) until a lane survives; write the learning entry.
4. Brock leg (`pewter_to_badge`); write the learning entry.
5. Route 3 leg to map 59 (`badge_to_mtmoon`); write the learning entry.
6. Full chain in one invocation if possible; record total turns.

Read `scripts/relay.py` first to learn its flags (`--segments`, `--seed-state`, `--timeout`, `--max-turns-scale`, `--parallel`, `--run-dir`) and how `report.json` / batons are laid out. Read `scripts/agent.py --help` if you need lane flags. Each relay call launches up to 6 headless emulators; run only one relay invocation at a time. A lane runs about 30 game turns per second. If a segment fails, inspect its `report.json` and lane `fitness.json` files, form a hypothesis, and change something concrete (a variant's genome in `scripts/relay.py`, seed state, timeout, turns scale) before retrying — do not just rerun the same command more than twice. You may edit `scripts/relay.py` variants or `scripts/agent.py` if you have a real diagnosis; keep `uv run pytest -q -x tests/test_relay.py` passing if you touch relay.py.

## Budget and stopping

Stop when either the Mt. Moon baton exists (`batons/badge_to_mtmoon.state` in a run dir) or you have spent about 2.5 hours of wall clock. Do not exceed that.

## Deliverables (mandatory, even on failure)

- `docs/learnings/*.md` entries as above (one per obstacle you attempted, even if unresolved — mark winner as "unresolved" then).
- `docs/learnings/SPEEDRUN_SUMMARY.md` with: harness/model you are, segments reached, per-segment winner lane + turns, total game turns, wall clock, what blocked you, and the exact commands you ran in order.
- `git add docs/learnings scripts` and `git commit -m "speedrun: <short summary>"` on the current branch (commit only source/docs; do not commit `data/`, `rom/`, `pokedex/`, or `.state` files).

Begin now.

## Context-safety rules (this harness has a 128k window and no prompt caching)
- Never read a whole file; use grep -n / sed -n ranges of at most 150 lines, or the read tool with offset/limit.
- Never cat agent.log or other lane logs; use grep, tail -n, or awk summaries.
- Web tools are disabled. The repo already contains the map geometry you need (scripts/world_map.py, references/routes.json, scripts/pathfinding.py, lane world.map files).
- Long-running commands: relay.py calls may take up to 30 minutes; run them in the foreground (a default timeout is applied automatically). Do not write emulator probe scripts that poke RAM addresses; drive PyBoy only through scripts/agent.py flags.
- Write each docs/learnings entry as soon as an obstacle is cleared, and commit as you go — do not save deliverables for the end.
