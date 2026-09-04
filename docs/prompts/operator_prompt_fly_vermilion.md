# Mission: Fly is near Vermilion — map 92 has never been entered

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary. **Kept short on purpose.**

## Why here

Fly is not on the island — drop that lead entirely. It's near Vermilion City. Checked properly
this time (matching the sink by proximity to each sprite, not exact coordinates, which was
silently hiding real engagement): of Vermilion's six buildings, five have real conversations on
record. **Map 92 has none — all five of its bodies (four trainers, one NPC) have never once been
engaged.** That's the strongest lead in the whole city.

## The job

1. Baton: any save on or near map 5 (Vermilion) with six badges — e.g.
   `data/local_runs/roster-bench/bike_vermilion.state`.
2. Enter map 92 (warp on map 5 at (12,19)) and `Rig.engage_bodies(("trainer", "npc"))`. Fight the
   four trainers — cheap at L99/L100 — and read the NPC's line in full.
3. **The moment anyone mentions FLY or hands over an item, stop and read the whole exchange.**
4. If map 92 isn't it, the fallback is Route 16 (map 28), reached from Vermilion:
   `5 -> 17 -> 10 -> 18 -> 6 -> 27 -> 28`. A shrub on that path needs CUT (Charizard has it).

## Discipline

- Screenshot anything that refuses to move you.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Commit as you go.
- **If you conclude you are blocked by something outside this repo (a missing binary, a deleted
  tool), you must show the command output proving it, in the same report.** A claim without that
  evidence will not be trusted.

## Definition of done

`docs/learnings/fly-vermilion-<run_id>.md`: what map 92 held, and whether Fly was found.
