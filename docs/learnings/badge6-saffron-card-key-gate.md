# Badge 6 (Sabrina): cleared to Saffron, stopped at the CARD KEY

Session 2026-08-30/31, first legs driven by the real `scripts/supervisor.py run`. Badges
`0b00011111` throughout — no badge was won. What was won is the road, and two gates that are
now measured instead of assumed.

## Cleared, and banked

`BADGE5.state` (Fuchsia gym) → Fuchsia → Saffron → inside Silph Co, then Silph 1F → 2F → 3F →
the floor below the top. Batons under `data/local_runs/roster-bench/`: `b6-7`, `b6-10`, `b6`,
`b6_silph-234` (map 209), `b6_silph-178` (Saffron, at the gym door).

**The measured road Fuchsia → Saffron**, which is not the one `rt.route` reaches for first:

```
7 -> 26 -> 25 -> 24 -> 23 -> (gate house 87) -> 4 Lavender -> 19 Route 8 -> 10 Saffron
```

Two of those hops are gate buildings, not edges — `cross_edge` returns `no-path` and
`pass_gate` gets through: **23→4** and **19→10**. Two others are graph paths the world refuses
and the supervisor auto-bans:

- **29→28, Cycling Road.** Map 28 is 20x144 and every ledge extracted from this cartridge hops
  *down*, *left* or *right* — there is no upward ledge anywhere in the ROM. The connection
  table is undirected; the world is not.
- **30→31, Route 19.** Water. Needs Surf, which the engine does not have.

**Route 12 (map 23) is severed** into a south region (428 cells, y21–107) and a north region
(67 cells, y0–17). Gate house 87 is the only link: door **(10,21)** on the south side,
**(10,15)/(11,15)** on the north. Its corridor pinches to a single cell at **(10,63)** — grid
row 63 is walkable only at x=10 — and a trainer parked at **(10,62)** plugged it. Beating that
trainer opened the road. The trainer we kept bumping into at (14,76) was a bystander; column 15
walks straight around it. See `road.blocking_body`.

## Gate 1 — Sabrina's gym door (the reason no badge was won)

Saffron's gym is the warp at **(34,3) → 178**. The body at **(34,4)** alone severs that hop, and
what it says is the whole finding:

> **"Get out of the way!"**

Engaged three times; it does not battle, does not move, and does not vary. This is a script
gate, not a trainer. Full record: `docs/learnings/map10-to-178-stuck-20260831-012749-466a.md`.

## Gate 2 — the CARD KEY (what actually blocks gate 1)

Silph Co floors are maps **181, 207, 208, 209, 210, 211, 212, 213, 233, 234** (234 is 16x18,
the small top floor), all **tileset 22** — the facility set, where tiles decide where you end up
and a planned walk is a category error.

- **Silph 1F's pad at (16,10) → 208 is dead.** `rt.route` picks it because the graph has no
  opinion about which doors work. The floor's live ways up are **(26,0) → 207** and
  **(20,0) → 236**.
- On **map 209**, the warp at **(11,7) → 234** is refused, and the NPC at **(14,6)** says on
  screen that it **requires a CARD KEY**. That is read from the game, not recalled.

`b6_silph-234.state` is banked on 209 in front of that warp. An earlier run *reported* reaching
234; it had not. The read was torn across the warp window — `(234, 17, 11)` on a map sixteen
tiles wide — and `Rig.settled_pos()` exists now so that "arrived" can never again come from a
position the world has not finished writing.

## The card-key hunt, and what it ruled out

Second session on this gate. The decisive measurement is a *refusal with text*: standing on
map 234 at (10,9), every planned walk returned `refused` while raw directional presses moved
fine, because stepping up prints

> **"Darn! It needs a CARD KEY!"**

The tile at (10,8) is a script gate, and the collision grid extracted from the cartridge calls
it plain walkable floor. That one fact explains the whole hunt: `road.reachable` over-reports on
every Silph floor, so the item sweep and the trainer approach kept choosing approach cells
behind doors that will not open. Eleven item balls with "reachable" approach cells yielded
exactly one pickup, and two trainers four tiles away were "unreachable".

**Ruled out by measurement, not by argument:**

- **The trainers on 207–212 do not carry it.** All of them were fought (14 Rockets, ~10k in
  winnings, banked `b6rock-207` … `b6rock-212`). The bag afterwards is unchanged apart from
  CALCIUM: DOME FOSSIL, HM01, HP UP, HYPER POTION, LIFT KEY, MOON STONE, NUGGET, POKe FLUTE,
  RARE CANDY, S.S.TICKET, SILPH SCOPE, SUPER POTION, TM07/10/11/21/24/28/34. **No CARD KEY.**
  So the Rocket Hideout's LIFT KEY template — beaten Rocket drops the key — does *not* apply here.
