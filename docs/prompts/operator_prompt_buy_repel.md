# Mission: buy Repel at Fuchsia's own mart

You are the Investigator. Use `uv run ...` for all Python. Print `date` at the start and before
any summary. **Kept short on purpose.**

## Why

The sea crossing to Cinnabar isn't blocked by a wall — it's blocked by constant wild battles. We
one-shot every fight already (L99/L100 party), but each one still costs real turns: menu, move,
animation, text. 200 straight actions on the water moved the player one tile because most of the
budget went to fights, not walking. Repel stops random encounters for a set number of steps. We
have never once bought or used one, and we have ₽92,360+.

## The job

1. Baton: `data/local_runs/roster-bench/b8_BATON_island_gyarados_safe.state` — map 30 at (6,9),
   six badges, one hop from Fuchsia.
2. Bag is 20/20 full — `Rig.make_room()` before anything.
3. Walk to Fuchsia (map 7), enter the mart at warp (5,13) → **map 152**, clerk at (0,5) — talk to
   it **across the counter** from (2,5) facing left, the same way every mart works
   (`road.counter_stands`).
4. **Buy as many Repels (or Max Repels, whichever is offered) as the bag can hold.** Read the shop
   menu; don't guess the item name.
5. Bank the result. This leg's job ends here — actually redoing the sea crossing with Repel active
   is separate follow-up work, not this mission.

## Discipline

- Screenshot anything that refuses to move you.
- Never `pkill -f <pattern>` matching your own command line. Kill by PID.
- Commit as you go.

## Definition of done

`docs/learnings/buy-repel-<run_id>.md`: what the mart actually sold, what you bought, and the
final bag contents. Bank the state as `repel_bought.state`.
