# 2026-08-15 — Mt. Moon relay (issue #70), five models on the pi harness

Goal: `route1_to_forest → forest_to_pewter → pewter_to_badge → badge_to_mtmoon` via
`scripts/relay.py`, recording a `docs/learnings/` entry per obstacle. Seed `route1.state`.
Harness: pi 0.70.6 + guardrails extension, identical prompt (`operator_prompt_v2`), 2.5 h budget,
one worktree per model, all runs captured to tapes and streamed to Kafka.

Result: nobody reached Mt. Moon; everybody reached Pewter (2/4). All five stalled on the same repo
defects on the Brock leg (`routes.json` Pewter Gym waypoint at (16,11) is a wall; `--stop-on-map`
saves on the first frame of a map change). Full narrative: `docs/learnings/by-run/2026-08-15-*`.

## Scoreboard

| model | segs | wall | model time | turns | tools | out tok/s | s/turn | input tok | cache read | output tok | provider $ | code fix | learnings | commits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Sonnet 5 (`claude-sonnet-5`, adaptive thinking) | 2/4 | 49 m | 28.9 m | 186 | 187 | 72.8 | 9.3 | 372 | 24.8 M | 126 k | $17.14 (pi fallback rate; true $6.86) | yes — RUN/menu desync; waypoint-index reset | 5 + summary | 3 |
| Kimi K2.6 (`kimi-k2.6:cloud`, Ollama cloud) | 2/4 | 158 m | ≥34.8 m¹ | ≥190 | ≥228 | 56.4 | 11.0 | ≥26.7 M | 0 | ≥118 k | n/a | yes — flee-loop cap; Pewter targets; transition-save diagnosis | 3 | 3 |
| Haiku 4.5 (`claude-haiku-4-5-20251001`) | 2/4 | 67 m | 5.9 m | 74 | 73 | 91.9 | 4.8 | 4.7 k | 3.5 M | 32 k | $0.87 | no (variant spreads, seed swap) | 3 + summary | 3 |
| Qwen3.5-35B Q4 (`qwen35b-64k`, local RTX 5090) | 2/4 | 38 m | 27.1 m | 101 | 123 | 20.1 | 16.1 | 4.9 M | 0 | 33 k | local | edits, uncommitted, off-format² | 1 (free-form) | 0 |
| Gemma4-8B Q4 (`gemma4-64k`, local RTX 5090) | 2/4 | ~15 m active³ | 0.9 m | 29 | 27 | 142.9 | 1.9 | 751 k | 0 | 8 k | local | no (2 genome numbers) | 3 + summary | 4 |

¹ Kimi's pi transcript stopped updating after an in-run compaction at 13:04; row is a lower bound
over the first 66 min. ² Qwen's context was pinned at Ollama's 64 k `num_ctx` — silent truncation
of the front of the prompt (the mission) for the second half of the run. ³ Gemma exited at 4 min
(thinking-only turn, no action) and was resumed once with "act every turn"; wall spans the idle gap.

Reference (not same-harness): Haiku 4.5 on Claude Code with the superpowers plugin loaded — 39 min,
$1.28, 1/4 segments, wrong root cause; the plugin's SessionStart hook turned the headless run into a
plan + a question and exited at 70 s. Plugin since removed.

## True cost — priced as cloud tokens

Provider-reported cost is not comparable across rows (Ollama cloud is a flat subscription, local
models and the Claude Max sub report $0, and pi priced `claude-sonnet-5` with a fallback rate). So
every run is re-priced at published per-million-token cloud rates on the tokens it actually used
(`scripts/bench_report.py --rate-in/--rate-out/--rate-cache-read/--rate-cache-write`). This is what
the run costs *at scale*.

| model | tokens (in / cache read / cache write / out) | rate used ($/M in / out; cache read / write) | **cloud $** | notes |
|---|---|---|---|---|
| Sonnet 5 | 372 / 24.8 M / 256 k / 126 k | 2 / 10; 0.20 / 2.50 (Anthropic list) | **$6.86** | pi reported $17.14 using a fallback rate — wrong |
| Kimi K2.6 | ≥26.7 M / 0 / 0 / ≥118 k (first 66 min) | 0.95 / 4.00; cache-hit 0.16 (Moonshot list) | **≥$25.87** (≈$60 for the full 158 min) | uncached — every turn re-sent ~108 k tokens. Same tokens with 90 % cache hits ≈ $6.9. Ollama cloud billed a flat sub instead |
| Haiku 4.5 | 4.7 k / 3.5 M / 285 k / 32 k | 1 / 5; 0.10 / 1.25 (Anthropic list) | **$0.87** | matches pi |
| Qwen3.5-35B (local) | 4.9 M / 0 / 0 / 33 k | 0.14 / 1.00 (OpenRouter, Qwen3.5-35B-A3B) | **$0.73** | cloud-equivalent |
| Gemma4-8B (local) | 751 k / 0 / 0 / 8 k | 0.20 / 0.20 (proxy: Gemma 4 E4B; no 8B cloud SKU) | **$0.15** | cloud-equivalent |

