# Mission: explore Seafoam Islands — every building, every NPC

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary.

**This mission is short on purpose.** The last two attempts at this water died on a long, dense
brief — one stalled reasoning for 90 minutes without acting. Don't write elaborate planning
scripts. Walk to a body, press A, read what it says, move to the next one.

## Baton

`data/local_runs/roster-bench/seafoam_progress.state` — inside Seafoam Islands, map 159, six
badges, full-HP party. You are already two floors in.

## The job

1. On this floor and every floor you reach inside Seafoam, call
   `Rig.engage_bodies(("trainer", "npc"))` — it walks to every body the cartridge lists for the
   map and talks to or fights each one. Fight what fights back; your party is L99/L100, none of it
   is dangerous.
2. **Enter every warp on the floor before leaving it** — doors, stairs, the lot. Don't skip one
   because it looks like a dead end.
3. Keep a plain list as you go: floor, what NPCs said, what was found, where each warp led.
4. If a warp leads to Cinnabar (map 8) or its gym (map 166), say so immediately and keep going —
   that's the goal this whole arc has been chasing.

## Two things already known — don't re-derive them

- **The entrance alcove is walled on three sides.** If you ever bank a state and reload it lands
  somewhere unexpected, check whether it's back at the entrance — `probe_step()` will silently use
  the door itself if nothing else moves, and it now prints when that happens. Don't bank standing
  directly on a warp tile; step one tile clear first.
- **Strength gates one specific spot inside** — an NPC already said "This requires STRENGTH." Note
  where, but don't stop there; other paths exist and you don't have Strength yet regardless.

## Discipline

- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Talk before fighting isn't always possible (some bodies are trainers who fight on contact) —
  that's fine, `engage_bodies` handles both.
- Commit as you go. `uv run pytest` and `uv run ruff check .` before touching `scripts/`.

## Definition of done

`docs/learnings/seafoam-explored-<run_id>.md` with the floor-by-floor list above. If you reach
Cinnabar or its gym, bank it and say what the gym door says.
