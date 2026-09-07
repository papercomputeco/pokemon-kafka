# The v6 Forger meets a refusal it barely knows — 2026-09-07 late

Lane 36 from `cinnabar` (map 8, 6 badges, no SECRET KEY) at the locked gym door, with the v6 adapter seated
(`pokemon-forger:Q4_K_M`, rebuilt from the v6 merge). Run in `forward_lane36.jsonl`; log `logs/fwd_l36_166.log`.

## Measured

- The door at 8 (18,4) refused each attempt and printed "The door is locked...". The engine's class table has no class
  for it; the corpus holds it as two `unclassified` rows.
- The seated adapter read the refusal **3 times** and answered `gate: unclassified` **3 times**, each with
  the full clears text ("not measured yet: this sentence is not a known gate; talk to the body facing the step, read
  its whole sentence, and record what clears it before acting on a guess"), complete JSON, no digit runaway, no
  salvage needed. 2 dialogue reads on the way.
- Compare lane 33 the same morning: on a sentence no row covered, the v5 adapter named its nearest class and ran away
  into "9999 9999" until the token cap, eight times out of eight.

So the reflex taught by eight capped rows is what the seat now does when the sentence is not one it knows: say so and
send the crew to measure. That is the "does it give up on a new NPC" question answered on the gate side: it does not
give up and it no longer guesses.

## What this arc did not show

- A refusal sentence absent from the corpus entirely. Every true refusal in the sink is now a training row (this one
  as `unclassified`), so the next genuinely new gate will be met in play, not staged.
- Lanes 34 and 35 earlier produced no gate read at all: the Route 16 save's route to Cinnabar walled on Route 25, and
  at Vermilion's dock the walk capped short of the pier cell, so `read_refusal` had no step to press. The dock
  sentence ("The ship set sail.") was even read as a *body's* words at 5 (19,7). Refusals that print only on one cell
  need the read to step onto that cell; an engine follow-up.

## Next

1. Let the `unclassified` reading do something: hand the sentence to the Investigator's recon as the first body to ask,
   and record the measured clear as a new class when a leg finds it.
2. Step onto the refusing cell in `read_refusal` when the walk caps short of a warp.
3. The stale vote; the Yellow lane.
