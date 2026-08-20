# 2026-08-19 — Mt. Moon head-to-head on the reconciled main: qwen38-27b vs Sonnet 5

The first runs on main @ `7363923` (PR #97: qwen38's warp-table gym-exit leg merged as the measured
winner over Haiku's cooldown patches, plus the coverage/robustness pass). Both rows share everything
but the model: `badge1_gym_hp6.state` seed, `operator_prompt_mtmoon.md` mission, 2 h hard cap,
`--sideloop-every 300` required, `ASSIST=none`. Mode is `mixed` (README): Sonnet on Claude Code
(Max sub), qwen38 local on pi. **Compare Claude ↔ local on behaviour, not wall clock.** This is
also Sonnet 5's first row anywhere in benchmarks/.

The question going in: with the gym exit and Route 3 entry merged and "free", is the wall the
eastward Route 3 crossing? Answer: no — the wall moved *backwards* into the door-mat machinery,
and both models spent their budget there.

## Scoreboard

| model | harness | map 59 | furthest | wall | model time | turns | s/turn | out tok/s | input | cache read | output | provider $ | cloud $ eq | Wh / energy $ | code fix | commits | learnings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sonnet 5 | Claude Code | **no** | map 58/2 — the Center exit door bounce | 89.1 m | 76.5 m | 351 | — | — | 20.8 k | 41.2 M | 408 k | **$23.57** | — | — | `agent.py` | 3 | 5 (quoted log lines, one mid-run count stale — see below) |
| **qwen38-27b** (128k, no MTP, 600 W) | pi, local | **no** | **map 55 entry (city (29,13)); run 1 also touched 14** | 113.0 m | 85.3 m | 229 | 22.4 | 54.5 | 14.2 M | 0 | 279 k | $0 | $2.27 | 860.5 / $0.26 | `agent.py` | **8** | 2 |

Guard: qwen38 row passed the harness-death check (0 errors, no Xid, no Ollama crash; power log
integrated by the launcher). 5 compactions, max ctx 98 k — the guardrails' proactive compaction
held a 113-minute local run inside the window. No baton from either run; every `report.json`
`winner: null`.

## The character inversion

`role_metrics.py` on both sessions, against the same models' prior rows:

| run | relays | probes | probe/relay | calls→1st relay | early exit |
|---|---|---|---|---|---|
| qwen38 08-18 (pre-merge base) | — | 14 | high (Investigator) | late (code first) | by choice, 25 m left |
| **qwen38 r2 (today)** | **10** | **0** | **0.0** | **31** | **no — 113 of 120 m** |
| Sonnet 5 (today) | **1** | **16** | **16.0** | **291** | **yes — ~31 m left** |

They swapped scripts. qwen38, whose 08-18 character was the probe-everything Investigator, ran a
tight patch→relay→read-ground→patch loop: 8 commits, one per measured failure (entry-door spring,
edge sweep ordering, the A* pilot's stale-grid wedge, press-slide). Zero probes — the relays *were*
its probes. Sonnet ran one relay in 89 minutes and 16 probes: nine numbered fixes, each with a
6000-turn probe and an explicit ruled-out cause. Neither script beat the wall.

## What each model did with the same seed

**Sonnet 5** found the real seam in the merged base within the hour: the canonical Pewter heal
flow is badge-gated off (`if state.badges & 0x01: never detour`), while the merged `_mtmoon_action`
*defers* to that flow inside the Center — so badge-1 lanes crossed Route 3 at 6/48 HP and whited
out. Its heal-gating fix is verified in its own probe log (`HEAL | map=58 pos=(3,3) at counter
hp=6/50`). That fix exposed the next wall and the run died on it: exiting the Center springs
`58 -> 2 -> 58` at (13,25), the same `LAST_MAP`-mat family as the gym door, one building over.
Fixes #5–#9 (settle-wait, cooldown bump, backtrack-disable, dismiss-suppression, `_mtmoon_healed`
latch) each measured 0 wins / 6000 turns. It ended by choice at 89 of 120 minutes with the blocker
named, located, and unresolved — a shallower early exit than Haiku's (74 % of budget used vs ~30 %)
but the same shape. One verification note: its summary quotes `grep -c` = 232 for the probe13
bounce; the log has grown since (309 lines for the `58 -> 2` direction alone) — the count was taken
mid-run, the phenomenon is real.

**qwen38-27b** hit the same heal seam and patched past it in its first commit ("heal once inside
the Center") without ever wedging on the Center door — then spent the run fighting the gate rooms.
Run 1 reproduced the 2↔14 spring (777 transitions, 0 crossings); patches 2–6 worked the road maps
55/57: warp-table INT format fix, edge-sweep-before-forward-link, a bounce-aware march fallback
for the A* pilot's "stale open-cell" wedge (115 replans on 57's 9×8 room, never arrived), a
press-slide for non-firing edge presses, and blocking 57's city-door spring (2↔57 ×18). Final
blocker, its words: *"pilot stale-grid wedge in the custom gate rooms (57/55)"* — with next-agent
moves documented. 7 relay runs, 37 lane-lives, best lane parked in map 55's room. It used 113 of
120 minutes.

Mission compliance note: the mission says one relay at a time; qwen38 queued up to 11 relay
invocations mid-run. The box-wide relay `flock` (Brock-day fix) serialized them — load peaked ~70
(healthy chain peak is ≤53) from its parallel `--parallel 1..4` lanes plus healer races, the
30-slot pool held throughout, and no lane starved into a fake wall that we can see. The lock
doing its job is why this is a footnote and not an invalidated row.

## Self-healing on this segment

| | Sonnet 5 | qwen38-27b r2 |
|---|---|---|
| sideloop races finished rc=0 | 140 | 664 |
| skipped, box full (rc=1) | 0 | 166 |
| advice applied | 140 | 664 |
| outcome change attributable | none | none |

The 08-18 finding repeats a third time: the subloop moved knobs constantly and neither wall was a
knob. Both walls today were code (a gated-off heal flow; door-mat springs in gate rooms), and both
models correctly went at the code instead. Notable vs 08-18: qwen38's heal was *not* silenced this
time (664 applied vs 0) — its lane mix left slots free often enough for races to land.

## Verdict

Neither model cleared Mt. Moon; the row that matters is the shape of the failure. qwen38 got
further (55, with 14 touched, vs the Center doorstep), used more of its budget, and left 8
mergeable-shaped commits plus a written hand-off; it did it for ~$2.53 all-in against Sonnet's
$23.57. Sonnet found the heal seam with the cleanest causal chain of any run on this mission and
measured nine hypotheses honestly, but converted none of it into map progress. On this mission,
at these prices, **qwen38 is the better operator and Sonnet is the better diagnostician** — the
same split as Haiku-vs-qwen38 on 08-18, at 13× Haiku's price point.

## Next

- **The door-mat machinery is now three-for-three as the wall** (gym, Center, gate rooms 55/57).
  One fix source pass (Opus, per the multi-model split) over the *general* mat/spring handling —
  `LAST_MAP` mats, gate-room pilots, press-slide — would likely unblock every future leg at once;
  qwen38's 8 commits and Sonnet's 9 measured failures are the spec.
- Sonnet's heal-gating fix and qwen38's r2 patches overlap again (both touch the heal seam and
  door handling). Same reconciliation discipline as PR #97: pick one base, salvage the other's
  measurements as data.
- Sonnet's early exit means the harness-side continuation nudge (the top lever after five Haiku
  early exits) now has a second model as evidence.
- An `ASSIST=fit` row for Sonnet would test whether "you probe 16× per relay; relay more" moves it
  the way Haiku's section moved Haiku.

Artifacts: worktrees `../pokemon-kafka-speedrun-sonnet-cc-mtmoon` (branch `speedrun/sonnet-cc-mtmoon`,
3 commits) and `../pokemon-kafka-speedrun-pi-qwen38-27b-mtmoon-r2` (branch
`speedrun/pi-qwen38-27b-mtmoon-r2`, 8 commits); stream-json `data/local_runs/sonnet-cc-mtmoon.claude.jsonl`;
pi transcript in `~/.pi/agent/sessions/...mtmoon-r2--/`; chain log `data/local_runs/mtmoon-chain2.log`;
power `data/power/`; seeds `demo-runs/states/mtmoon_seeds/`.
