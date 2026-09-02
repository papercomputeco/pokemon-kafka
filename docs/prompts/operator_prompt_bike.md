# Investigation: the BICYCLE

You are the Investigator on this repo. Use `uv run ...` for all Python (AGENTS.md). Print `date`
at the start and before any summary. Work the whole budget; do not stop early.

**This is a recon mission. Its product is observations — sentences the game said, with the map and
coordinates they were said at.** Talk to everything. A body you did not speak to is a fact you do
not have. Across four earlier legs this project engaged **zero** bodies on a whole story arc and
lost five legs to reasoning about a world nobody had looked at.

## Why the bike matters

The overland route to Viridian (badge 8) is blocked at **`29 -> 28`**, and the cartridge says why
in its own words: **"You need a BICYCLE for CYCLING ROAD!"**. The northern alternative is blocked
too — `15 -> 14` is `no-path` from four independent entry routes, all landing in the same sealed
pocket of map 15. The bike is the cheapest unblocking move available.

## What the cartridge already told us — extracted, not recalled

Decoded from this ROM's own text this session:

- **`BICYCLE` is item 6. `BIKE VOUCHER` is item 45.** Neither appears as an item ball on any map,
  so **both come from a person.** That is why this is a talking problem.
- The BIKE SHOP script reads: *"Hi! Welcome to our BIKE SHOP"* / *"It's a cool BIKE! Do you want
  it?"* / *"Sorry! You can't afford it!"* / *"Oh, that's A BIKE VOUCHER! OK! Here you go!"* /
  *" exchanged the BIKE VOUCHER for a BICYCLE"* / *"You better make room for this!"*
- **Money will not buy it.** The voucher is the only key.
- A sign block groups *"MON FAN CLUB — All MON fans welcome!"* with **VERMILION CITY**, VERMILION
  POLICE, VERMILION HARBOR and LT.SURGE.

## The two hypotheses to TEST — not conclusions to act on

**Where the voucher is: Vermilion, map 5.** Its warp (7,3) leads to map 163, the FISHING GURU who
gave us the OLD ROD — so map 5 is confirmed Vermilion by something we did ourselves. Buildings:

| warp on map 5 | building | size / tileset | non-item sprites |
|---|---|---|---|
| (9,13) | map **90** | 8x8 ts16 | **6** &larr; densest small room in the city |
| (23,13) | map 91 | 8x8 ts2 | 3 |
| (12,19) | map 92 | 10x18 ts7 | 5 |
| (23,13) | map 93 | 8x8 ts8 | 3 |
| (15,13) | map 196 | 8x8 ts8 | 1 |
| (11,3) | map 89 | 14x8 ts6 | 4 (Pokemon Center) |

**Where the shop is: Cerulean, map 3** — the shop text sits directly beside MISTY dialogue in the
ROM, and a Cerulean NPC at (9,27) says *"I want a bright red BICYCLE!"*. Buildings:

| warp on map 3 | building | size / tileset | non-item sprites |
|---|---|---|---|
| (9,9) and (9,11) | map **230** | 8x8 ts13 | 1 &larr; two entrances, one clerk |
| (30,19) | map 65 | 10x14 ts7 | 4 |
| (13,25) | map 66 | 8x8 ts21 | 3 |
| (25,25) | map 67 | 8x8 ts2 | 3 |
| (27,9)/(27,11) | map 62 | 8x8 ts8 | 2 |
| (13,15) | map 63 | 8x8 ts8 | 2 |

**Test them, in that order, and let the screen decide.** If map 90 is not the fan club, the next
body will say so. Record what each one says either way — a ruled-out building is a real result.

## The baton and the route

`data/local_runs/roster-bench/v8m10-3.state` — map **3 (Cerulean) at (14,35)**, badges
`0b00111111`, party healthy: Charizard L100, Dugtrio L100, Gloom L99, Primeape L99, Pidgeot L99,
Hypno L99. Route Cerulean to Vermilion: `3 -> 16 -> 10 -> 17 -> 5`.

**THE BAG IS FULL — 20/20.** The shop says *"You better make room for this!"*, and a full bag
**silently refuses gifts**, which is exactly why the SECRET HOUSE handed over nothing until a slot
was freed. Call `Rig.make_room()` (it tosses the largest stack, never a single key item) **before**
collecting the voucher and again before the bicycle. Verify with `Rig.bag_named()` after each.

## How to run it

    uv run python scripts/supervisor.py run --state <baton> --goal 5 \
        --budget 1800 --heal --engage --bank bike_vermilion \
        --live-label "bike — recon in Vermilion"

`LegRunner.recon` already talks to the bodies the cartridge lists before the first consult, and
what it hears reaches the seats under `HEARD:`. For a building sweep, drive `Rig` directly and
call `Rig.say(text, "discovery")` on everything you hear so it lands in the sink.

**Reading dialogue correctly matters here** — the window layer is **sticky** and will hand back
`'OPTION EXIT'` or the previous body's line if you trust it blindly. A text box **blocks
movement**, so gate every read:

    r.ctl.press(facing); r.ctl.press("a")
    talking = not r.probe_step()
    said = r.textbox() if talking else ""

Clear the box (press B) between bodies, or you will record one body's sentence three times — that
has already happened once in this repo's telemetry.

## Discipline

- **Never `pkill -f <pattern>` where the pattern is in your own command line.** It matches your own
  shell and kills your run; two legs died this way. The harness now blocks it. Kill by PID, or
  bracket the pattern (`supervisor[.]py`).
- Do not re-derive tile tables, diff RAM, or hunt ROM addresses. Five legs died that way.
- World facts come from `references/rom_truth.json`; query it, never `cat` it.
- Commit as you go. `uv run pytest` and `uv run ruff check .` before any commit touching
  `scripts/`; this repo requires **100% coverage**.

## Definition of done

1. **`BICYCLE` (item 6) is in the bag**, banked as `bicycle.state`. If you get only as far as the
   voucher, bank `voucher.state` — that is real progress.
2. `docs/learnings/bike-recon-<run_id>.md` listing **every building entered, every body spoken to,
   the map and coordinates, and what it said** — including the ones that turned out to be nothing.
3. If the bike is in hand, test the gate: walk `29 -> 28` and report what happens.
