# Mission: Gold Teeth → the Warden → HM04 Strength

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary. **Kept short on purpose — this is now a two-step job, not a search.**

## The full quest, from the cartridge's own text

> *"REQUEST NOTICE: Please find the SAFARI WARDEN's lost GOLD TEETH! They're around here
> somewhere! Reward offered! Contact: WARDEN."* ... *gave the GOLD TEETH to the WARDEN! The
> WARDEN popped in his teeth!* ... *"Thanks, kid! No one could understand a word that I said!"*
> → **received HM04, teaches STRENGTH.**

Both pieces are now located:

1. **GOLD TEETH is an item ball at map 219, (19,7)** — inside the Safari Zone, ground we've
   walked past before without picking it up.
2. **The Warden is one of two staff NPCs in map 156** — the Safari Zone's own gate/reception
   building (entered from Fuchsia's map 156 warps toward 220). Neither has ever been talked to.

## The job

1. Baton: `data/local_runs/roster-bench/loop219.state` — inside the Safari Zone (map 219), six
   badges, bag full (20/20) — `Rig.make_room()` first.
2. Walk to (19,7) on map 219 and pick up the GOLD TEETH item ball.
3. Head to map 156 and `Rig.engage_bodies(("npc",))` — talk to both staff NPCs. One of them is the
   Warden; giving him the teeth should trigger automatically once you're holding them and talk.
4. **Confirm HM04 is actually in the bag afterward** — don't just trust the dialogue, check
   `Rig.bag_named()`.

## Discipline

- Screenshot anything that refuses to move you.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Commit as you go.
- **If you conclude you're blocked by something outside this repo, show the command output
  proving it in the same report.** An unverified claim will not be trusted.

## Definition of done

`docs/learnings/gold-teeth-<run_id>.md`: confirm HM04 is in the bag, bank it as
`strength_won.state`. If either the item or the Warden isn't where this says, report exactly
what you found instead.
