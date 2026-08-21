# 2026-08-20 — Mt. Moon clear, local-only 5-hour batch: nobody exits, one model impeaches the map

The first multi-model run under the expedition loop (main @ 17b7031 + `bench/mtmoon2` mission/
seed base). Question: with the mountain reached and ROM truth in hand, can **local models alone**
— pi harness, full self-heal, supervisor loop, **no Claude anywhere** (escalation disabled) —
take a lane through Mt. Moon to Route 4's east side? Hard 5-hour ceiling, serial slots, reap
between models, **qwen38-27b last and alone** (its 600 W draw shares with nothing). Seed:
`mtmoon1f_entrance_hp42` — the 08-20 expedition's own baton (map 59 at (14,35), Charmeleon L17,
42/50 HP). The `mtmoon_clear` segment did not exist; building it was part of the mission.

**Result: no baton.** All three failed the traversal — and the most important output of the
batch is qwen38's finding that the map they were all navigating with was wrong (see below).
These are expedition-mode rows (`assist=all`): compare them with each other, never with the
unassisted tables.

## Scoreboard

| model | slot | attempts | furthest | wall (sessions) | model time | turns | s/turn | out tok/s | input | output | cloud $ eq | Wh* / energy $* | code commits | learnings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| laguna-xs (128k) | 70 m | 4 | **B1F — 8,247 events on map 60** | 81.0 m | 73.5 m | 1,438 | 3.1 | 123.6 | 85.8 M | 545 k | **$12.56** | 43.2 / $0.017 | **0** (uncommitted `mtmoon_clear` edit) | **0** |
| qwen3-coder-30b (128k) | 70 m | 6 | cave mouth — never descended a ladder | 22.1 m | 20.9 m | 272 | 4.6 | 59.1 | 7.6 M | 74 k | $1.14 | 16.2 / $0.006 | **0** | 1 (summary; unverified) |
| qwen38-27b (128k, alone) | 205 m | 3 | n/a — **ran zero relays by choice** | 199.2 m | 198.2 m | 302 | **39.4** | 54.8 | 17.6 M | 652 k | $3.12 | 643.7 / $0.251 | 1 (far-door probe tool) | 0 (worked to the buzzer, no summary) |

*Energy caveat: `power_sampler.py` is relaunched per attempt with the same `--out` path, so the
CSV holds only each model's **final attempt window** — these Wh figures are floors of floors.
Launcher fix (per-attempt CSV names) is queued. Guard: no Xid, no Ollama crash, load sane; the
chain ended by its own deadline (rc 124), as designed.

## What each model did with the same seed

**laguna-xs** was the only model to make real underground progress: lanes deep in B1F (map 60),
the furthest in-game position of the batch — and it wrote a `mtmoon_clear` segment into
`agent.py`. Then it committed **none of it**: zero commits, zero learnings, the segment edit
stranded uncommitted in the worktree. Its bench row explains why the README calls its failure
mode structural: 1,438 turns at 3.1 s/turn produced **85.8 M input tokens and 17 compactions**
in 81 minutes — the compaction-amnesia signature, third row in a row ($12.56 cloud-equivalent,
the most expensive nothing of the batch). ROM truth fixed its navigation; nothing yet fixes its
deliverable discipline. The uncommitted segment is preserved in
`../pokemon-kafka-speedrun-pi-exp-laguna-xs-mtmoon2` for salvage.

**qwen3-coder-30b** replayed its 08-16 character unchanged: never created the segment, never
went below 1F, and burned six attempts re-running the existing relay into the cave's west
entrance mats — the supervisor fingerprinted the `15<->59` spring at 492 bounces on attempt 1
and **4,262** by attempt 2, nudged it toward `rom_truth.py route` once (by design), then charged
it four wall-attempts. 22 minutes of model time across six sessions — fast bailouts, no
investigation. It did leave a clean-looking SPEEDRUN_SUMMARY; per the Brock-day rule its numbers
are not to be cited until checked against lane logs.