- **The reachable item balls do not hold it.** Of the 11 on 208–212, only (1,9) on 212 opened,
  and it was CALCIUM. The rest sit behind card-key doors.
- **A full bag is not the cause.** `make_room` frees a slot by tossing the largest stack and was
  verified live (20 slots -> 19). Pickups land when the tile is reachable.

**Never visited:** maps **236, 213, 233, 235**. Silph 1F has three ways up — (26,0)->207,
(16,10)->208 (dead), and **(20,0)->236** — and `rt.route` picked 207 every single time, so 236
has never been entered. That is the open lead, and it is a lookup rather than a guess.

## The lift tour — every floor visited, still no key

A lift car is not a hop in the connection graph (`rt.route` correctly reports no path out of
map 236), because it is a **control panel**, and the panel is a **sign, not an NPC** — Silph's
at (3,0), the Rocket Hideout's at (1,1). That is why talking to bodies never found it. The
floor list scrolls like the ITEM list (`0xCC26` cursor inside a three-row window, `0xCC36`
scroll), and menus render to the **window** tilemap, never the background.

`supervisor.py lift-tour` rode all ten floors. The floor-to-map mapping, read off the panel:

| 2F | 3F | 4F | 5F | 6F | 7F | 8F | 9F | 10F | 11F |
|---|---|---|---|---|---|---|---|---|---|
| 207 | 208 | 209 | 210 | 211 | 212 | 213 | 233 | 234 | **235** |

**Map 234 is 10F, not the top floor** — an earlier note in this file assumed otherwise. 11F is
map 235, and it is **tileset 16**, not 22.

Roughly 25 Rockets fought across the tour and the walked sweep combined. Total yield: **CALCIUM**
(7F) and **TM26** (10F). **No CARD KEY, on any floor, in any pocket the lift reaches.**

The lift enters *different* pockets than walking does — riding to 5F lands on map 210 at (20,1)
where every walked approach arrives at (8,15) — but neither region contains the item balls. Six
balls were attempted and logged as unreachable: (3,9)/(4,7)/(5,8) on 209 and (2,13)/(4,6)/(21,16)
on 210. They sit in a *third* region behind card-key doors.

**11F is the sharpest measurement.** The lift drops us at (13,0)→(15,10) inside a pocket of
**52 cells out of 324**. Giovanni and the Silph president are the two npcs at **(7,5)** and
**(10,5)**, both outside it, along with two of the floor's three trainers.

Two things worth carrying forward:

1. **Giovanni is `kind: "npc"` in the extraction, not `"trainer"`** — his sprite carries a
   different text flag — so `engage_trainers` walks straight past him. A floor clear that only
   fights `kind == "trainer"` will never fight a boss.
2. **The pads are floor-to-floor, not intra-map — a guess this record already had to correct.**
   The first version of this note called the pads intra-map warps on the tileset-22 floors and
   named riding them as the next move. Counted, that is wrong: of Silph's floors only 208 and
   213 hold *any* intra-map warp (two each); every other floor has none. What the floors have
   instead is dense **cross-linking to other floors** — 209 warps to 208, 210, 211, 234 and 236;
   210 to 208, 209, 211, 212, 233, 236; and so on. Those are the teleport blocks 2F describes,
   and `rt.route` already models them as ordinary warps.

   Two consequences. The reachable set grows by riding *between* floors, since each pad lands in
   a particular pocket of its destination — so "which pocket of floor N does floor M's pad reach"
   is the map worth building. And `_reroute_around` bans a **map pair** on first refusal, which
   throws away every other route to that destination; on a graph this densely cross-linked that
   is too blunt, and banning the specific warp tile would be right.

   `Rig.escape_pocket` (ride until we stand outside our own walkable region, same map) was built
   for the wrong floor and returns False on Silph, correctly. It is the right tool for exactly
   one place measured so far: **Sabrina's gym, map 178, which has thirty intra-map pads.**

## Why static reachability cannot answer anything inside Silph

The last and most expensive correction of the session. Having found that 11F is reachable from
three doors and that only map 212's at (5,7) lands in Giovanni's 128-cell region, the whole chain
was verified with `road.reachable` — **208 → 212 (landing (5,3)) → (5,7) → 235 (3,2) → Giovanni**
— and every hop checked out. It was then run, and the *first westward step on 208* printed:

