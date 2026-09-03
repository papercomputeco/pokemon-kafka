# Investigation: the three wedges between us and badge 8

You are the Investigator. Use `uv run ...` for all Python (AGENTS.md). Print `date` at the start
and before any summary. **This is a recon mission: the product is observations, not progress.**

A previous leg concluded *"badge 8 is a closed world on this cartridge"*
(`docs/learnings/viridian-badge8-closed-world.md`, commit `8a3798c`). **Treat that as a hypothesis
to break, not a fact.** It is right about the connection graph and wrong about what the graph
knows. Your job is to find whether any of three wedges opens.

## What is already measured — do not re-derive it

- Viridian (map 1) is entered only from maps **12, 13 or 33**. The single overland chain into that
  cluster is `3 -> 15 -> 14 -> 2 -> 13 -> 1`. Water (maps 30/31/8/32) is the only alternative and
  needs a surfer.
- **Map 15 connects `south -> 14`** — NOT west. The earlier leg probed the west edge and concluded
  the world was closed; that probe tested an edge with no connection on it.
- Entering map 15 from Cerulean lands at **(89,11)**. `survey_pocket` from there measured
  **114 cells, x 63..89, y 10..15, 0 talking walls, 206 probes** — and **no cell on row 17**, which
  is where the exit to map 14 lives (open cells at (6..11,17) and (86..89,17)).
- Physically from (89,11): `left` and `up` move, `down` refuses, `right` exits east to map 3.

## Wedge 1 — why does the east pocket stop at x=63?

114 cells and **zero talking walls** means nothing spoke; it is collision, a ledge, or a tile-pair.
Map 15 is tileset 0, where the ROM's one-way **LEDGE** hops apply — a two-cell jump over a tile the
grid calls solid, and they are one-way.

**Go to the western boundary of the pocket and read what happens.** Walk the x=63..65 column at
every reachable row, step west at each, and record the outcome per cell. A ledge that only jumps
one way would explain a pocket you can leave but not re-enter — and would mean the route exists
but not from this side.

## Wedge 2 — Mt. Moon, which the graph cannot see

This is the most promising one. Map 15 has **three warps**: `(11,5) -> 68`, `(18,5) -> 59`,
`(24,5) -> 60`. Maps **59 / 60 / 61** are Mt. Moon (tileset 17; the nav skill leg's success
criterion is `final_map_id: 60`).

**The extracted graph is blind here.** Mt. Moon's only outside exits are warps to **255**, the
LAST_MAP sentinel — a runtime value, not a table entry — so `route()` cannot make an edge from
them and no router will ever plan through Mt. Moon. That is why every path search says `15 -> 14`
is the only way west. **This project has already cleared Mt. Moon** (`demo-runs/beat12-mt-moon-clear`).

Measure it:

1. Can the warps at (11,5)/(18,5)/(24,5) be reached at all? They sit at x=11..24, and our pocket is
   x=63..89 — so probably not from the Cerulean side. **Say so if not**, that is the answer to
   wedge 1 as well.
2. If you can get in: **go through Mt. Moon and record which map you come out on.** If the far exit
   lands on map **14** or **2**, the west is open and the "closed world" verdict is dead.
3. Either way, record the warp destinations you actually observe. A LAST_MAP warp's real
   destination is only knowable by walking through it, and nobody here has written one down.

## Wedge 3 — is there still a surfer?

The water route needs SURF. The party is now Charizard L100, Dugtrio L100, **Gloom L99**,
Primeape L99, Pidgeot L99, Hypno L99 — **Gyarados is gone**, and it was the only surfer.

**Check the PC box.** `Rig.center_pc` / `CENTER_PC = ((13,4),"up")` opens the player's PC; BILL's
PC is the Pokémon box. If Gyarados is in storage, withdrawing it reopens the entire water route and
badge 7 as well. If it is not there, say so plainly — that closes the option honestly.

## How to work

- `LegRunner.recon` talks to bodies before the first consult, and the Investigator (`recon` tier)
  picks which body is worth the budget when there are more than you can ask.
- **The window layer is sticky** — a naive read returns `'OPTION EXIT'` or the last line. A text box
  blocks movement, so gate every read: `talking = not r.probe_step()`. Press B between bodies.
- **A body with no walkable neighbour is not unreachable** — `road.counter_stands` talks across a
  counter. That is how the marts opened.
- Map 15 holds an `npc` at (9,8), a `trainer` at (63,3) and an `item` at (57,3) — all outside the
  surveyed pocket. If you reach any of them, talk and record.

## Discipline

- **Never `pkill -f <pattern>` where the pattern is in your own command line.** Two legs killed
  themselves that way; the harness blocks it now. Kill by PID.
- Do not diff RAM or hunt ROM addresses. Five legs died that way.
- **Do not emit a `discovery` event per frame.** The last two legs wrote 221k and 1.25M events and
  the day's sink is over 40 MB. Record each distinct sentence once.
- Commit as you go; `uv run pytest` and `uv run ruff check .` before touching `scripts/`.

## Definition of done

`docs/learnings/wedges-<run_id>.md` answering, with coordinates and the game's own sentences:

1. What is at the pocket's western boundary on map 15, and whether it is one-way.
2. Whether Mt. Moon can be entered from map 15, and **what map its far exit actually lands on**.
3. Whether a surfer exists in the PC box.

A documented "all three are shut" is a real result and closes the question honestly. A single
opened door changes the whole arc.
