# Mission: cut through, don't stop at the Route 16 crossing

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary. **Kept short on purpose.**

## What the last leg found, verified independently

Map 92 (the Fly building) really is sealed off by land — confirmed twice now: 42 walkable cells
touch its door, 825 once water is allowed, and the current baton sits outside that pocket. That
part is real, not a guess. Getting there needs a surfer, which is a separate, later trip.

**But there's a cheaper option first.** The route `5 → 17 → 10 → 18 → 6 → 27 → 28` (Vermilion to
Route 16) was refused at the `17 → 10` crossing, and the last leg stopped there instead of trying
the obvious thing: **that crossing is a Cut-tree shrub, not a dead hop, and Charizard already
knows Cut.**

## The job

1. Baton: `data/local_runs/roster-bench/bike_vermilion.state` — map 5, six badges, Charizard knows
   CUT (`knows_move("CUT")`).
2. Walk `5 → 17`. At the refused `17 → 10` crossing, **use the CUT field move on the blocking
   tile** (`Rig.use_field_move("CUT", face=..., species="Charizard")`) instead of stopping.
3. Continue `10 → 18 → 6 → 27 → 28` if the shrub clears.
4. Enter every building on Route 16 and `Rig.engage_bodies(("trainer", "npc"))`. Read every line.

## Discipline

- Screenshot anything that refuses to move you, and look before deciding what it is.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Commit as you go.
- If you conclude you're blocked by something outside this repo, show the command output proving
  it, in the same report.

## Definition of done

`docs/learnings/cut-to-fly-<run_id>.md`: whether Cut cleared the shrub, what Route 16 held, and
whether HM02 (Fly) was found. If not, say plainly that map 92 (via a surfer) is the remaining lead.
