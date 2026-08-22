# Skill mission: the puzzle leg — clear Mt. Moon

You are an autonomous operator on this repo. Your goal: take a relay lane **through Mt. Moon and
out the far side**. Success is a lane whose fitness shows `final_map_id: 15` (Route 4) at
**x ≥ 22** — the dungeon's east exit lands at (24,5); the west side of 15 is where the lane came
in and does not count. The deliverable is `batons/mtmoon_clear.state`. Print `date` at the start
and before any summary.

This is the PUZZLE skill leg of a matrix: the floors hold anomalies that no reference fully
captures — steps the engine refuses although the grid says open, positions that read as progress
while going nowhere, doorways whose behaviour depends on state you have to observe. What is
measured is observation and reasoning: diagnosing what the live engine is actually doing before
spending lanes on a wrong theory. **This segment has never been cleared by anyone.**

## The seed

`demo-runs/states/mtmoon_seeds/mtmoon1f_entrance_hp42.state` — Mt. Moon 1F (map 59) at (14,35),
Badge 1, Charmeleon L19 at 42/55 HP, no potions. Zubat and Paras live here; reason about
attrition before you commit lanes. Read `MANIFEST.md`.

## Ground truth — look topology up, never probe for it

`references/rom_truth.json` via `scripts/rom_truth.py` (`route 59 15`, `seed-worldmap 59 60 61 15`).
**Never cat the file or print grid rows into your reasoning.** Two verified facts: map 59's own
warps are the west entrance mats plus three ladders down to 60 — the way out is through the
floors; and Route 4 (15) has a second cave door at (24,5) into map 60 (warp 7) — the far exit.
When the reference and the engine disagree, the engine is authoritative: measure live, then
adjust the plan, not the reference.

## The segment

`mtmoon_clear` (scripts/relay.py) stops on `--stop-on-map 15 --stop-min-x 22`. Prescribed shape
(one relay run at a time on this box, always):

    uv run python scripts/rom_truth.py seed-worldmap 59 60 61 15 --out mtmoon.worldmap
    uv run python scripts/relay.py rom/pokemon_red.gb --segments mtmoon_clear \
      --seed-state demo-runs/states/mtmoon_seeds/mtmoon1f_entrance_hp42.state \
      --seed-worldmap mtmoon.worldmap --sideloop-every 300

Self-healing (`--sideloop-every 300`) stays on for every relay. If a lane wedges, read WHERE and
WHY from its events before relaunching — the fingerprint of the wedge is the puzzle.
