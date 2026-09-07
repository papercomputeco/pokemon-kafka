# The Forger's first live arc — 2026-09-07

The trained Forger adapter (`pokemon-forger:Q4_K_M`, PR #144) took its seat and rode a replay arc:
two engage legs from `lab_revived` (map 170) into Cinnabar Island (map 7) and Route 20 (map 31),
`data/replay_arcs/forward_lane.sh 30 7 31`, rows in `forward_lane30.jsonl`, runs
`20260907-182710-4f98` and `20260907-182822-c3b9`. Recorded, not obeyed: every engaged body's sentence
went to the adapter as the training prompt, and the reading landed in `supervisor.forger_read` beside
the engine's own label.

## Measured

| | |
|---|---|
| legs / arrived | 2 / 2 (73 s and 2 s; both `engaged-no-badge`, the expected end of `--engage` on a town) |
| bodies read | 9, all parsed as JSON |
| latency | mean 0.28 s, max 1.02 s (the first call, cold) |
| body agrees with the cartridge's sprite kind | 9 / 9 |
| outcome agrees with the hook's label | 4 / 9 |

## The five disagreements are the hook's, not the adapter's

The hook labels a hand-over `handed` and everything else `talk`; it does not see the battle rows the
corpus builder uses. All five disagreements fall on that gap:

- **3 × `fought-won`** where the engine said `talk`: "I rode my bird POKéMON here!" at 31 (34,9) and
  "AAAAAAAAAA gained 410 EXP. Points!" at 162 (9,14) and (8,14). A fight happened; the adapter read it
  off the sentence. The corpus rule would label these the same way.
- **2 × `stale`** where the engine said `talk`: the SAFARI ZONE sentence read again at 7 (29,17) one
  cell after the body at (28,17) said it, and "there is really a POKéMON." at 7 (13,12). Both are the
  window's leftover text, which the corpus labels `stale` and the catalog does not count as heard.

So on this arc the adapter's outcome head was right wherever it could be checked, and the engine label
it was scored against is the thing to fix: `forger_read` should take the fight window and the stale
sentence set into account before agreement means anything. Until then read `agree.outcome` as
"agrees with the naive label", not as accuracy.

## What it costs

Nine reads added under three seconds to a 75 s arc. The adapter answers in one line and never
needs the closing call the thinking seats need.

## Next

1. Give `forger_read` the corpus builder's outcome rule (fight within 5 s → fought-*, repeated
   sentence → stale) so live agreement is a real number.
2. Run the same arc on a gate-heavy leg (Route 20 west → Seafoam, Cycling Road) so the gate-text head
   is read live; this arc printed no refusal sentence.
3. Only after both: let a `stale` reading stop the catalog counting the body as heard, the first
   place a reading would change what the loop does.
