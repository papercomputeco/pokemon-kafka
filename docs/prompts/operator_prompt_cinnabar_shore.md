# Mission: walk to Cinnabar's shore — a wall is not always a wall

You are the Investigator. Use `uv run ...` for all Python (AGENTS.md). Print `date` at the start
and before any summary. **Read this whole file before touching the emulator.**

## What today taught, in plain terms

Two earlier attempts today called this water "sealed" — a solid wall with no way through. Both
were wrong, and both were wrong the same way: each one looked at wherever it happened to land,
found it blocked, and generalized from one spot. **A screenshot proved it.** What looked like a
wall of rock in the collision data was, on screen, a boulder poking up out of open water — you go
around it, not through it. What looked like a second wall right after was a narrow patch of sand
between more boulders.

**The lesson: when something refuses, look at the actual screen before deciding it's a wall.**
Attached to this mission are four real screenshots from today — the "wall," what's just past it,
and where the crossing is currently stuck. Look at them. This water is a field of scattered
boulders, not a corridor and not a solid barrier. It has to be threaded, not pushed through.

## The job

**Baton:** `data/local_runs/roster-bench/m31_manual.state` — map 31 (the sea route between
Fuchsia and Cinnabar) at (44,12), six badges, full-HP party: Charizard L100, Dugtrio L100,
Primeape L99, Pidgeot L99, Hypno L99, Gyarados L20 (the only surfer — `knows_move("SURF")` finds
it at party index 5, keep it off the lead and awake).

**Get to Cinnabar's shore (map 8) and bank it.** The map data says the water connected to this
exact spot reaches Cinnabar's edge, both entrances to Seafoam Islands, and a wide stretch of the
sea besides — nothing in the data says you're boxed in. Treat that as encouraging, not certain:
it's a claim from the collision model, and the model has been wrong before today. **Only your own
steps prove it.**

## How to actually get through a boulder field

- **Try all four directions from wherever you stop, not just the one that failed.** A boulder
  blocks one heading and nothing else; the earlier scripts kept retrying the same direction and
  calling that "stuck."
- **After a fight, check the screen before moving again.** A leftover text box (an EXP message, a
  level-up) freezes movement, and it looks identical to a real wall unless you read it. Clear it,
  then try the step again — don't count that as a refusal.
- **If SURF stops working mid-crossing, look at what's actually happening before re-arming it.**
  Today's scripts tried to re-arm SURF automatically and it sometimes opened a menu that didn't
  close, which then blocked everything after it looked identical to being stuck. Check the screen.
- **Take a screenshot at every point you stop for more than a few tries**, and look at it before
  deciding what kind of stuck it is — boulder, body, leftover text, or a real edge.

## Seafoam Islands may not be a detour — check it on the way

A sign on this exact water reads **"SEA ROUTE 19: FUCHSIA CITY - SEAFOAM ISLANDS"**. That is this
sea's real name, and it names Seafoam, not Cinnabar. There are two doors into Seafoam Islands on
this map (they lead to map 192, a cave-style interior). **If you pass near either one, go in and
look around before continuing past it.** It may sit on the direct line to Cinnabar rather than off
to the side, and nobody has ever set foot in it to find out. Screenshot whatever you find.

## Two side questions worth a cheap check, not a detour

- **Is there anything to interact with on these boulders?** Walk up to one and press A. Measured
  today: nothing on this map is listed as a pushable object, only trainers — so this is probably
  "no," but nobody has actually pressed the button on one. Record the answer either way.
- **HM04 (Strength) is not needed to reach the shore** — the boulders here aren't the kind you can
  move, and the map data says a way through exists without it. Don't go chasing Strength for this
  leg; it's a different errand for a different day if it turns out to matter later.

## Discipline

- **Never `pkill -f <pattern>` matching your own command line** — the harness blocks it now, but
  don't test that. Kill by PID.
- Talk to bodies on the way; the arc that talks wins its badges.
- Commit as you go. `uv run pytest` and `uv run ruff check .` before touching `scripts/`; 100%
  coverage is required.

## Definition of done

1. **A screenshot of Cinnabar's shore**, or a screenshot of wherever you actually stopped and
   could not pass, with a plain description of what's in it.
2. `docs/learnings/cinnabar-shore-<run_id>.md` — what worked, what didn't, and the coordinates of
   anywhere that turned out to be a genuine dead end (not just the current attempt's failure).
3. If you reach Cinnabar: keep going to the gym door (map 8, warp at (18,3) -> map 166, Blaine)
   and report what it says.
