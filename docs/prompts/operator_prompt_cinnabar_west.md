# Mission: surf WEST off Route 20 to Cinnabar. Seafoam was never the path.

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary. Screenshot anything that refuses to move you, and look at it before deciding what
it is.

## The finding that reframes this arc (extracted from the cartridge, not recalled)

`references/rom_truth.json`, map 31 (Route 20): `connections = {'west': 8, 'east': 30}`.

**Route 20 connects west, directly, to map 8 — Cinnabar.** Its only warp is 192, the Seafoam
cave. The cave is a *side entrance off this route*, not a step on the way. Every Seafoam leg,
every boulder, every hunt for HM04 STRENGTH was an optional detour. Cinnabar needs **Surf and
nothing else.** Map 8 has never been reached once in this project's telemetry.

## Your baton already surfs

`data/local_runs/roster-bench/m31_manual.state` — map 31 at **(44,12)**, six badges, HM03 in the
bag, Gyarados knows SURF (`knows_move("SURF")`). Do not go looking for STRENGTH; you do not
need it. Do not enter warp 192.

## The one thing to test

Map 31 is 100x18. The static tile model says:

- the water region that touches the west column (x=0, rows 14-16 are water) is ~694 cells
- **your position (44,12) sits in a separate 49-cell pocket, x=44..54, that does not reach x=0**

That is a *heuristic on tile ids*, so treat it as a hypothesis, not a wall. Test it live:

1. Surf/walk WEST along map 31 and read what actually stops you. The pocket boundary is around
   x=54. When a step is refused, **screenshot it and read the sentence on screen** before
   concluding anything.
2. If the pocket is real, the way out is most likely a row change: the big region reaches x=0
   on **rows 14-16**, you are on row 12. Try working south first, then west.
3. `road.shore_stand` + `surf_cross` now arm from a cell that touches edge-reaching water — use
   the engine (`supervisor.py run --goal 8`), do not hand-drive a straight line west.

## Discipline

- `--no-consult` first: this may be pure topology, and that tells an engine bug from a real wall.
- Talk to every body you pass; `Rig.engage_bodies(("trainer","npc"))`. A `pic == 63` "npc" is a
  Strength boulder, not a person — ignore those, you are not doing boulders.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Commit as you go. Name any one-off driver `scripts/probe_<name>.py`.

## Definition of done

Banked state on **map 8**. Then talk to every body in Cinnabar and enter every building, and
report what the town says about the gym and Blaine. If you cannot leave map 31, write down the
exact cell and the exact refusal sentence — that is the useful artifact, not a guess.
