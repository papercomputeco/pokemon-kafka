# The water arc talked to nobody, and the game had two different answers (2026-09-02)

Operator's observation, and it was correct: the badge-7 legs were reading failure codes instead
of the screen. Counted across the whole run:

    engagements by map: {178: 25, 210: 15, 212: 3, 213: 3, 182: 3, 207: 3, 208: 3, 234: 1}
    map 7 (Fuchsia): 0   map 30: 0   map 31: 0   map 8 (Cinnabar): 0   map 166 (gym): 0

Every one of the 76 recorded conversations belongs to the badge-6 Silph/Saffron arc. **Four legs
crossed the sea route and engaged no one.** Map 30's own stuck doc listed ten live bodies and used
them only as obstacles to route around — the ROM's sprite list calls all ten `trainer`.

## The game distinguishes two refusals, and they are different problems

Now that `_arm_surf` records what it heard, the sink separates them:

    map 30  discovery  surf.refused  "No SURFing on GYARADOS here!"
    map 30  discovery  surf.refused  "There's no place to get off!"
    map 31  discovery  surf.refused  "There's no place to get off!"
    map 31  discovery  surf.refused  "No SURFing on GYARADOS here!"

Measured association, not a claim about the engine's internals: the first appears when standing
and facing a tile that will not accept a launch; the second appears when already out on the water.
Treating them as one "refused" is how a leg concludes it is boxed in — they need different
responses, and the failure code the old path returned could not tell them apart.

## Corrections to earlier records in this repo

- **The island is 43 cells, not six.** `docs/learnings/surf-is-armed-and-the-water-is-not-a-tile-id.md`
  says "on map 30 it is six cells, (6,4)..(11,4)". Measured from (6,9) on
  `b8_BATON_island_gyarados_safe.state`, the body-aware region spans x 4-13, y 0-9 — 43 cells.
  The six-cell figure came from a different state and was probably taken while the frozen-world
  bug was swallowing input. **Do not plan from it.**
- Two of those trainers, **(8,7) and (13,7)**, are adjacent to walkable cells and therefore
  reachable. Talking to (13,7) from (13,8) facing up returned the first sentence this arc has ever
  heard from the sea route — **"Wait! You'll have a heart attack!"** — and opened a battle. With an
  L99/L100 party those trainers are free; they were never obstacles.

## How to tell dialogue from stale pixels

The window layer is **sticky**: `Rig.textbox()` will happily return `'OPTION EXIT'` — the START
menu's bottom rows, left over from the last menu drawn — when nothing is being said at all. A
probe that trusts text alone reports a sentence at every cell in every direction, which is what
the first observation sweep did.

The reliable predicate is the one that found the frozen-world bug: **a text box blocks movement.**
`probe_step()` is False exactly while the game is talking. Gate the read on it:

    r.ctl.press(facing); r.ctl.press("a")
    talking = not r.probe_step()
    said = r.textbox() if talking else ""

## The west edge does not launch

From the island's west edge (x=4, cells (4,6)..(4,9)), facing west, `_arm_surf` is False at all
four cells — and now that is trustworthy rather than the lie it used to be. Map 30 connects
`west -> 31`, so the launch point is somewhere other than the nearest edge cell. That is the
open question, and it is a navigation question with an honest signal behind it at last.
