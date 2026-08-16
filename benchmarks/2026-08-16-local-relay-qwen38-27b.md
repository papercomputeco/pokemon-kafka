# 2026-08-16 — Mt. Moon relay, qwen38-27b (Qwen3.8 27B dense, local, 128k) on the pi harness

Third local relay run of the day, same recipe (`scripts/local_relay_run.sh qwen38-27b`). Qwen3.8
topped the eval quiz (0.79, perfect on the investigation case) and is the slowest of the "good"
decoders (130 tok/s probe, dense, thinking). **Attempt 1 (21:18) was killed at 8 min by a GPU
crash** — Ollama's journal: `CUDA error: the launch timed out and was terminated` →
`llama-server terminated: signal: aborted` — while the model was diagnosing correctly; pi reported
it as the model stopping (`stopReason: stop`, usage 0/0). Evidence kept in
`data/local_runs/qwen38-27b.attempt1/`. This file is **attempt 2**, a fresh worktree; the Ollama
journal is clean for its window.

## Scoreboard

| model | segs | wall | model time | turns | tools | out tok/s | s/turn | input tok | cache read | output tok | provider $ | cloud $ | Wh | energy $ | max ctx | code fix | learnings | commits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen38-27b (`qwen38-27b-128k`, local RTX 5090, attempt 2) | **1/4** | 22.2 m | 15.0 m | 91 | 99 | 70.4 | 9.9 | 6.48 M | 0 | 63 k | local | $0.97 (0.14 / 1.00 proxy) | **156.3** | $0.047 | **130,851** | **yes — battle-wedge watchdog in `agent.py`, tests + lint pass, cleared the segment** | 0 | 0 |
| _laguna-xs (today)_ | 2/4 | 40.0 m | 6.6 m | 98 | 97 | 91.1 | 4.0 | 8.42 M | 0 | 36 k | local | $0.85 | 77.5 | $0.023 | 130,820 | no | 1 | 0 |
| _Haiku 4.5 (08-15)_ | 2/4 | 67 m | 5.9 m | 74 | 73 | 91.9 | 4.8 | 4.7 k | 3.5 M | 32 k | $0.87 | $0.87 | — | — | — | no | 3 + summary | 3 |
| _Sonnet 5 (08-15)_ | 2/4 | 49 m | 28.9 m | 186 | 187 | 72.8 | 9.3 | 372 | 24.8 M | 126 k | $6.86 | $6.86 | — | — | — | yes | 5 + summary | 3 |

Power: 277 samples over 23.1 min, GPU mean **406 W**, peak 609 W (dense 27B at 128k runs the card
hot the whole time; Laguna's MoE averaged 114 W). Ended with `stopReason: length` at 130,851 —
the **128k window filled**, one pi compaction, mid-run.

## What happened

1. Dry run, segment-1 smoke: the six-lane flee-loop wall (2000 turns, map 13, all lanes
   identical). It read `routes.json`, ran a single `agent.py` lane from a checkpoint with 60-turn
   budgets to reproduce, and diagnosed the stall as a **battle whose state (flag + both HP) is
   identical turn after turn — an input-locked screen** that neither RUN nor FIGHT clears because a
   B-press is never sent in wild battles.
2. It **changed the agent code**: a battle-wedge watchdog in `PokemonAgent` (signature of
   `battle_type/player_hp/enemy_hp`; after two identical turns, `_recover_battle_wedge()` — B ×8,
   A ×3, wait — up to 4 attempts, reset on battle end). 40 lines, `pytest tests/test_relay.py`
   24 passed, `ruff` clean — it ran both before re-running the relay.
3. Re-ran `route1_to_forest`: **all six lanes cleared to Viridian Forest in 740 turns** (from 2000
   stuck). The `WEDGE` recovery fired once in the base lane. Baton written. **1/4.**
4. Context filled at 130,851 tokens on turn 91 while it was setting up `forest_to_pewter`. No
   learning file, no summary, no commit — the mission said commit as you go and it did not get
   there.

## Reading

- **The first local model to fix code, and the fix worked.** Sonnet and Kimi were the only 08-15
  models that changed `agent.py`; Qwen3.8 is the only local one. Its diagnosis differs from the
  learnings' ("the stall-guard branch returns run unconditionally") — it read the same log and
  saw a frozen screen rather than a wrong branch — but the empirical test is the relay, and the
  relay passed. It also *validated* the fix (tests + lint) before trusting it, which no other local
  model did.
- **Context, not judgement, ended the run — for the second model in a row.** Laguna died at
  130,820, Qwen3.8 at 130,851. Both were mid-task and productive. pi compacts only after a 400 and
  local Ollama models return `length` instead; one compaction was not enough for either. This is
  now the single most valuable harness fix: compact at ~75 % of the window from the guardrails
  extension, and nudge the operator to commit deliverables early. Both runs would have had ~1.5 h
  of budget left.
- **Slow and hot, but it did the expensive thing.** 9.9 s/turn (Haiku 4.8, Sonnet 9.3), 406 W
  mean, 156 Wh — 2× Laguna's energy for half the segments — but the segments-per-hour comparison
  is unfair to a model that spent its time on a real code fix. It is the local Sonnet, not the
  local Haiku.
- **The GPU crash was not the model.** Attempt 1 and attempt 2 opened the same way (smoke run,
  identical lanes, read the log, read `agent.py`); attempt 1 was cut off by CUDA, attempt 2 went on
  to fix the bug. Without the journal these look like a thinking-only exit and a good run by two
  different models.

## Checked against the agent eval

`evals/cases/route1-flee-loop.json` (FAIL on `main`: 2000 turns stuck on Route 2, 4 HP) run
against the patched `agent.py`: **reaches Viridian Forest in 916 turns** — the loop is broken —
but arrives at 2 HP and the case requires ≥5, so it still reads FAIL. The watchdog fixes the
wedge, not the health; the learnings' recommended fix (cap the stall-guard run and fall back to
fight) addresses the other half.

## Next

- Ship the compaction guard, then rerun both Laguna and Qwen3.8 with the wedge watchdog in place
  (it is a real fix; it belongs on `main` after review) — Qwen3.8 has ~1.5 h and three segments
  left in it.
- Add `WEDGE` recoveries to the game-side telemetry so the fix's firing rate is measurable.

Artifacts: worktree `../pokemon-kafka-speedrun-pi-qwen38-27b` (branch `speedrun/pi-qwen38-27b`,
uncommitted `scripts/agent.py` diff), pi session
`~/.pi/agent/sessions/--home-bdougie-code-pcc-labs-pokemon-kafka-speedrun-pi-qwen38-27b--/2026-08-16T05-07-*.jsonl`,
baton `<worktree>/data/relay/260816-052925/batons/route1_to_forest.state`, power CSV
`<worktree>/data/power/qwen38-27b.csv`, attempt-1 evidence `data/local_runs/qwen38-27b.attempt1/`.
