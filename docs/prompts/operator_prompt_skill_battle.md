# Skill mission: the battle leg — Brock, from the face-off tile

You are an autonomous operator on this repo. Your goal: take a relay lane from the pre-Brock
baton to **Badge 1**. Success is a lane whose fitness shows `badges: 1` and `brock_won: true`;
the deliverable is `batons/pewter_to_badge.state`. Print `date` at the start and before any
summary; your clock estimates are not reliable without it.

This is the BATTLE skill leg of a matrix — navigation is deliberately trivial here (the seed
stands at Brock's face-off row, full HP). What is measured is how you operate the fight:
`brock_turns`, the winner's `lead_hp` afterward, and whether your first relay lands or you burn
attempts. Move quality, HP thresholds, and the battle genome knobs are the whole game.

## The seed

`demo-runs/states/pre-brock.state` — Pewter Gym (map 54) at (5,1), badges 0, Charmeleon L16 at
48/48. Captured by `--save-state-on-trainer` on the way to the badge; the fight starts within a
few turns of pressing forward.

## The segment

`pewter_to_badge` (scripts/relay.py) stops on `--stop-on-badge 1`. Prescribed shape (one relay
run at a time on this box, always):

    uv run python scripts/relay.py rom/pokemon_red.gb --segments pewter_to_badge \
      --seed-state demo-runs/states/pre-brock.state --sideloop-every 300

Battle behaviour is the genome (EVOLVE_PARAMS): `hp_run_threshold`, `hp_heal_threshold`,
`status_move_score`, `unknown_move_score`. Ember is resisted by rock — reason about what wins
this fight before you spend lanes on it. Read the fitness JSON, not the log tail, to judge a lane.
