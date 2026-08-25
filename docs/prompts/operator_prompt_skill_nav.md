# Skill mission: the navigation leg — Mt. Moon 1F down to B1F

You are an autonomous operator on this repo. Your goal: take a relay lane from the Mt. Moon 1F
entrance **down one floor**. Success is a lane whose fitness shows `final_map_id: 60` (B1F); the
deliverable is `batons/mtmoon_1f_to_b1f.state`. Print `date` at the start and before any summary.

This is the NAVIGATION skill leg of a matrix: one floor of cave, no fixed trainers on the way,
a correct collision reference available. What is measured is route-finding — turns to the goal,
stuck events, and whether your first relay lands.

## The seed

`demo-runs/states/mtmoon_seeds/mtmoon1f_entrance_hp42.state` — Mt. Moon 1F (map 59) at (14,35),
Badge 1, Charmeleon L19 at 42/55 HP. Beside it: a `.worldmap` and `.genome.json`; read
`MANIFEST.md`. Study the seed's exact tile against map 59's warp table before you launch
anything — where the lane STARTS is part of the puzzle.

## Ground truth — look topology up, never probe for it

`references/rom_truth.json` via `scripts/rom_truth.py` (`route 59 60`, `seed-worldmap`).
**Never cat the file or print grid rows into your reasoning.** Map 59's own warps are the west
entrance mats plus three ladders down to 60. The engine is authoritative when it disagrees with
any reference — a per-cell grid cannot express everything the engine enforces.

## The segment

`mtmoon_1f_to_b1f` (scripts/relay.py) stops on `--stop-on-map 60`. Prescribed shape:

    uv run python scripts/rom_truth.py seed-worldmap 59 60 --out mtmoon-nav.worldmap
    uv run python scripts/relay.py rom/pokemon_red.gb --segments mtmoon_1f_to_b1f \
      --seed-state demo-runs/states/mtmoon_seeds/mtmoon1f_entrance_hp42.state \
      --seed-worldmap mtmoon-nav.worldmap --sideloop-every 300
