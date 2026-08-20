# Expedition mode — long-running sessions with a learning loop that converges

Status: spec (2026-08-20). Owner: bdougie. Prior art: every dated file in `benchmarks/`.

## The problem, from measured evidence

The goal is sessions that run for days and *compound*. The current system has three loops, and
the benchmarks say only one of them converges:

| loop | evidence | verdict |
|---|---|---|
| genome subloop (`--sideloop-every`) | ~2,000 applied patches across 4 runs (239 Brock, 1,258 mixed day, 664+140 qwen-vs-sonnet), **zero attributable outcome changes** | does not converge — every wall so far was code, not a knob |
| within-run hypothesis loop | Sonnet fixes #5–#9: one theory family, five variants, all 0 wins; 6 early exits across 3 models | orbits a wall family; nothing forces a strategy switch or continuation |
| cross-run loop (run → learnings → merge → rerun) | every wall that ever fell (parcel gate, Brock, gym door) fell to this | **converges — but a human is the loop body** |

Removing the 2 h budget without changing anything else buys more orbiting, not more progress.
Expedition mode automates the loop that works and adds the three missing pieces.

**Non-goals:** expedition rows never enter the model-vs-model benchmark tables (they are
maximally assisted by construction); no change to how unassisted bench rows are produced; no
OpenRouter/stereOS (per standing scope).

## Component 1 — ROM truth: stop searching for what's knowable

The largest measured waste is models re-deriving world facts by collision: "gym sealed" (wrong),
"Route 3 is a pocket; map 59 unreachable" (wrong), "true Brock position unknown without ROM
data" (it was (5,1)). Warp tables, map connections, collision grids, and trainer coordinates are
deterministic data in `rom/pokemon_red.gb`; the pret/pokered disassembly documents every offset.

- **`scripts/rom_truth.py extract`** → `references/rom_truth.json`: per map id — dimensions,
  warp table (x, y, dest map, dest warp), the four edge connections, walkable-tile grid,
  trainer/sprite coords and facing. One-time extraction, committed, versioned by ROM hash.
- **`scripts/rom_truth.py route A B`**: static A* over the extracted world graph → the full
  warp/edge chain from map A to map B. This makes "is 59 reachable from 2, and how" a lookup.
- Agent integration: `WorldMap` seeds from `rom_truth.json` when present (optimistic-unknown
  becomes known-truth); `_mtmoon_action`-style legs read the static table instead of live-only
  `wWarps`. Live reads stay as verification, not discovery.
