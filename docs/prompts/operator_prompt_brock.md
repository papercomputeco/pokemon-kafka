You are the operator for a Pokemon Red speedrun experiment. Work ONLY inside the current git worktree (your cwd); never cd to a sibling repo. Do not push, do not open PRs, do not run `paper` or `tapes` commands. Use `uv run ...` for all Python (see AGENTS.md).

## Mission — win the Pewter Gym battle

One goal, and it is the wall four previous runs failed on: **beat Brock and take Badge 1.**

Success is measured, not asserted: a `pewter_to_badge` segment whose winning lane reports
`badges >= 1` and `brock_won: true` in its `fitness.json`, with the baton state to prove it.
Anything short of that is a failure row — write it up honestly.

The ROM is at `rom/pokemon_red.gb` — ALWAYS pass it explicitly as the first positional arg (the
script's default ROM filename is wrong).

## You do not have to replay the first two segments

Seed states from earlier runs are staged in `demo-runs/states/brock_seeds/` with a
`MANIFEST.md` describing each one's party health and provenance. Two kinds:

- `pewter_arrival_*.state` — a lane standing in Pewter City (map 2), forest already cleared.
  Feed one to `relay.py --segments pewter_to_badge --seed-state <path>`.
- `pewter_gym_pre_jr_trainer_hp8.state` — inside Pewter Gym (map 54) at 8 HP, parked on the Gym's
  Jr. Trainer, NOT on Brock. Evidence of where earlier runs stalled, not a shortcut.

Pick deliberately (the healthiest arrival is not always the best-levelled one) and say in your
write-up which seed you used and why. You may also run the earlier segments yourself if you have a
reason to — e.g. you conclude no existing seed can win and you need a stronger party — but spend
the budget on the wall, not on ground already covered.

## What is already known about this wall (from run r8, 2026-08-16)

The blocker was named as a triad. Treat this as evidence, not as instructions — verify before you
build on it:

1. **No map-54 interior waypoints** in `references/routes.json`. r7 reached the Gym (map 54) and
   then burned 12000 turns at (4,5) with 840 stuck events — it gets inside and cannot navigate to
   Brock. Emulator-verified interior waypoints are the cheapest named lever.
2. **A single low-HP lead.** Every arrival baton is `party_size: 1`, often self-poisoned and under
   15 HP. Brock's Onix is not losing to that.
3. **No heal path.** `scripts/healer.py` is a parameter race, not an in-game heal, and the relay
   lanes run `--no-self-heal`. Pewter's Pokemon Center is on the map the lane is standing on and
   nothing ever walks into it.
4. `BATTLE_SPREAD` in `scripts/relay.py` varies wild-flee/heal thresholds only — **never
   navigation**. All six lanes of `pewter_to_badge` were effectively byte-identical runs.

A standing theory that is already **refuted** — do not re-derive it: baton corruption does not
explain the Brock failure (see `docs/learnings/by-run/`, r8's `baton-integrity-refuted.md`;
pre- and post-fix batons are byte-identical and the arrival coordinate is inside the live Pewter
map header).

## What you may change

Anything in the repo that gets the badge, with a real diagnosis behind it:
`references/routes.json` waypoints, the `BATTLE_SPREAD` / `NAV_SPREAD` variants and the
`pewter_to_badge` Segment in `scripts/relay.py`, decision logic in `scripts/agent.py`, a heal path.
Read `scripts/relay.py` first for its flags (`--segments`, `--seed-state`, `--timeout`,
`--max-turns-scale`, `--parallel`, `--run-dir`) and the report/baton layout; `uv run python
scripts/agent.py --help` for lane flags. Keep `uv run pytest -q -x tests/test_relay.py` passing if
you touch relay.py, and add tests for behaviour you change in agent.py.

Each relay call launches up to 6 headless emulators plus their self-heal subloops, so **only one
relay invocation may run at a time** — this is enforced, not advisory: a second concurrent relay
prints `[relay] REFUSED` and exits 2. If you see that, wait for the running one rather than working
around it. A lane runs about 30 game turns per second when the box is not oversubscribed; if lanes
start returning unchanged positions with high `stuck_count`, suspect load before you suspect
navigation. If a segment fails, read its `report.json` and the lane
`fitness.json` files, form a hypothesis, and change something concrete before retrying — do not
rerun the same command more than twice.

## Self-healing is ON and must stay on

This repo's whole point is that the agent heals itself while it plays, so every relay call you make
must carry `--sideloop-every 300`:

    uv run python scripts/relay.py rom/pokemon_red.gb --segments pewter_to_badge \
        --seed-state demo-runs/states/brock_seeds/<seed>.state --sideloop-every 300

That flag gives each lane an AlphaEvolve subloop: every 300 turns the lane snapshots the live game,
races decision variants from that snapshot in the background, and hot-applies the winning genome
between turns without stopping. Each lane's heal is private to it (own `genome.md`, own `advice/`
inbox), so the lanes still differ only by their variant. Confirm it is actually running rather than
assuming it — a lane log should show, in order:

    SIDELOOP | spawned at turn 300
    SIDELOOP | finished rc=0
    ADVICE   | Advice applied (sideloop): ...

