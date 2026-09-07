# The Forger's third arc: walking into a gate — 2026-09-07

Lane 33 from `at_gym_v` (Vermilion, 2 badges, the S.S. Anne still docked): 95 (the ship) → 19 → 3 → 186.
Rows `forward_lane33.jsonl`; runs `…-c242`, `…-721c`, `…-07a0`, `…-767c`. The point was to make the walk
*step into* a refusal so the gate-text head is read live for the first time. It was.

## Measured

| | |
|---|---|
| legs / arrived | 4 / 2 (ship boarded and engaged; map 3 engaged; 19 exhausted the ladder at the gate; 186 gave up behind the same gate) |
| reads | 35: 27 npc-dialogue, 8 gate-text; mean 0.29 s |
| npc body / outcome / gate class | 27/27, 15/27, 27/27 |
| gate-text parsed | **0 / 8** |

Every npc outcome disagreement (12) is stale-vs-talk timing on the ship's waiter and map 3's townsfolk: the
window's leftover sentence read at the next cells, with the engine counting cells of the run and the adapter
reading one sentence. No trainer misses this arc.

## The gate-text head, read live for the first time

All eight refusals were one sentence, the Saffron-side gate guard on maps 70 and 73: "I on guard duty. Gee,
I thi…" (the window cuts it there). It is in neither the engine's class table nor the corpus's 82 gate rows.
The adapter's reply, re-asked verbatim after the arc:

```
{"gate": "script_guard", "clears_with": "a story gate, not a trainer or item: the dialogue from the
guard … says 'I on guard duty. Gee, I think I heard a kid come in... 9999 9999 9999 9999 …
```

It named its nearest class in the first tokens, then ran away into "9999 9999" inside `clears_with` and hit
the 160-token cap with the object unclosed. Eight reads, eight non-readings, and the one field that mattered
was there every time. Two things follow:

1. **`parse_forger` salvages a truncated reply** (this PR): the completed string fields (`gate`, `body`,
   `outcome`) become a reading marked `"partial": true` instead of nothing. The runaway is dropped, the name
   is kept, `agree.gate` is scored.
2. **The class itself is a data gap, not a modelling one.** The guard's sentence is measured; what clears
   it is not (this run never found out), so no class is added to `GATE_CLASSES` yet — a class needs a
   measured clear, never a recalled one. When a leg clears that gate, the sentence, the class and the
   verb go into the table and the corpus together.

The "9999" runaway is the Q4_K_M copy's behaviour on an out-of-distribution refusal; the bf16 gate scored
8/8 on sentences whose class it had seen. Free-text fields (`clears_with`) are where a small quantized model
degenerates first; a categorical field asked alone would not.

## Catalog note

The ship's six bodies and map 3's fourteen were engaged again from a 2-badge baton; the Forger agreed with
the cartridge on every body kind. `engaged-no-badge` is the expected end of `--engage` on a non-gym map.

## Next

1. Ask the gate question in two turns when the reply truncates: class first (categorical), clear second.
2. Clear the Saffron gate on a later baton, measure the sentence's clear, add the class.
3. The first vote: a `stale` reading keeps a body out of the heard catalog.