- Mission integration: expedition missions include the routed chain for the leg ("the path is
  54→2→14→(route 4)→59 via these warps") so model budget goes to *execution* walls, not topology.

Acceptance: a unit test routes 54 → 59 offline; the door-mat spring class (gym, Center, gate
rooms 55/57 — 3-for-3 as the wall on 08-18/19) is addressed by knowing every mat's dest before
stepping, with a regression test per measured spring (2↔54, 58↔2, 2↔57, 2↔14).

## Component 2 — the loop supervisor: force continuation and strategy switches

Harness-side, because mission text is measured exhausted (five Haiku early exits told in-mission,
plus Sonnet's, moved nothing).

- **Continuation**: both launchers already know budget remaining at operator exit. If the
  operator exits with > 20 % budget left and no baton written, relaunch with a continuation
  prompt (`claude -p --resume <session>` / pi session resume): "Budget remains: Xm. The blocker
  you named is not solved. Continue." Bounded (max 3 continuations per leg) and logged in the row.
- **Wedge detection**: a sidecar (`scripts/supervisor.py`, polling the same telemetry
  `role_metrics.py` reads) tracks furthest-coordinate-per-map and failure fingerprints
  (map-pair springs, unchanged position + rising stuck). Two triggers:
  - *no new furthest coordinate in N minutes* → inject a strategy-switch advice via the existing
    per-lane advice inbox (e030175) and, on the next operator turn, via a harness nudge;
  - *same fingerprint twice* → the nudge names it: "you have now tried the <family> approach
    twice; the supervisor blocks a third; change dimension (code vs genome vs route)."
- **Load honesty**: supervisor holds the Brock-day rule — before a wedge nudge, check slots/load
  so starvation is never reported to the model as a wall.

Acceptance: replay of the Sonnet 08-19 session (stream-json) triggers the family-repeat nudge at
fix #6, and the continuation fires at its 89-minute exit. Replay of Brock r1 does *not* fire the
wedge nudge during the load-204 window.

## Component 3 — auto-resume: survive the box

Multi-day local runs will eat an eGPU hang. The harness-death guard *detects* (dead stream, Xid,
Ollama crash); nothing *recovers*.

- **`scripts/expedition_run.sh`** (outer loop, replaces the ad-hoc chain scripts): on operator
  death, run the guard's checks; if harness-death, `reap_emulators.sh`, restart Ollama if its
  crash signature matched, and relaunch the leg from the newest baton (else the leg seed) in the
  same worktree — learnings and commits are already on disk, so nothing is relearned. Bounded
  (max R resumes per leg, default 5); every resume logged in the leg report.
- Kernel-hang case (box needs a human): PushNotification-style alert + clean stop, never a
  silent stall.

Acceptance: `kill -9` of the operator mid-leg resumes within 2 minutes from the last baton;
a simulated Ollama crash log triggers the service restart path.

## Component 4 — expedition mode: assists on, knowledge compounds

Benchmarks measure models, so `ASSIST=none` is their default. Expeditions clear the game, so:

- `MODE=expedition` in both launchers: `ASSIST=all` (tips + consult + fit), no budget cap
  (supervisor owns termination), rows labeled `expedition` and excluded from bench tables by
  label — the same separation the README already enforces for assisted rows.
- **Tip promotion becomes part of the loop**: after each leg, `advisor.py promote` runs against
  the leg's learnings; verified entries land in `docs/prompts/tips.md` on the expedition branch,
  so leg N+1 starts smarter than leg N without a human copying knowledge.
- Legs chain by baton on one long-lived branch (`expedition/<start-date>`); merges to main
  remain human-gated PRs (the #97 reconciliation discipline), but the expedition does not wait
  for them — it carries its own fixes forward.

## Component 5 — escalation tier: Opus inside the loop

Standing split (see `multi-model-path`): Opus is a fix source, never a row. In expedition mode
that becomes a rule the supervisor executes instead of a decision made per-wall:

- K failed attempts on one wall fingerprint (default 3, counting across resumes and models) →
  the supervisor spawns a fix-source run: Opus on Claude Code, 30-minute cap (Brock took 14),
  in a fresh worktree, prompted with the wall's accumulated evidence (learnings + fingerprints +
  the failing lanes' logs). Its patch lands on the expedition branch after tests, and the
  expedition resumes. Cost-bounded: a per-day Opus budget, alert when exhausted.
- Workhorse economics stay: qwen38 local ≈ $0.26 energy/2 h leg; Sonnet/Opus only via the
  escalation tier or explicit choice.

## Delivery — all components in this PR

| ships | files |
|---|---|
| ROM truth: extract / route / seed-worldmap, sha-guarded | `scripts/rom_truth.py`, `references/rom_truth.json`, `tests/test_rom_truth.py` |
| Supervisor: exit classification, spring/stall fingerprints, replay | `scripts/supervisor.py`, `tests/test_supervisor.py` |
| Outer loop: resume / continue / retry / escalate, advisor hand-off | `scripts/expedition_run.sh` |
| Expedition mode + supervisor prompt injection | `MODE` / `MISSION_EXTRA_FILE` in both launchers |
| Fix-source mission for the escalation tier | `docs/prompts/operator_prompt_fixsource.md` |

**First result, before any run:** `rom_truth.py route 54 59` answers the question three 2-hour
runs could not — `54 --mat--> 2 --east edge--> 14 --NORTH edge--> 15 --warp (18,5)--> 59`.
Route 3's exit is its **north** connection to Route 4; qwen38's marches were sweeping an east
edge that ROM truth shows is interior. Validation: Pewter's seven warps match the live-measured
table byte-for-byte, the gym mats read LAST_MAP at (4,13)/(5,13), Route 3's warp table is empty
at 70x18 — and the derived collision grids agree with the learned `badge1_gym_hp6.worldmap` on
**465/465 cells** of map 2. Supervisor replay on the real runs fingerprints Sonnet's Center
bounce (`2<->58`, 617 round trips in probe13 alone) and qwen38 r2's gate-room spring (`2<->57`).

"Does ROM truth move an unassisted row?" remains a bench question in its own right
(`ASSIST` stays none; `rom_truth.json` is repo data like `routes.json`, not an assist).

## Risks

- **ROM-truth correctness**: a wrong collision grid misroutes silently. Mitigation: cross-check
  extracted warps against every live `wWarps` read logged in past runs' telemetry (we have
  thousands) before trusting the grid.
- **Supervisor nudge loops**: a nudge that fires every poll becomes noise the model learns to
  ignore. Mitigation: once-per-fingerprint emission (the pattern `MTMOON-MISS` already uses).
- **Expedition branch drift** from main: long expeditions accumulate fixes main doesn't have.
  Mitigation: the human-gated reconciliation PR after each cleared segment, while the expedition
  continues — same as #97.
- **Unattended cost**: local is ~$3/day; the Opus tier is the only real spend and is capped.