If you never see `Advice applied`, healing is not happening and that is itself a finding worth
reporting. Do not turn the flag off to make a run faster.

The in-run wedge heal (a lane that crosses a terminal stuck streak races from its own wedged save
state) is on by default and needs no flag. The end-of-run healer (`scripts/healer.py check`) is
deliberately NOT run per lane — it writes the shared `notes.md` — but you may run it yourself
against a finished segment's winning `fitness.json` if you want a genome promoted between segments.

## Budget

**There is no turn budget, no token budget and no cost budget.** Use as many relay rounds, lanes
and game turns as the diagnosis justifies; raise `--max-turns` past the segment defaults if turns
are what you need.

**Wall clock is the only limit: 2 hours.** The harness kills the run at that point regardless, so
plan backwards from it and keep the last ~15 minutes for deliverables. Do NOT stop early because
you feel far along — if the badge is not won and time remains, keep working the problem. Ending a
run early with an unsolved named blocker is a failure of the run, not a display of restraint.

## Deliverables (mandatory, even on failure — write them AS YOU GO, not at the end)

- `docs/learnings/pewter-gym-brock.md` (and one file per distinct sub-obstacle you attempt, e.g.
  gym interior navigation, party health) in exactly this shape:

    obstacle:      <name>
    category:      battle | navigation | puzzle
    symptom:       <reproducible signature>
    failed:        <variants/approaches tried and how each failed>
    winner:        <the variant or change that cleared it, with the genome/code diff — or "unresolved">
    why it worked: <the causal explanation, not just the diff>
    generalizes:   <what to reach for when the next obstacle in this category appears>
    artifacts:     <baton paths, report.json, relevant logs>

- `docs/learnings/self-healing-observed.md`: what the self-healing loop actually did this run —
  how many sideloop races ran, how many winners were applied, which knobs they moved, and whether
  any of it changed the outcome. Quote the log lines. "It was on and did nothing measurable" is a
  perfectly good finding; an unsupported claim that it helped is not.
- `docs/learnings/SPEEDRUN_SUMMARY.md`: harness/model you are, seed state chosen and why, every
  approach tried in order with its measured result, whether `brock_won` is true, total game turns,
  wall clock, what blocked you, and the exact commands you ran in order.
- `git add docs/learnings scripts references && git commit -m "brock: <short summary>"` on the
  current branch. Commit source/docs only — never `data/`, `rom/`, `pokedex/`, or `.state` files.

Every number in your summary must come from a file you can point at. Do not report a badge you did
not measure.

Begin now.

## Context-safety rules
- Never read a whole large file; use grep -n / sed -n ranges of at most 150 lines, or the read tool
  with offset/limit.
- Never cat agent.log or other lane logs; use grep, tail -n, or awk summaries.
- Web tools are disabled. The repo already contains the map geometry you need
  (`scripts/world_map.py`, `references/routes.json`, `scripts/pathfinding.py`, lane `world.map`
  files, and the winning lanes' recorded frames).
- Long-running commands: relay.py calls may take up to 30 minutes; run them in the foreground.
- Do not write emulator probe scripts that poke RAM addresses directly; drive PyBoy only through
  `scripts/agent.py` flags.