> **"Darn! It needs a CARD KEY!"**

`road.reachable` walks the extracted collision grid, and the grid calls a card-key door plain
walkable floor. So **every static reachability claim made anywhere inside Silph over-reports**,
including the 343-cell region on 208, the 128-cell region on 235, and the six item balls listed
earlier as "approach cells reachable". None of those numbers mean what they appear to mean. The
only trustworthy statement about a Silph pocket is one obtained by stepping into its boundary and
reading what the game prints.

The tractable next piece of work follows directly: **build the door map by measurement.** For
each pocket, walk its boundary, attempt each outward step, and record which ones print the CARD
KEY line. `LegRunner.read_refusal` already captures exactly that sentence and keys it by (map,
x, y), so a boundary sweep would turn the invisible locks into data the graph can carry. Until
that exists, no route inside Silph can be planned — only tried.

## The measured door map, and the shape of what remains

`supervisor.py survey` walked every floor by attempted steps. The grid over-reports on all ten:

| floor | map | measured | grid claimed | gates |
|---|---|---|---|---|
| 2F | 207 | 239 | 319 | 4 |
| 3F | 208 | 233 | 343 | 2 |
| 4F | 209 | 205 | 303 | 4 |
| 5F | 210 | 168 | 317 | 6 |
| 6F | 211 | 200 | 238 | 2 |
| 7F | 212 | 100 | 223 | 4 |
| 8F | 213 | 263 | 274 | 4 |
| 9F | 233 | 112 | 269 | 8 |
| 10F | 234 | 114 | 168 | 2 |
| 11F | 235 | 49 | 52 | 0 |

**36 card-key gates**, each an exact `(x, y, direction)` in `survey-<map>.json`. Every reachable
item ball in the building is now open; 10F's three yielded TM26, RARE CANDY and CARBOS. **No
CARD KEY anywhere we can stand.**

**The building is a graph of pockets, and we have surveyed one pocket per floor.** Cross-checking
every warp landing against the surveyed pockets finds **51 landings that fall outside them** —
i.e. 51 doorways into ground nobody has walked. Several are reachable right now: from 10F's
pocket, the pads at (13,7) and (13,15) land on 209 at (17,11) and (3,15), neither of which is in
209's surveyed 205-cell pocket. Riding (13,7) was verified live and lands in a different region.

So the search is not exhausted, it is *unstructured*. What it needs is a **pocket-graph explorer**:
nodes are (map, pocket), edges are the measured exits, and each newly entered pocket gets
surveyed and swept before the frontier advances. Every piece of that exists — `survey_pocket`
measures a pocket, `sweep_items` empties it, the exits are already in the survey JSON — but
nothing walks the frontier, so exploration has been me picking doors by hand.

## The pocket model, and the two bugs it took to get right

The engine's unit of place was the **map**. Inside a gated building that is one level too
coarse: with the doors shut, "map 235" names two disconnected places — the 52-cell pocket the
lift reaches and the 128-cell one holding Giovanni — and map-level routing cannot tell them
apart. That, not the card key, is what defeated a whole session. `rom_truth.pockets()`,
`pocket_of()`, `pocket_exits()` and `route_pockets()` make the pocket first class.

Getting it right took two corrections, both worth keeping:

1. **A static pocket model is only as good as its gate coverage.** The first pocket graph was
   built from gates measured in one pocket per floor, and the six-hop chain it produced to
   Giovanni died on its fourth hop, in ground nobody had surveyed. `supervisor.py explore`
   answers this with coverage rather than a better guess: walk the frontier, survey each pocket
   entered, merge its gates, push its real exits. It needs `--area` — unbounded, it followed
   Silph's exits out into Saffron and then Route 7.
