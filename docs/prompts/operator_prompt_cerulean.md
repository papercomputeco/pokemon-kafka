# Mission: the road to Cascade — Route 4 into Cerulean, then Misty

You are an autonomous operator on this repo. Your goal: take a relay lane from Route 4's east
side into Cerulean City and win **Badge 2**. Success is a lane whose fitness shows `badges: 2`;
the deliverable is `batons/cerulean_to_badge2.state` (the intermediate
`batons/route4_to_cerulean.state` is written on the way). Print `date` at the start and before
any summary; your clock estimates are not reliable without it.

This is a progress run, not a benchmark row: use everything — ROM truth, tips, self-healing,
the learnings pile. The row is labelled assisted either way.

## The seed

`demo-runs/states/mtmoon_seeds/route4_east_hp25.state` — the Mt. Moon clear's own baton: Route 4
(map 15) east side at (27,3), Badge 1, and the lead at **25 HP**. Read `MANIFEST.md` beside it.
25 HP will not survive careless trainer contact: the Pokemon Center in Cerulean is the first
stop worth planning before anything ambitious.

## Ground truth — look topology up, never probe for it

`references/rom_truth.json` via `scripts/rom_truth.py` (`route 15 3`). Route 4's **east edge**
hands the lane to Cerulean City (map 3) — an edge hop fires no warp, the lane must walk off the
side. The gym is inside the city; Nugget Bridge and Route 24 are north of it — a detour, not
the goal. **Never cat the file or print grid rows into your reasoning.** When the reference and
the engine disagree, the engine is authoritative: measure live, then adjust the plan, not the
reference.

## The segments

Two chained segments (`scripts/relay.py`): `route4_to_cerulean` stops on map 3;
`cerulean_to_badge2` stops on `badges: 2`. The relay seeds the second from the first's winner
automatically. Prescribed shape (one relay run at a time on this box, always):

    uv run python scripts/rom_truth.py seed-worldmap 15 3 65 --out cerulean.worldmap
    uv run python scripts/relay.py rom/pokemon_red.gb --segments route4_to_cerulean cerulean_to_badge2 \
      --seed-state demo-runs/states/mtmoon_seeds/route4_east_hp25.state \
      --seed-worldmap cerulean.worldmap --sideloop-every 300

Self-healing (`--sideloop-every 300`) stays on for every relay. If a lane wedges, read WHERE it
wedged from its own fitness and agent.log before relaunching — a body is not a wall, and a
frozen dialogue wants an A-press, not a re-race.

## The fight at the end

The gym leader's team is water-typed and your lead is a fire type at a level the seed's
MANIFEST states — reason about the type chart, levels, and HP from what you observe in the
battle events, not from memory. If the lead cannot carry the fight, what the lane caught on the
way (Route 4, the bridge) is part of the answer.

## Budget and honesty

Your budget per attempt is in the supervisor briefing. Write learnings with real log lines;
"N/A — not attempted" where true. Every slot teaches the road to Cerulean, win or lose —
leave the worktree minable.
