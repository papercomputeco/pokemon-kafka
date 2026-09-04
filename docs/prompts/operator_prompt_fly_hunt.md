# Mission: find who gives HM02 (Fly) — start on our own island, nobody's checked it

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary. **Kept short on purpose — long briefs have killed two legs today.**

## Why here first

The cartridge's HM02 text reads: *"...over water! Oh, you found my secret retreat! ... received
HM02! HM02 is FLY!"* That same text block also contains the Cycling Road sign and *"PALLET TOWN
is in the west"* — the same cluster as NPCs on the sea south of Fuchsia. **Map 30 — our own
island — has ten trainer sprites, and not one has ever been talked to**, at any point this whole
project. The ones far from the entry point are the likely candidates:

    (8,7) (13,7) (13,25) (4,27) (16,31) (9,11) (8,43) (11,43) (9,42) (10,44)

## The job

1. Baton: `data/local_runs/roster-bench/b8_BATON_island_gyarados_safe.state` (map 30, six badges).
2. `Rig.engage_bodies(("trainer", "npc"))` — it walks to every listed body and talks or fights.
   If it can't reach one, note which and why, but keep going to the rest first.
3. **The moment anyone mentions FLY, a secret retreat, or hands over an item, stop and read the
   full text.** That's the find.
4. If none of the ten say anything about Fly, fall back to **Route 16** (map 28), reached from
   **Vermilion (map 5)**: `5 -> 17 -> 10 -> 18 -> 6 -> 27 -> 28`. This is a real, modeled route
   and it never touches the Cerulean/map-15 pocket two legs called sealed today — an independent
   path, confirmed from the connection graph. **Somewhere on this path is a shrub you need CUT to
   clear** — the connection graph can't show exactly where, that's a tile-level detail, so expect
   a refusal and read what it says rather than assuming a dead hop. Charizard already knows CUT.
   The extracted map data shows zero recorded warps on map 28 itself, so a building there may not
   register as a normal door — walk the route and look, don't just trust the warp list.

## Discipline

- Screenshot anything that refuses to move you, and look before calling it a wall.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Commit as you go.

## Definition of done

`docs/learnings/fly-hunt-<run_id>.md`: what each of the ten said, whether HM02 was found, and if
not, what Route 16 actually looks like.
