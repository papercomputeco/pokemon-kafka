# The CARD KEY, and the four engine defects that hid it (2026-08-31/09-01)

Supersedes the open questions in `badge6-saffron-card-key-gate.md`. That record ended asking
"why does the pocket model claim reachable where the engine refuses". All four answers were
ours; none were the cartridge's.

**Result:** CARD KEY picked up at map 210 (5F) **(21,16)**, banked `b6_key_won.state`. Two prior
sessions swept the building for it — ~25 Rockets fought, every reachable ball opened, a full lift
tour — and it was never a search problem.

## 1. The cartridge said where it was, and the parser threw the byte away

Gen 1 object data gives an item-ball sprite one extra byte: the item id. `parse_map` counted it
and discarded it. Now kept, so a story item is a lookup:

| item | map | cell |
|---|---|---|
| CARD KEY | 210 (Silph 5F) | (21,16) |
| SECRET KEY | 216 | (5,13) |
| SILPH SCOPE / LIFT KEY | 202 (Rocket Hideout B4F) | (25,2) / (10,2) |

The last row is the cross-check: both were picked up live earlier in this run, so the decode is
verified against the bag rather than against recollection. `Rig.ball_contents(map)` names a
floor's balls; `sweep_items(want=)` opens the wanted one first.

## 2. `reachable` walks over teleport pads; `walk` refuses to

A pad fires the moment you step on it, so a route *through* one is a route off the floor. `walk`
has always blocked pads; `reachable` never did. Every approach decision inside Silph — every
"same pocket, 0 hops" that the engine then refused — was made on the wrong number. `road.walkable`
is the movement question; `road.pads_reaching` names the ride hidden behind "could not reach".

## 3. A region whose only door is a pad was invisible to every leg

Neither the walk nor the facing-oracle can *stand* on a pad, so a region entered only by a pad
does not exist to them. It is nine steps if you ride: from 5F (26,3) a step east fires (27,3) and
lands on 7F (21,15); step off, step back on, and you return **standing on (27,3)** with (28,3)
one step away. The round trip matters — arriving on a pad does not re-fire it. `road.ride_pad`,
tried automatically by `Rig.approach`.

`road.rides_to(truth, pairs, map, targets, bodies)` answers the question a gated building
actually poses: *which door, on any floor, lands somewhere that can walk to this cell.* Use it
before planning any route inside Silph.

## 4. The wall that actually cost the sessions: a gate that was a body talking

`survey_pocket` records every refused step with what the game said — correct, and the sentence is
evidence. Hanging all of them on the map as permanent walls was not. **106 of 130 measured
"gates" are sprites talking:** "AAAAAAA got 1400 for winning!", "I am one of the 4 ROCKET
BROTHERS!", "Hey kid! What are you doing here?". Only 24 are doors: "Darn! It needs a CARD KEY!"

One false gate decided everything. 5F's `9,16,right` carried **"I heard a kid was wandering
around."** — a wanderer's small talk, recorded once and applied from both sides ever after. It
sits on the single tile between 9F's landing at (9,15) and the key at (21,16). Every route to the
key was pruned before any leg could plan it, silently, while the floor reported itself sealed
behind card-key doors that wanted the key we were hunting.

`attach_measured_gates` now hangs only door text and *silent* refusals (nothing spoke, so nothing
was standing there). **This reverses the bias `passable` was written with.** Over-blocking was
called the safe direction because under-blocking "costs a run". Measured: a false wall costs
*every* run and says nothing, while a missing one costs one hop that the leg then measures and
writes down. Prefer under-blocking.

First leg after the change, no consults: `233 --warp--> 210`, `picked up [(48, 1)] at (21,16)`.

## What is still true, and what to distrust

- The card-key **doors** on each floor (the 24 real ones) are good data.
- Any claim that a Silph pocket is *sealed* predates this fix and should be re-derived with
  `rides_to`. The 19-of-43-pockets figure in the older record was computed with 106 phantom walls.
- Party in `b6_key_won.state` has three fainted members. Saffron's Pokémon Center is **map 182**,
  door (9,29) — identified by the interior template (14x8, tileset 6, nurse npc at (3,1)), the
  same signature as Cerulean's map 64, not from memory. `supervisor.py run --heal` uses it.

## Operating notes (they cost two false diagnoses)

- Launch a pi operator **detached** (`setsid nohup ... & disown`); a plain background task gets
  its process group reaped mid-leg and looks like a crash.
- pi's child renames itself `pi`, so `ps -C node` reports a live run as dead. Use
  `pgrep -f pi-coding-agent` — and never `pkill -f` a pattern your own command line contains.
- `pi -p` buffers stdout until exit; watch `~/.pi/agent/sessions/--<cwd>--/*.jsonl` instead.
- The Extractor seat (kimi-k2.6:cloud) gets exactly **300 seconds** from this gateway and spends
  all of them thinking: six attempts, six non-answers. Consults stream now, and a closing call
  hands the seat its own cut-off reasoning back — that answered in 49s. See `expedition_crew.py`.
