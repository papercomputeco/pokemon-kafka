# Mission: Seafoam — go left on every floor, don't rush the vertical shaft

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary. **Kept short on purpose.**

## Why

The last Seafoam leg raced straight down the doors — 1F→2F→3F→4F→5F — and 5F was a dead end. It
also flagged several NPCs and doors on the **west (left) side** of each floor as "pad pockets" and
skipped them without trying. That's the same mistake as calling a boulder a wall: a label instead
of a look.

## The job

1. Baton: `data/local_runs/roster-bench/seafoam_1f_safe.state` — map 192, one step clear of the
   entrance, six badges.
2. **On every floor, work the west side of the map fully before taking a door onward.** Try
   approaching a blocked body or door from more than one direction — up, down, left, right — before
   deciding it's unreachable. `road.pads_reaching`/`road.rides_to` name a ride if a plain walk can't
   reach something; try those before giving up on a spot.
3. Talk to or fight every body you reach. Read what it says in full.
4. If a warp anywhere leads to a map you haven't seen before — especially anything outside the
   192/159/160/161/162 chain — say so immediately and go look.

## Discipline

- Screenshot anything that refuses to move you, before deciding what it is.
- Never bank a state standing directly on a warp tile — step one tile clear first.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Commit as you go.

## Definition of done

`docs/learnings/seafoam-west-<run_id>.md`: what was on the west side of each floor that the last
leg skipped, and whether any of it leads somewhere new.
