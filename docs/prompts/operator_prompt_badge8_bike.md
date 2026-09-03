# Mission: ride the bike to badge 8

You are an autonomous operator on this repo. Use `uv run ...` for all Python (AGENTS.md). Print
`date` at the start and before any summary. Work the whole budget; do not stop early.

Six badges are won and **the BICYCLE is in the bag**. Badge 7 (Cinnabar) is water-locked and
parked — ignore it. **Your objective is badge 8: Giovanni, in Viridian's gym.**

## The baton

`data/local_runs/roster-bench/bicycle.state` — map **66** (Cerulean BIKE SHOP) at (4,2), badges
`0b00111111`, bag **19/20**. Party all healthy: Charizard L100, Dugtrio L100, Gloom L99,
Primeape L99, Pidgeot L99, Hypno L99. That team beats Giovanni comfortably; this is a navigation
and discovery job, not a fighting one.

**You have no Poké Balls, and ₽92,360.** See "the marts are open now" below — that is new.

## What the bike is for, and what is NOT known

Measured, from the cartridge's own text: **"You need a BICYCLE for CYCLING ROAD!"** The overland
route to Viridian was blocked at **`29 -> 28`** for exactly that reason. You now hold the key.

**Nobody has ridden it. Everything past this point is discovery, and that is the job:**

- **Is the gate open now?** Nobody has tested `29 -> 28` (or `27 -> 28`) holding a BICYCLE. Go and
  find out, and **record what the game says either way**.
- **Does the engine need to know you have it?** The bike is an item, not a field move. The gate may
  be a body that reads your bag, or a sign, or a tile rule. Read the refusal before theorising —
  if something still refuses, `Rig.textbox()` gives the sentence and it is the instruction stream.
- **Which side do you enter from?** The engine's own route from Cerulean is
  `3 -> 16 -> 10 -> 18 -> 6 -> 27 -> 28 -> 29`, i.e. it enters Cycling Road from the **north (27)**
  and never walks `29 -> 28` at all. Either direction is fine; the badge is the goal, not the hop.
- **Viridian's gym is map 45**, entered by the warp at **(32,7) on map 1**. **Its opening condition
  is UNVERIFIED.** Do not assume seven badges opens it and do not assume it is shut. Walk to that
  door and read what the game says. That single observation is the most valuable thing this leg
  can bring back, even if the badge does not follow.

## You route. I state constraints.

`supervisor.py run --goal 45` plans it, and `_reroute_around` bans a failed hop and re-plans, so a
wall is a measurement rather than a dead end. **Do not accept a hand-written hop chain from anyone,
including this file.** Constraints to route *within*:

- **The sea is unsolved.** Maps 30 / 31 / 8 / 32 are water (6% walkable against 30–79% for land)
  and five legs died there. `rom_truth.route` will happily offer a Fuchsia→Viridian path through
  them because it is fewer hops. Treat any hop into 30/31/8/32 as banned.
- **`3 -> 16` is `no-path` from (3,9,12)** — measured twice, and it is the top blocker in this arc.
  It killed two badge-8 legs and it stopped the bike from being ridden. If you find a way through
  or around it, **that is a result worth more than the badge.**
- **`15 -> 14` is `no-path` from four independent entry routes**, all landing in the same sealed
  pocket of map 15.
- **`29 -> 28`** was refused for want of a bicycle. You have one. Re-test it.

## The marts are open now — this is new capability

Until this week every shop clerk in the game was unreachable: a counter body has no walkable
neighbour, and the engine only ever tried adjacent tiles. `road.counter_stands(body)` now gives
the cell two tiles away and the facing that talks across it, and `_go_and_talk` falls back to it.

Confirmed live at Cerulean's mart (map 67, clerk at (0,5), stand (2,5) face left):
*"Hi there! May I help you?"* … *"POKé BALL? That will be ₽200. OK?"*

There is one mart per city — Viridian 42, Pewter 56, Cerulean 67, Vermilion 91, map 150,
Cinnabar 172. `quartermaster.buy()` has existed all along and **has never once been called**:
the telemetry holds zero purchase events. You have ₽92,360 and no Poké Balls.

**Spend some of it if it helps you.** Balls, potions, repels — this is your judgement call, and
whatever you buy, record it: it will be the first purchase this project has ever made.

## Recon is a step, and the Investigator is a seat

`LegRunner.recon` talks to the bodies the cartridge lists before the first consult on a wall, and
the sentences reach the seats under `HEARD:`. When there are more bodies than budget, the
Investigator (`recon` tier) picks which one is worth it.

- **Talk to everything on the way.** The arc that engaged 82 bodies won its badge; the arc that
  engaged 0 lost five legs (`benchmarks/2026-09-02-crew-vs-solo.md`).
- **The window layer is sticky** — a naive read returns `'OPTION EXIT'` at every cell. A text box
  blocks movement, so gate the read: `talking = not r.probe_step()`.
- **A body with no walkable neighbour is not unreachable** — try `road.counter_stands`.

## Discipline

- **Never `pkill -f <pattern>` where the pattern is in your own command line** — it matches your
  own shell and kills the run. Two legs died this way; the harness now blocks it. Kill by PID.
- Do not re-derive tile tables, diff RAM, or hunt ROM addresses. Five legs died that way. If a
  probe says *nothing works in any direction*, suspect the harness, not the cartridge.
- The bag is **19/20**. A full bag silently refuses gifts and purchases — `Rig.make_room()` first.
- Commit as you go. `uv run pytest` and `uv run ruff check .` before any commit touching
  `scripts/`; this repo requires **100% coverage**.

## Definition of done

1. **`BADGES` gains the eighth bit**, banked as `badge8.state`. If you do not get it, bank
   whatever you did reach.
2. **What the Cycling Road gate said with a BICYCLE in the bag**, written down — open or not.
3. **What the Viridian gym door said**, written down — open or not.
4. `docs/learnings/bike-to-badge8-<run_id>.md` with the above plus every body spoken to and every
   route banned. A documented failure is worth more than an undocumented badge.