Reading: uncached Kimi is the most expensive run by 4×; caching is the single biggest cost lever
(Sonnet's 24.8 M tokens were 99 % cache reads). Cost per segment cleared: Sonnet $3.43, Kimi ≥$13,
Haiku $0.44, Qwen $0.37, Gemma $0.08 — but only Sonnet/Kimi produced code fixes.

### Local energy (measured after the fact)

`scripts/power_sampler.py` did not exist during today's runs, so local energy is estimated from a
calibration: on the RTX 5090, `gemma4-64k` and `qwen35b-64k` generation peaks at 290–350 W
(226 / 175 tok/s on a 700-token burst; idle 19 W). Using 300 W over model time: Qwen ≈ 27 min →
≈0.14 kWh (≈$0.04 at $0.30/kWh); Gemma ≈ 0.9 min → ≈5 Wh. CPU package power is not readable
without root on this box (RAPL), so these are GPU-only. Future rows carry measured Wh and $ from the
sampler CSV via `bench_report.py --power-log --kwh-price`.

## Game-side (from `data/telemetry/game`, the Kafka `agent.game.events` feed)

| run | events | lanes | battle events | HP-0 events | stuck events | blackouts |
|---|---|---|---|---|---|---|
| Sonnet | 559,942 | 102 | 31,815 | 96 | 13,724 | 141 |
| Kimi (attempt 2) | 4,479,018 | 432 | 112,269 | 1,133 | 226,053 | 1,106 |
| Haiku | 1,632,427 | 184 | 278,604 | 663 | 65,562 | 554 |
| Qwen-35B | 345,833 | 108 | 39,641 | 95 | 7,502 | 105 |
| Gemma-8B | 351,257 | 60 | 39,341 | 137 | 21,035 | 165 |

Flink: 10,623 alerts on `agent.telemetry.alerts` for the day (DOOR_STALL, BATTLE_LOOP,
GAME_STUCK_LOOP, POSITION_DEADLOCK, STUCK_STREAK_SPIKE, IN_PLACE_WEDGE, LOW_HP_GRIND,
BATTLE_WIPE, NO_PROGRESS). Alerts don't carry `run_id` yet, so they aren't split per model.

## Strengths observed

- **Sonnet 5** — fastest to a complete, honest result; disciplined reads (`sed -n` ranges); found
  a real navigation bug (waypoint-index reset) and pinned the Brock wedge to bad map data. Costly at
  this cadence.
- **Kimi K2.6** — deepest diagnoses (flee-loop mechanism, mid-transition savestate); slow, uncached,
  needs context guardrails; missed the summary deliverable.
- **Haiku 4.5** — cheapest, fastest per turn; config-layer only, plausible-but-wrong root causes,
  self-terminates at ~1 h.
- **Qwen3.5-35B** — solid tool use for a local model (20 tok/s), a real hypothesis about the world
  map, but derailed by silent context truncation.
- **Gemma4-8B** — 143 tok/s and working tool calls; ends turns without acting; pattern-matches
  obstacle names from the prompt.

## Repo defects surfaced (fix before the next round)

1. `references/routes.json` — Pewter Gym waypoint (16,11) is a wall; Kimi's attempt 1 used (16,17).
2. `scripts/agent.py --stop-on-map` — savestate taken on the first frame after `wCurMap` changes,
   player coords still on the previous map (Kimi).
3. Wild-battle flee stall on Route 1/2 — two compatible fixes: cap stall-guard runs and fall back to
   fight (Kimi, arrives at 17 HP) or confirm RUN + periodic unstick (Sonnet, arrives at 4 HP).
4. Waypoint index starts at 0 when a lane loads mid-map, replaying the early game after a whiteout
   (Sonnet).
