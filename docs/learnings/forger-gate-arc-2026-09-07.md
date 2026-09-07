# The Forger's second arc, after the label fix — 2026-09-07

Two "gate-heavy" lanes with the Forger seated and the hook labelling the way the corpus does (PR #146):
lane 31 from `fly_won-27` (Route 16 sleeper → gate house 186 → Cycling Road 28) and lane 32 from
`lab_revived` (the sailed ship's map 95 → Cinnabar 8). Rows `forward_lane31.jsonl`, `forward_lane32.jsonl`;
runs `…-67ec`, `…-f138`, `…-fb78`, `…-83bb`, `…-8d53`.

## Measured

| | |
|---|---|
| legs / arrived | 5 / 3 (27, 186, 8 arrived; 28 spent its budget; 95 was killed by the outer 1300 s timeout) |
| bodies read | 25, all parsed; mean 0.41 s, max 1.45 s |
| body agrees with the cartridge | 21 / 25 |
| outcome agrees with the corpus-rule label | 15 / 25 (was 4 / 9 against the naive label) |
| gate class agrees | 25 / 25 (three `sleeping_blocker`, 22 none) |
| gate-text reads | **0** |

## What the disagreements are now

- **Trainers read as npc/talk (4).** Route 21's "I beat. I guess I'll FLY" (twice) and two Route 18 pre-battle
  lines. The cartridge lists them as trainers and a fight closed inside the window; the adapter read the
  sentence as an npc chatting. These are the adapter's misses, the kind the outcome head's 0.66 predicts.
- **Stale vs talk on Cinnabar (6).** The engine's stale rule counts cells of one run; the adapter reads one
  sentence at a time. They flip in both directions (the adapter says stale at the second cell, the engine
  at the third) and neither is wrong about the world: the window's leftover text is being read at cells
  where no body stands. The catalog already discounts these; the label rule and the adapter disagree only
  about *when* a repeat becomes stale.
- **The sleeper after the flute (1).** Sentence "A sleeping POKéMON blocks the way", fight closed 2 s
  earlier: the corpus precedence says `fought-won`, the adapter says `gate`. Both are true; the rule picks
  the fight.

So the outcome number is now a real one, and the four trainer misses are the thing more rows of
`fought-*` would teach.

## The gate-text head is still unexercised

Not one `supervisor.gate_text` event in five legs. The refusal-sentence hook fires on the probe-step path
(a step the walk refused, with text on screen). The sleeper is met through the blocker path, so its
sentence is a dialogue read; the pedestrians guard was never reached; the dock was never reached. To hear a
gate live the leg has to *walk into* it: the ship dock from a Vermilion baton, map 15's "No SURFing" cell,
a badge-gate guard.

## Two lane mistakes, mine

- `fly_won-27` holds the POKe FLUTE and no BICYCLE (bag read from the `fwd_l31_186` bank). Cycling Road
  cannot be ridden from it; the leg correctly found 27→28 unreachable from its region and spent four
  attempts on the 186→27 mat. The right baton is `bicycle` (map 66) or `r16_bike-28`.
- The ship leg routed overland from Cinnabar toward Vermilion and its consults ran past the budget; the
  outer timeout killed it before the JSON report (`exit 124`, `no-json`). The budget is checked between
  hops, not inside a consult (known since the first sweep).

## Next

1. A walk-into-the-gate arc: `at_gym_v` → 95 (the dock prints "The ship set sail."), a badge-gate guard, and
   map 15 (16,15) facing the pond.
2. More `fought-*` dialogue rows for the adapter: replay trainer-dense routes with the Forger reading.
3. Then the first vote: a `stale` reading keeps a body out of the heard catalog.