**qwen38-27b** never ran a relay in 3.3 hours — a choice, and probably the right one. Its first
leg audited the seeded worldmap against the live engine and found that **the ROM-truth collision
grid for Mt. Moon 1F is wrong in 842 of 1,440 cells**: the parser's 2×2-quad rule reads the
wrong corner tile for the cavern tileset (the overworld/gym tilesets it was validated on agree
by coincidence). Its second leg built and committed a text-box-aware far-door probe ("learned
live-walls, on-screen dialog on failure"); its third was mid-DFS, mapping B1F's ~25-cell pocket
and its ladders from the live engine, when the ceiling hit. Its ruling, verbatim: *"the live
engine is authoritative, not the reference file."* 39.4 s/turn of deep thinking, one commit,
no summary — the Investigator investigated the instruments instead of the mountain, and the
instruments deserved it.

## The finding that reframes the batch

Every model in this batch navigated caves with a **poisoned seeded map**: `rom_truth.json`'s
cavern grids mark ~58 % of 1F's cells wrongly. laguna's B1F wandering and coder's mat-bouncing
both happened on top of it; the mission's own briefing ("never probe for topology — look it up")
pointed at a reference that was wrong precisely here. The spec named this its #1 risk — *"a
wrong collision grid misroutes silently"* — and mitigated it by validating against learned
worldmaps, but the validation set (Pewter, the gym) never exercised the cavern tileset. It took
an operator distrusting its own briefing to catch it.

Fix path, in order: correct the quad rule in `rom_truth.py parse_map` against qwen38's measured
coordinates ((9,22) checks (8,23), not (10,23)); re-extract; re-validate against qwen38's live
probe data *and* the learned `mtmoon1f` worldmap from the cleared leg; add a cavern-tileset case
to `tests/test_rom_truth.py`; then re-seed and rerun this mission. The traversal is probably
cheap once the map is true.

## Loop machinery, this batch

| | laguna-xs | qwen3-coder | qwen38-27b |
|---|---|---|---|
| continuations used | 2/2 | 2/2 | 0 |
| wall attempts charged | 1 (no-fingerprint) | 4 (`15<->59`) | 2 (no-fingerprint) |
| spring fingerprints | none | `15<->59` ×4,262 | none |
| early exits | 3 | 5 | **0** |
| slot ended by | ceiling (124) | attempt cap (6) | deadline (124) |

Escalation never fired (disabled by design — no Claude models were invoked at any point). The
whole batch's **measured** electricity: $0.27 across the three final-attempt windows; even the
worst honest full-slot bound (5 h × 600 W) is under $1.20 at the new $0.39/kWh rate.

## Next

- **Fix the cavern collision rule** (above) — the single lever that probably unblocks the
  traversal for any capable model. qwen38's probe tool and measured coordinates are the spec.
- Salvage laguna's uncommitted `mtmoon_clear` segment as a starting point — data, not verdict.
- Launcher: per-attempt power CSVs so expedition energy is fully integrated, not last-window.
- Character table: laguna = Driver with structural deliverable-loss (3rd row); qwen3-coder =
  relay-spammer, unchanged (2nd row); qwen38 = Investigator to a fault — give it a mission that
  *is* the audit next time and it will excel on purpose.

Artifacts: worktrees `../pokemon-kafka-speedrun-pi-exp-{laguna-xs,qwen3-coder-30b,qwen38-27b}-mtmoon2`;
chain log `data/local_runs/mtmoon2-chain.log`; supervisor states `data/local_runs/exp-*-mtmoon2.supervisor.json`;
pi sessions under `~/.pi/agent/sessions/`; power CSVs in each worktree's `data/power/`; base
`bench/mtmoon2` @ d745c6d; seed manifest `demo-runs/states/mtmoon_seeds/MANIFEST.md`.