2. **A shut door is shut from both sides.** Gates are recorded from whichever side somebody
   stood on, and honouring only that direction makes connectivity *asymmetric* — 234 cells
   reachable from one side of a 233 door, 109 from the other, with `pocket_of` reporting both
   cells as the same pocket. That is impossible for a flood fill, and it is exactly why the
   chain broke. `passable` blocks both ends now, which matches the one door measured from both
   sides (234's (10,8), refused up from (10,9) and down from (10,7)) and errs the safe way:
   over-blocking costs a route we might have had, under-blocking costs a run.

With 117 measured gates and the symmetric rule, **19 of 43 pockets are reachable** and the model
*declines* to route to Giovanni rather than proposing a chain that breaks halfway. That is the
improvement; the earlier route was an artifact.

**The remaining search space, and it is small.** The card key must be in the reachable component,
because the game is completable without it. What is in there and untried:

- unopened item balls: map **210 p1** (2,13), **210 p2** (21,16), **212 p1** (1,9)
- npcs never spoken to: map **207 p0** (10,1), **208 p0** (24,8), **213 p0** (4,2), **234 p2** (9,15)

Standing caution: under the conservative rule more coverage means *fewer* provable routes, so a
false-positive gate silently removes a real path. `survey_pocket` skips cells with a body on
them, but a wanderer that moved, or a trainer freeze, would still register as a door. If the
reachable set shrinks as coverage grows, audit the gates before believing the shrinkage.

## Where it actually stands, and the one well-defined question left

Every npc and trainer reachable from the six lift batons has been spoken to, and every ball
they can reach is open. Yield: CARBOS and RARE CANDY on 10F. **No CARD KEY.**

The remaining targets are all *routable on paper* and *unreachable in practice*, which is the
open question and it is now sharp:

| target | model says | live says |
|---|---|---|
| 212 (1,9) ball, from 7F baton | same pocket, 0 hops | could not open |
| 208 (24,8) npc, from 3F baton | same pocket, 0 hops | could not reach |
| 210 (21,16) ball, from 5F baton | same pocket, 0 hops | could not open |

Two layers explain part of it and neither explains all of it:

1. **A pocket is terrain; bodies sever it further.** `pockets()` is bodiless by construction, so
   it is an *upper bound* on where you can stand. On 210 a single sprite at (28,4) severs the
   ball at (21,16) — `blocking_body` names it — and that body is itself unreachable from the
   baton, so the severance is not clearable from there.
2. **Gate coverage is still incomplete in these pockets.** Where the body-aware region *does*
   include an approach cell (212, 208) and the live approach still fails, the model is
   over-reporting, which means gates nobody has walked into yet.

So the question for the next session is not "where is the card key" but: **why does the pocket
model claim reachable where the engine refuses, on 212 (21,3)->(1,9) and 208 (18,8)->(24,8)?**
Both are one `survey_pocket` away from an answer, and the survey now re-probes rather than
trusting the gate file it feeds, so it can correct itself.

Worth noting what has *not* been tried: physically walking the pocket route from the Silph
entrance. Every attempt so far has teleported in via the lift, and the 19-reachable figure is
computed from the entrance — the two are not the same starting set.

## What the next run needs

1. **Build the pocket-graph explorer.** Not another hand-picked door: a frontier walk over
   (map, pocket) using the measured exits, surveying and sweeping each new pocket. 51 landings
   are known to lead outside everything surveyed so far; that is the search space, and it is
   finite and enumerated.
2. **Fight the boss as an npc.** On 11F (map 235) the two npcs at (7,5) and (10,5) are Giovanni
   and the president. Whatever reaches them has to engage `kind: "npc"` sprites, which the
   current `--clear-floor` does not.
3. **Then Giovanni → Silph falls.** Expect the gym guard at (34,4) to stand down once Silph falls; that
   is the hypothesis this leg leaves behind, not a fact — verify it by walking back to (34,3).
4. **Then badges 7 and 8 are blocked on SURF**, which does not exist in `scripts/` in any form
   (only field-Cut, `road.cut_facing`). Cinnabar (map 8) connects only north→32 and east→31,
   both water. Surf and Strength come from the Safari Zone in Fuchsia. Build field-HM support in
   the engine, with tests, before planning either leg.

## Engine changes this leg paid for

Every one of these was a bug found by running, not by reading:

| what | why it mattered |
|---|---|
| `Rig.settle()` | a baton banked mid-dialogue swallows every step; `BADGE5.state` fingerprinted a wall that was not in the world |
| `probe_step` avoids warps | the settle probe stepped onto Fuchsia gym's mat and warped back inside |
| `rt.route(banned=)` + reroute | Cycling Road and the dead Silph pad, routed around instead of argued about |
| `road.blocking_body` / `gate_doors` | name the body that severs the map, not the one underfoot |
| `_clear_blocker` retires verdicts | Route 12 was banned as impassable on evidence gathered while the blocker still stood |
| per-seat tokens **and** timeouts | the Extractor was starved: 6,286 reasoning tokens and no answer at a 1,600 cap; raising tokens without the wait just changed the failure to "timed out" |
| `Rig.oracle_goto` restored | it did not survive the promotion out of the scratchpad, and tileset 22 is where it is the only mover |
| `settled_pos` | a torn read across a warp is not a place |
