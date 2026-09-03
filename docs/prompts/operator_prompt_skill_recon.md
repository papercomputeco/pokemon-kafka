# Skill mission: the recon leg — read the room before anyone reasons

You are an autonomous operator on this repo. Your goal: **observation**, not progress. Take the
baton into a map you have not surveyed and come back with what the game said. Print `date` at the
start and before any summary.

This is the RECON skill leg of a matrix. What is measured is **how much of the world you can make
speak**: bodies engaged, distinct sentences recorded, and whether any of them changes what the next
leg would do. Turns to a goal do not count here; a leg that walks nowhere and returns eleven
sentences beats one that crosses two maps in silence.

## Why this seat exists

Counted across two arcs of the same run, same engine, same ladder
(`benchmarks/2026-09-02-crew-vs-solo.md`):

| arc | bodies engaged | outcome |
|---|---|---|
| badge 6 | **82** across 8 maps | badge won |
| badge 7 | **0** across 6 maps | five legs lost |

Map 30's own exhaustion record listed ten live bodies and used them only as obstacles to route
around. The cartridge calls all ten `trainer`. The first time anyone spoke to one, it answered.

## What to do

1. **Engage every body the cartridge lists for the map** — `kind` of `npc` *and* `trainer`. Talking
   is not a lesser form of fighting: three ways of acquiring a story item are observed in this ROM,
   and one of them is an npc simply handing it over.
2. **Enter every building.** A ruled-out door is a real result — record it as one.
3. **Record every sentence** into the sink with `Rig.say(text, "discovery")`, with the map and the
   coordinates it was said at.
4. **Report what changed.** The deliverable is `docs/learnings/<leg>-recon-<run_id>.md`: every body
   spoken to, every door opened, and — separately — the one or two sentences that alter what the
   next leg should try.

## Reading dialogue correctly

The window layer is **sticky**: it keeps the last menu drawn, so a naive read returns `'OPTION
EXIT'` at every cell in every direction and you will record dialogue that never happened. A text
box **blocks movement**, which is the honest signal:

    r.ctl.press(facing); r.ctl.press("a")
    talking = not r.probe_step()
    said = r.textbox() if talking else ""

Clear the box (press B) between bodies, or one body's line gets recorded three times — that has
already happened in this repo's telemetry.

**A body with no walkable neighbour is not unreachable.** It may be behind a **counter**:
`road.counter_stands(body)` gives the cells two tiles away and the facing that talks across it.
That geometry was hard-coded for Pokémon Center nurses and ungeneralised until a leg stood in the
BIKE SHOP holding the voucher and reported the clerk unreachable — the clerk was fine, the
approach was not. The same shape gates the MART in every city.

## Discipline

- Cite measured coordinates, never theories. Read the refusal before reasoning about it.
- Do not re-derive tile tables, diff RAM, or hunt ROM addresses — five legs died that way. If a
  probe says *nothing works in any direction*, suspect the harness, not the cartridge.
- Never `pkill -f <pattern>` where the pattern appears in your own command line; it matches your
  own shell. Kill by PID, or bracket it (`supervisor[.]py`). The harness now blocks this.
- Commit as you go; an uncommitted diff is a lost diff.

## Definition of done

1. Every listed body on the map engaged, or a recorded reason why not.
2. The sentences are in `data/telemetry/game/<UTC-date>.jsonl` as `discovery` events.
3. `docs/learnings/<leg>-recon-<run_id>.md` exists and names what the next leg should try.
