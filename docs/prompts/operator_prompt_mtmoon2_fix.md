# Mission: fix the cavern map, then clear Mt. Moon

Two jobs, strictly in order. Print `date` at the start and before any summary.

## Job 1 — fix the collision rule (your own finding)

A prior session in this worktree audited `references/rom_truth.json` against the live engine and
measured **842 of 1,440 cells wrong on Mt. Moon 1F (map 59)**: `scripts/rom_truth.py parse_map`'s
2×2-quad corner rule is wrong for the cavern tileset (the overworld/gym tilesets it was
validated on agree by coincidence). Your committed far-door probe (`git log`, commit c6fc43b —
text-box aware stepping, learned live-walls) is the measuring instrument.

Deliverables, all committed:
1. The corrected rule in `scripts/rom_truth.py` — derive it from measurement, not theory: probe
   disputed cells with the live engine (the probe tool), and cross-check against
   `demo-runs/states/mtmoon_seeds/mtmoon1f_entrance_hp42.worldmap` — real cells learned by the
   lanes that first reached map 59. The fix must keep the overworld/gym maps at 100 % agreement
   (the existing validation) while making the cavern grids match the engine.
2. A cavern-tileset case in `tests/test_rom_truth.py`; full suite green (`uv run pytest --cov`
   — CI requires 100 %).
3. Re-extract: `uv run python scripts/rom_truth.py extract` → commit the corrected
   `references/rom_truth.json`.
4. A learnings file naming the true rule with the measured coordinates that prove it.

Until Job 1 is done, treat `rom_truth.json`'s cave grids as untrustworthy — do **not** seed
cave maps from it, and ignore any earlier briefing that says otherwise. The live engine is
authoritative.

## Job 2 — clear the mountain

Only after the map is fixed. Goal, seed, and discipline are unchanged from
`docs/prompts/operator_prompt_mtmoon2.md`: from `mtmoon1f_entrance_hp42.state` (map 59 at
(14,35)), get a lane to **map 3, or map 15 at x ≥ 30 having visited 60 or 61**, via a
`mtmoon_clear` segment that writes `batons/mtmoon_clear.state`. Facts that survive the audit:
map 59's only exits are the west mats and three ladders down to 60; Route 4 (15) has a second
cave door at (24,5) into map 60 (warp 7) — the far exit. A draft `mtmoon_clear` segment exists
as an **uncommitted diff** in `../pokemon-kafka-speedrun-pi-exp-laguna-xs-mtmoon2/scripts/agent.py`
— salvage it as a starting point if it survives your inspection, but its author never verified it.

One relay at a time; `--sideloop-every 300` on; seed the (fixed) worldmap; probe before
committing lanes; commit as you go; keep working after any summary while budget remains.

## Amendment (2026-08-21) — the unreachable-proof's measured flaw

A prior session in this worktree completed Job 1 (the ≥3-of-4 rule — it stands, keep it) and
then ruled the goal unreachable from the seed. That ruling rests on a connectivity model where
**warp cells are walls**: under the corrected grid, map 59's three ladder cells (5,5), (17,11),
(25,15) all read WALL — yet the engine enters warp tiles regardless of collision (your own lanes
stood on the (14,35) entrance mat, which also hosts a warp; every Gen 1 player has descended
these exact ladders). A sub-tile majority does not close a cell that hosts a warp-table entry.

So: skip Job 1 (done — do not redo it). Amend the model — any cell carrying a warp entry is
enterable, in `seed_worldmap` and in any connectivity analysis, with a test. Verify live first:
one probe stepping onto (5,5) from an adjacent walkable cell; the warp to 60 should fire. Then
rebuild the component analysis and finish Job 2 — the route should be computable before you run it.
