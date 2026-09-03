# Mission: Route 4 was declared sealed. Nobody talked to anyone. Go talk to them.

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary.

**This mission is short on purpose.** Long, dense briefs have killed two legs today. Do this:
walk to a body, press A, read what it says, move to the next one.

## Why this mission exists

Two legs today declared the water route to Cinnabar "sealed" — twice wrong, both times because
nobody looked at the actual screen. Checked just now: the same thing happened on this side of the
map. **Twenty-nine NPCs sit on the maps between here and Pallet Town — Route 4, Diglett's Cave
area, Pewter, Route 2, Viridian, Pallet itself — and not one has ever been talked to.** One of
them stands at (9,8) on this exact map, in the pocket that got called sealed.

Don't trust the collision grid. Go talk to people.

## Baton

`data/local_runs/roster-bench/v8m10-15.state` — map 15 (Route 4) at (89,11), six badges, healthy
party: Charizard L100, Dugtrio L100, Gloom L99, Primeape L99, Pidgeot L99, Hypno L99.

## The job

1. `Rig.engage_bodies(("trainer", "npc"))` on this map first — there's an NPC at (9,8) nobody's
   spoken to. Read what it says.
2. Work toward Pallet Town (map 0), engaging every body on every map you pass through: Route 4,
   the Diglett's Cave area, Pewter City, Route 2, Viridian City, Pallet Town. `road.route`/
   `supervisor.py run --goal <map>` will plan the path; let it route, don't hand-plan a chain.
3. **If anything refuses to move you, screenshot it and look before deciding it's a wall.** The
   engine does this automatically now on a stuck arm and on exhaustion — but if you're driving
   `Rig` directly, call `Rig.screenshot(tag)` yourself.
4. Once in Pallet, walk south. That's the route to Cinnabar the game itself describes — Route 21,
   straight south of Pallet, into the water. See if it's actually open.

## Discipline

- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Don't re-derive tile tables or hunt ROM addresses.
- Commit as you go. `uv run pytest` and `uv run ruff check .` before touching `scripts/`.

## Definition of done

`docs/learnings/route-to-pallet-<run_id>.md`: what every NPC said, what actually blocked movement
(with a screenshot, not a tile id), and whether Route 21 south of Pallet is open.
