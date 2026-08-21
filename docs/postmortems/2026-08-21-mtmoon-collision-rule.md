# The Mt. Moon Feedback Loop

Blameless postmortem — 2026-08-21, `bench/mtmoon2`, expedition
`speedrun/pi-exp-qwen38-27b-mtmoon2` (qwen38-27b, local).

## Summary

A benchmark expedition was asked to fix a bug that did not exist, and it succeeded. It replaced a
correct collision rule in `scripts/rom_truth.py` with an incorrect one, then used the corrupted map
to prove — rigorously, with live measurements, a new test, and a green suite at 100 % coverage —
that Mt. Moon cannot be cleared from the mission seed.

The mountain is clearable. The parser was right. The proof was careful work performed on a false
premise that the harness handed the model in its own prompt and never gave it a way to question.

**Impact.** About 6.5 hours of local GPU time across two legs produced no baton. A wrong conclusion
("nobody exited Mt. Moon because the map I gave them was wrong") was published on PR #100. A parser
regression sits quarantined on the expedition branch and must not be merged. Nothing outside the
benchmark repo was affected.

**Silver lining.** The run's measurements were sound. They were pointing at a real defect nobody had
modeled — tile-pair collisions — which is now fixed on `bench/mtmoon2`.

## What was actually true

**1. The parser's rule was correct.** `rom_truth.py` reads the bottom-left sub-tile of each 2×2 quad,
the canonical pokered convention. Test it against an invariant the engine cannot violate — every warp
destination must be standable, because the engine places the player there — across all 248 maps:

| rule | warp tiles standable | cavern maps only |
|---|---|---|
| bottom-left (original) | **801 / 816** | **4 / 4** |
| ≥3-of-4 (the "fix") | 256 / 816 | 0 / 4 |

**2. The real mechanism was missing from the model, not wrong in it.** pokered's
`TilePairCollisionsLand` refuses moves *between* two specific tiles even when both cells are
walkable. It is an **edge** property, so no walkable/solid grid can express it. Measured live on
Mt. Moon B2F, three separate columns refuse the step from row 11 to row 12 on a clean screen — all
of them the CAVERN pair `0x20 → 0x05` — while every accepted move in the same columns is not a pair.

The expedition saw edge refusals, inferred a broken node rule, and approximated an edge constraint by
deleting nodes. That is why the replacement also deleted 69 % of the game's warp tiles.

**3. The mountain is clearable.** `wLastMap` (read from `0xD365`) stays 15 through both cave ladders,
so the far door resolves to Route 4 `(24,5)` and exits east — the "circular door" argument is false.
A whole-cave search over `(map, x, y, wLastMap)` with node, pair and warp edges reaches the goal at
`15 (30,6)` having visited both deep floors, on one condition: the two sprites at `61 (12,6)/(13,6)`
are the **fossils**, and they occupy the only doorway to the northwest ladder. Take either one and
the route opens. That is a game action, not a map fact, and no collision rule of any kind would have
revealed it.

## Timeline (PDT, 2026-08-21)

| time | event |
|---|---|
| 02:10 | Operator asks whether the model can "fix the wedge in the cavern." |
| 02:11 | Fix-first mission launched. It opens by quoting the model's own earlier finding back to it as established fact: *"A prior session audited `rom_truth.json` and measured 842 of 1,440 cells wrong… your probe is the measuring instrument."* Job 1 is "fix the rule." |
| 03:28 | The rule is replaced (`810139d`). Suite green, coverage 100 %. |
| 04:17–04:29 | Sweep data and a cavern test case committed; cave topology re-derived on the new grid. |
| 06:33 | First "east exit impasse" evidence file. |
| 06:52–06:57 | Supervisor session drops (network, then an API error) and is resumed. The carried-forward summary states the collision fix as settled. |
| 06:56 | "Prove goal unreachable from seed" (`b0182f1`) — six candidate exits measured or parsed dead. |
| 07:00 | Second leg launched with the same mission text, the regression now in its worktree history. |
| 07:53 | "Engine-verified unreachable verdict" (`61df13d`). |
| ~07:58 | Attempt cap reached, no baton. The model declines to write one, correctly: *"a baton by definition is a goal state, and this one isn't."* |
| 08:0x → | Supervision handed to a fresh session. The audit starts with the warp-tile invariant and ends at the tile-pair table. |

## Contributing factors

**The premise arrived as fact.** The mission's first paragraph asserted the 842-cell finding as
settled and named Job 1 as "fix the rule." Nothing in the prompt marked it as a hypothesis, and
"the premise is false" was not among the deliverables. A model that complied was doing its job.
(The 842 figure itself counted 1,282 cells the sweep marked `unreachable` — never measured at all.)

