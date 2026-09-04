# Investigation: ask the swimmers how you cross this water

You are the Investigator. Use `uv run ...` for all Python (AGENTS.md). Print `date` at the start
and before any summary. **The product is sentences the game said, with the map and coordinates.**

Two legs have now concluded that badges 7 and 8 are unreachable because map 31's water is split by
a solid row. The collision measurement supports them. **But nobody has asked the people standing in
that water.** Map 31 is full of SWIMMER trainers — we fought one this session — and the cartridge
gives them lines that read like directions, not flavour.

## What the cartridge already says — verify it on screen, do not take my word

Decoded from this ROM's own text this session:

- **"HM03 is SURF! POKéMON will be able to ferry you across water!"**
- **"Now that you have the SOULBADGE, ... It also lets you SURF outside of battle!"** — we hold
  six badges, so that condition is satisfied. If a body tells you otherwise, that is a finding.
- The refusal we keep meeting: **"No SURFing on <mon> here!"**
- And from the swimmers themselves:
  - *"Why are you riding a POKéMON? Can't you swim?"*
  - *"I see a couple of islands!"* / *"What's beyond the horizon?"*
  - *"My boy friend wanted to swim to SEAFOAM ISLANDS."* / *"These waters are treacherous!"*
  - *"You have to fish for sea POKéMON!"* / *"Watch out for TENTACOOL!"*
  - *"I rode my bird POKéMON here!"* / *"My birds can't FLY me back!"*

**Islands, a horizon, and a named destination we have never visited.** That is the question this
leg exists to answer: *is there somewhere out there we have not tried to reach?*

## The job

**Baton:** `data/local_runs/roster-bench/b7_first_probe31.state` — map 30 at (4,9), six badges,
Gyarados L20 with SURF (`knows_move("SURF")` finds it), five L99/L100 heavies. Keep Gyarados **off
the lead and awake**: a fainted surfer is unusable because Gen 1 omits fainted members from the
POKéMON menu.

1. **Get on the water and stay on it.** `_arm_surf()` now judges by position and turns to face
   water first, so a `True` means you moved.
2. **Talk to every SWIMMER and every body you can reach on maps 30 and 31.** They are trainers, so
   most will fight first — fight them (your party outclasses them by ~80 levels) and **talk again
   afterwards**, because the post-battle line is usually the informative one. That is how
   "They need to learn better moves" was recorded earlier this run.
3. **Record every distinct sentence** with `Rig.say(text, "discovery")`. `Rig.say` now de-dups per
   (map, kind, text), so say freely — repeats cost nothing and the sink stays minable.
4. **Ask specifically what the water allows.** If a body mentions islands, a horizon, SEAFOAM, a
   ferry, fishing, or somewhere you cannot see, **write the coordinates down and try to go there.**

## Reading dialogue correctly

- The window layer is **sticky**: a naive read returns `'OPTION EXIT'` or the previous line. A text
  box blocks movement, so gate every read: `talking = not r.probe_step()`. Press B between bodies.
- **A body with no walkable neighbour is not unreachable** — `road.counter_stands(body)` talks
  across a counter. That is how every mart in the game opened.
- `LegRunner.recon` talks to the bodies the cartridge lists before the first consult, and the
  Investigator seat picks which body is worth the budget when there are more than you can ask.

## What is already measured — do not re-derive it

- **`0x3a` is NOT surfable.** Measured live, four attempts, all refused; `0x14` is surfable (64
  landings). Row 1 of map 31 is 100 unbroken `0x3a` cells. The engine's `WATER_TILES = {0x11,
  0x14}` is correct.
- Under that model map 31's water is two components; the one you land in spans x 0..61 and does not
  touch the east edge. **That is why this is a talking problem now, not a routing one.**
- Do not diff RAM, hunt ROM addresses, or re-derive tile tables. Five legs died that way.
- **Never `pkill -f <pattern>` matching your own command line** — two legs killed themselves that
  way; the harness blocks it now. Kill by PID.

## Definition of done

`docs/learnings/swimmers-<run_id>.md` containing:

1. **Every sentence heard on maps 30 and 31**, with map and coordinates, before and after battle.
2. **Anything that names a place** — islands, SEAFOAM, a ferry, a horizon — and whether you could
   reach it.
3. A plain answer to: **according to the people in this water, how is it crossed?**

If every swimmer only talks about sunburn, say so. A documented "they know nothing" closes the
question honestly and is worth more than another routing verdict.
