# Mission: find the Warden — HM04 (Strength) is somewhere in the Safari Zone

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary. **Kept short on purpose.**

## Why

Seafoam Islands has boulders that answer *"This requires STRENGTH."* when bumped — confirmed live,
and confirmed structurally: all four share the exact same sprite graphic, appearing nowhere else
as any other body, meaning they're the same kind of object, not people. Pushing them past this
point needs Strength, which nobody has.

The cartridge's HM04 text names its giver **"the Warden"**, thanking us for something, in the same
line as a mention of the Safari Zone. **Every building in the real Safari Zone cluster — maps
221, 223, 224, 225 (map 222, the Secret House, is already done — that one gave HM03) — has NPCs
nobody has ever talked to, in this project's entire history.** One of them is likely the Warden.

## The job

1. Baton: `data/local_runs/roster-bench/loop219.state` — inside the Safari Zone (map 219), six
   badges. Gyarados is fainted; that's fine for talking indoors — Safari battles have no FIGHT
   option anyway (BALL / BAIT / THROW ROCK / RUN). Heal at Fuchsia's Center (map 154) first if it's
   convenient, but don't detour far for it.
2. Enter buildings **221, 223, 224, and 225** and `Rig.engage_bodies(("trainer", "npc"))` in each.
   Read every line in full.
3. **The moment anyone mentions HM04, STRENGTH, or being lost/thanking you for something, stop and
   read the whole exchange.** That's the Warden.
4. If none of the four buildings have him, say so plainly — that's a real result too.

## Discipline

- Screenshot anything that refuses to move you.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Commit as you go.

## Definition of done

`docs/learnings/warden-hunt-<run_id>.md`: what every NPC in all four buildings said, and whether
HM04 was found. If found, bank it as `strength_won.state`.