**Validation was circular, and a cheap non-circular check existed.** The parser's original
validation compared grids against worldmaps that had been seeded from those same grids. The
expedition caught this itself. But the harness offered no independent oracle to replace it, and the
obvious one — warp destinations must be standable — was never encoded, though it takes about
twenty lines and would have rejected the new rule instantly.

**The designated measuring instrument was uncalibrated.** The mission named the model's own probe as
ground truth. That probe's `step()` counts "position did not change" as a wall, and after a fled wild
battle the *"Got away safely!"* box eats the next d-pad press — so the walker records real corridors
as walls and slowly bricks its own map. It marked all of B2F row 12 solid this way. Some of the
"live wall" evidence in the impossibility proof is that bug.

**The continuation nudge forbade re-checking.** When a leg exited early, the auto-supervisor
re-entered it with *"Continue from where you stopped; do not re-verify what is already committed."*
Committed, at that point, included the regression.

**Compaction launders hypotheses into findings.** Across a crash, a resume, and a summarization, the
sentence "the model believes the grid is wrong" became "the grid is wrong." Nothing marked the
provenance, so nothing survived to be doubted.

**No domain smoke test.** A benchmark that asks a model to clear Mt. Moon never asserted that
Mt. Moon is clearable. That single check would have flagged the regression within seconds.

**We asked for rigor, and rigor is not doubt.** The model-fit notes told this model its weakness was
declaring things unreachable too early, so it responded with far more rigor: more probes, more
evidence files, a six-bridge impossibility proof. The harness asked "are you sure?" when it needed
to ask "is the question right?" Rigor applied to a false premise produces a better-defended wrong
answer.

## What went well

- The model **caught the circular validation itself** and said so plainly — a genuinely sharp
  observation about our methodology, not its own task.
- It built the repo's **first unbiased live dataset** (a 158-cell sweep of map 59), which is what
  later made the real diagnosis possible.
- It **refused to write a misleading baton**, reasoning that a baton is by definition a goal state
  and a false one would poison the next relay. That was the right call under its beliefs.
- It **wrote obstacle files as it went**, so the reasoning was auditable after the fact. This
  postmortem is only possible because it did.
- Its measurements were correct. Only the interpretation was wrong — and the interpretation was the
  one the prompt supplied.

## The same trap caught the supervisor

While auditing, the takeover session asserted that the route was "open end-to-end" on the strength of
a static grid, before live-walking B2F — and had to retract when the engine refused row 12. Identical
failure mode, opposite direction, about ten minutes of unearned confidence. That is evidence the trap
is structural rather than individual: whoever holds the map trusts the map.

## Already landed on `bench/mtmoon2`

- `73c6a68` — `rom_truth.py` models tile-pair collisions: `tile_pairs()`, `passable()`, per-cell
  `tiles` in the extract, a test pinned to the live-measured coordinates, re-extracted
  `rom_truth.json`. Suite green (1521 passed), ruff clean.
- `5653cd1`, `d90c0fc` — the audit, with the measurements behind every claim.
- **Known gap:** `WorldMap` / `seed-worldmap` are node-only and cannot carry edge constraints, so an
  A* over a seeded worldmap can still plan a route through a pair-blocked lip.

## Action items

### Harness

1. **Encode the oracles in CI.** Warp-tile standability across all maps, and a canonical Mt. Moon
   route smoke test. Any change to a collision rule that breaks either fails the build.
2. **Calibrate an instrument before designating it.** A probe named as ground truth in a mission
   should have to pass a self-test first (known-open and known-solid cells, with text on screen).
3. **Fix `mtmoon_probe.step()` upstream.** "No movement while a text box is up" is a retry, not a
   wall; only a refusal on a clean screen counts.
4. **Change the continuation nudge.** Replace "do not re-verify what is already committed" with
   "re-verify anything a conclusion depends on."
5. **Gate model changes to shared references.** A commit that alters how the world is *modeled* needs
   a human check; keep measurement commits and model-change commits separate so one can land without
   the other.

### Human instruction — how we write missions

6. **Label every claim with provenance and status:** measured, inferred, or unverified. Never restate
   a model's own prior conclusion back to it as established fact; that closes the loop we just
   watched run.
7. **Make "the premise is false" a first-class deliverable,** named in the prompt with an example of
   what that answer looks like and what evidence it needs.
8. **State the invariant the fix must preserve,** not only the symptom to fix. "Keep the overworld at
   100 %" was in the prompt; "every warp tile must remain standable" was the one that mattered.
9. **When asking for a fix, ask first for a falsification test of the bug.** One cheap step —
   "before changing the rule, show me a measurement the current rule gets wrong that no other
   mechanism explains" — would have ended this in the first ten minutes.

## In one line

The model did what we asked. The harness never gave it a way to ask whether we were right.
