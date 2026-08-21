# Mission: clear Mt. Moon

You are an autonomous operator on this repo. Your goal: take a relay lane **through Mt. Moon and
out the far side** — from the 1F entrance to Route 4's eastern stretch, toward Cerulean. Success
is a lane whose `final_map_id` is **3 (Cerulean City)**, or **15 (Route 4) at x ≥ 30** having
visited an underground floor (60 or 61) on the way. Print `date` at the start and before any
summary; your clock estimates are not reliable without it.

## The seed

`demo-runs/states/mtmoon_seeds/mtmoon1f_entrance_hp42.state` — Mt. Moon 1F (map 59) at (14,35),
Badge 1, Charmeleon L17 at 42/50 HP. This is the baton from the run that first reached the
mountain. Beside it: `mtmoon1f_entrance_hp42.worldmap` (the accumulated grids — seed it) and
`.genome.json`. Read `MANIFEST.md`.

## Ground truth — look topology up, never probe for it

`references/rom_truth.json` holds every map's warps, edge connections, and collision grids;
query it with `scripts/rom_truth.py` (`route A B`, `seed-worldmap`, or targeted `python -c`
one-liners). **Never cat the file or print grid rows into your reasoning** — seed the pilot
instead:

    uv run python scripts/rom_truth.py seed-worldmap 59 60 61 15 3 --out mtmoon.worldmap

Two facts to start from, both verified against the ROM: map 59's own warps are only the west
entrance mats plus three ladders down to 60 — the way out is **through the floors**; and
Route 4 (15) has a second cave door at (24,5) into map 60 (warp 7) — the far exit. Trainers,
item balls, and grass tiles for these maps are in the same file. Zubat and Paras live here;
your lead is 42/50 HP with no potions — reason about attrition before you commit lanes.

## The segment

`mtmoon_clear` does not exist in `scripts/agent.py` yet. Build it the way `badge_to_mtmoon`
was built (read that code first — it is the pattern that cleared the last leg: warp-table
driven, badge-gated, dispatching along a ROM-truth chain). When a lane satisfies the goal,
the relay must write `batons/mtmoon_clear.state` — that baton is this mission's deliverable.

Prescribed relay shape (one relay run at a time on this box, always):

    uv run python scripts/relay.py rom/pokemon_red.gb --segments mtmoon_clear \
      --seed-state demo-runs/states/mtmoon_seeds/mtmoon1f_entrance_hp42.state \
      --seed-worldmap mtmoon.worldmap --sideloop-every 300

Self-healing (`--sideloop-every 300`) stays on for every relay.

## Discipline

- Probe with a single lane before committing a relay; cite measured coordinates, not theories.
- Commit code + learnings as you go; an uncommitted diff is a lost diff. Tests green
  (`uv run pytest`) before any commit that touches `scripts/`.
- Write `docs/learnings/SPEEDRUN_SUMMARY.md` with harness/model, seed, every approach in order
  with its measured result, whether the goal was reached, total game turns, wall clock from
  `date`, and the exact commands you ran. Keep working after writing it if budget remains —
  ending early with an unsolved, named blocker is a failure of the run.
