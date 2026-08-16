# 2026-08-16 — Haiku 4.5 on the Claude Code harness, fixed `main` (harness-axis confirmation)

Why: confirm the game-side fixes (flee-loop watchdog, Pewter route, fight-menu sync) hold
independent of the local-GPU story, by running a cloud model on a different harness. Haiku 4.5 on
Claude Code (Max sub, no plugin this time — the 08-15 superpowers plugin is gone), `route1.state`
seed, worktree off `main`, captured to tapes, via `scripts/claude_relay_run.sh` (new, PR #82).

## Scoreboard

| model | segs | wall | model time | turns | input | cache read | cache write | output | provider $ | code | commits |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Haiku 4.5 (Claude Code, `main`, assist=none) | **1/4** | 11.0 m | 7.1 m | 64 | 2,390 | 5.13 M | 148 k | 28 k | **$0.95** | 2 relay variants (no code read) | 2 |
| _Haiku 4.5 (Claude Code, 08-15, old code + plugin)_ | 2/4 | 67 m | 5.9 m | 74 | 4.7 k | 3.5 M | 285 k | 32 k | $0.87 (bench) | no | 3 |
| _laguna-xs r2 (local, `main`)_ | 2/4 + inside Gym | 40 m | 6.6 m | 98 | 8.4 M | 0 | 0 | 36 k | $0.85 eq | no | 0 |

## What it confirmed

- **The flee-loop fix holds on a cloud driver on a different harness.** `route1_to_forest` cleared
  first relay (868 turns), same as laguna-xs r2 and every recent run. The Route 2 wedge that stopped
  every 08-15/16 run is gone.
- **Haiku behaved exactly as its fit says (SUMMARY §10): a driver.** Honest, methodical, committed
  as it went (2 commits with real diagnoses in the messages), added two flee-threshold *variants* to
  `relay.py` (`escape_mode`, `ultra_escape`) — knob-tuning, no code read. No fabricated attempts. It
  even correctly diagnosed that route1's 7-HP exit is deterministic (quest-phase override), not a
  variant-selectable outcome.

## What it surfaced — the forest regression, exactly as the eval predicted

All three `forest_to_pewter` attempts (6k → 12k → 16k turns, 7 variants) failed: every lane
oscillates in map 51 at **(6,7)-(7,8)** and **(25,21)-(26,22)**, healthy, and never reaches Pewter
(map 2). This is not new breakage — it is the `forest-crossing-healthy` eval's standing verdict
showing up in a real relay:

- before the battle fixes: `forest-crossing-healthy` was a **PYTHONHASHSEED coin flip** (PASS seed 7,
  FAIL seeds 0/1) — never a real pass;
- after #76/#77 (battle wedge/cap, fight-menu sync): a **deterministic FAIL** — battles now strong
  (L16, full HP) but navigation stalls in the forest.

The battle fixes did not break the forest; they removed the luck and the "too weak" masking that hid
it. laguna-xs r2 only crossed by brute force (`aggressive`, 12,000 turns), not the eval's genome.
Fix in progress on `fix/viridian-forest-navigation`, gated on `forest-crossing-healthy` passing
under PYTHONHASHSEED 0/1/7.

## Cross-model finding: models inflate wall-clock 5-7×

Haiku's own `SPEEDRUN_SUMMARY.md` reports "~65-80 minutes of the 150-minute budget" for a run that
took **11 minutes** (result event `duration_ms`). Qwen3-Coder claimed 45 for 8. Models have no
clock; they infer elapsed time from turn count and inflate it. This is a mission-prompt fix — have
the operator run `date` at start and before writing the summary — not a model flaw to grade. It also
means every self-reported wall-clock in a `SPEEDRUN_SUMMARY.md` is unreliable; trust the harness
(`bench_report.py` / the stream-json `result` event), which is why the scoreboard wall above is
measured, not self-reported.

Artifacts: worktree `../pokemon-kafka-speedrun-haiku-cc-r2` (branch `speedrun/haiku-cc-r2`, 2 commits),
stream-json `data/local_runs/haiku-cc-r2.claude.jsonl`, tapes session captured on :8082.
