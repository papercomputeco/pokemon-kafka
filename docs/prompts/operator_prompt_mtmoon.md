You are the operator for a Pokemon Red speedrun experiment. Work ONLY inside the current git worktree (your cwd); never cd to a sibling repo. Do not push, do not open PRs, do not run `paper` or `tapes` commands. Use `uv run ...` for all Python (see AGENTS.md).

## Mission — reach the Mt. Moon entrance

Badge 1 is done (PR #93). One goal now: **from the Pewter Gym with the badge in hand, reach Mt. Moon 1F (map id 59) via Route 3.**

Success is measured, not asserted: a `badge_to_mtmoon` segment whose winning lane reports `final_map_id: 59` in its `fitness.json`, with the baton `batons/badge_to_mtmoon.state` to prove it. Anything short of that is a failure row — write it up honestly.

The ROM is at `rom/pokemon_red.gb` — ALWAYS pass it explicitly as the first positional arg (the script's default ROM filename is wrong).

## The seed

`demo-runs/states/mtmoon_seeds/badge1_gym_hp6.state` — standing on Brock's tile in Pewter Gym (map 54) with Badge 1, one Charmeleon L16 at 6/48 HP. Read `MANIFEST.md` beside it. Feed it to:

    uv run python scripts/relay.py rom/pokemon_red.gb --segments badge_to_mtmoon \
        --seed-state demo-runs/states/mtmoon_seeds/badge1_gym_hp6.state --sideloop-every 300

You may also replay earlier segments if you have a reason to (a stronger party, say) — but the wall is ahead of you, not behind.

## This ground is uncharted — that is the point

Nothing in the repo knows Route 3. `references/routes.json` has waypoints for maps 0, 1, 2, 12, 13, 51 and 54 — not Route 3 (map 14) and not Mt. Moon. No previous run has left Pewter eastward. The known geometry you have: `scripts/world_map.py`, `scripts/pathfinding.py`, `references/routes.json` (as a *format* to extend), and each lane's `world.map` as it explores. The agent's own overworld reads (`--stop-on-map`, lane `world.map`, `fitness.json` positions) are your emulator-verified coordinates; use them the way the Brock fix used single-lane probes to find (5,1) — one hypothesis per probe, not six lanes hoping.

Things to reason about before the first relay call: (a) 6/48 HP and the heal path is gated on *not* having the badge; (b) Pewter's east exit and Route 3's trainers; (c) `badge_to_mtmoon` uses `NAV_SPREAD`, so lanes actually differ this time. If a segment fails, read its `report.json` and lane `fitness.json`, form a hypothesis, and change something concrete — `routes.json` waypoints, the `badge_to_mtmoon` Segment or `NAV_SPREAD` in `scripts/relay.py`, decision logic in `scripts/agent.py`. Do not rerun the same command more than twice. Keep `uv run pytest -q -x tests/test_relay.py` passing if you touch relay.py; add tests for behaviour you change in agent.py.

## Self-healing is ON and must stay on

Every relay call must carry `--sideloop-every 300`. Each lane then races decision variants from its own live snapshot every 300 turns and hot-applies the winner (private per lane: own `genome.md`, own `advice/`). Confirm it is running — a lane log shows `SIDELOOP | spawned`, `SIDELOOP | finished rc=0`, `ADVICE | Advice applied (sideloop): ...`. If you never see `Advice applied`, that is a finding to report. Do not turn it off to go faster.

Known from the Brock run: the subloop races `BATTLE_SPREAD` and can only move HP-threshold knobs; on a navigation wall it applied 239 patches that changed nothing. If you find yourself on a navigation wall, giving the subloop something navigational to search (see `sideloop.py`, `sideloop_segment`) is a legitimate fix.

## The box

Each relay launches up to 6 headless emulators plus subloops; **only one relay may run at a time — enforced**: a second prints `[relay] REFUSED` and exits 2. Wait for it. Emulators draw from a box-wide slot pool; a lane that cannot get a core says `SLOT | ...` in its log and either waits or (subloop lanes) skips. If lanes come back with unchanged positions and high `stuck_count`, check for `SLOT` lines and load before you believe it is a navigation wall.

## Budget

**No turn budget, no token budget, no cost budget.** Wall clock is the only limit: **2 hours**, hard-killed by the harness. Run `date` now and before you write the summary — you have no clock otherwise and models on this mission have consistently reported 2–2.4× the real elapsed time. Keep the last ~15 minutes for deliverables. **Do NOT stop early because you feel far along.** Three runs on the previous mission quit with 1h44m+ left and an unsolved blocker; each was graded as a failure of the run. If map 59 is not reached and time remains, keep working the problem.

## Deliverables (mandatory, even on failure — write them AS YOU GO)

- `docs/learnings/route3-to-mtmoon.md`, plus one file per distinct sub-obstacle, in exactly this shape:

    obstacle:      <name>
    category:      battle | navigation | puzzle
    symptom:       <reproducible signature>
    failed:        <variants/approaches tried and how each failed>
    winner:        <the variant or change that cleared it, with the genome/code diff — or "unresolved">
    why it worked: <the causal explanation, not just the diff>
    generalizes:   <what to reach for when the next obstacle in this category appears>
    artifacts:     <baton paths, report.json, relevant logs>

- `docs/learnings/self-healing-observed.md`: what the self-healing loop actually did — races run, winners applied, which knobs moved, whether any of it changed the outcome. **Quote real log lines** (`grep -h "Advice applied" data/relay/*/*/*/agent.log | sort | uniq -c`). "It ran and did nothing measurable" is a fine finding; a quoted line that is not in a log is not.
- `docs/learnings/SPEEDRUN_SUMMARY.md`: harness/model, seed, every approach in order with its measured result, whether map 59 was reached, total game turns, wall clock from `date`, what blocked you, the exact commands you ran.
- `git add docs/learnings scripts references tests && git commit -m "mtmoon: <short summary>"` on the current branch, as you go. Never commit `data/`, `rom/`, `pokedex/`, or `.state` files.

Every number in your summary must come from a file you can point at.

Begin now.

## Context-safety rules
- Never read a whole large file; use grep -n / sed -n ranges of at most 150 lines, or the read tool with offset/limit.
- Never cat agent.log or other lane logs; use grep, tail -n, or awk summaries.
- Web tools are disabled.
- Long-running commands: relay.py calls may take up to 30 minutes; run them in the foreground.
- Do not write emulator probe scripts that poke RAM addresses directly; drive PyBoy only through `scripts/agent.py` flags.
