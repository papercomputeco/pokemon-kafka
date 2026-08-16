# 2026-08-16 — Mt. Moon relay, qwen3-coder-30b (local, 128k) on the pi harness

The first relay run chosen by the two probes in `2026-08-15-local-decode-probe.md`: `qwen3-coder-30b`
was second on the diagnostic evals (0.69, answered every case) and third on decode (303 tok/s), the
best combined pick. Same harness as the 08-15 five-model run: pi + `scripts/pi-ext/guardrails.ts`,
`operator_prompt_v2` (window line changed 262k → 128k), seed `route1.state`, worktree off the same
base commit `2cd9240` so it faced the same repo defects, tapes capture, Kafka bridge, and — new —
`scripts/power_sampler.py` running for the whole run so energy is measured, not estimated.

## Scoreboard

| model | segs | wall | model time | turns | tools | out tok/s | s/turn | input tok | cache read | output tok | provider $ | cloud $ | Wh | energy $ | max ctx | code fix | learnings | commits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen3-coder-30b (`qwen3-coder-30b-128k`, local RTX 5090) | **0/4** | 12.0 m | 3.9 m | 115 | 114 | 112.2 | 2.0 | 3.88 M | 0 | 26 k | local | $0.57 (Qwen3-Coder-30B OpenRouter rate 0.14 / 1.00) | **40.3** | $0.012 | 51 k | no | 3 + summary (see below) | 1 |
| _Haiku 4.5 (08-15, for reference)_ | 2/4 | 67 m | 5.9 m | 74 | 73 | 91.9 | 4.8 | 4.7 k | 3.5 M | 32 k | $0.87 | $0.87 | — | — | — | no | 3 + summary | 3 |

Power: 152 samples over 12.6 min, GPU mean **190 W**, peak 604 W (the card's 600 W limit).
40.3 Wh is the whole-run figure including idle between turns; at $0.30/kWh that is 1.2 cents.

## What happened

1. Dry run, then the suggested segment-1 smoke (`--max-turns-scale 0.5 --timeout 900`). All six
   `route1_to_forest` variants ended identically: 2000 turns, final map 13, lead at 4/23 HP,
   `Action: run` against a Lv3 Weedle until the budget ran out — **the exact flee-loop obstacle**
   in `docs/learnings/route1-navigation-flee-loop.md`, and the exact case this model scored 0.82
   on in the eval suite when handed the `choose_action` excerpt.
2. It did not open `agent.py`, `report.json`, or a lane's `fitness.json`. It re-ran the segment
   with `--timeout 60 --parallel 1` (every lane killed at 60 s), then `forest_to_pewter` the same
   way, and concluded the relay system was "not processing segments correctly … system may be
   underperforming or misconfigured".
3. It wrote four `docs/learnings/` files and committed. Three describe obstacles it never reached
   (`brock.md`: "several battle variants were attempted … all failed to defeat Brock";
   `route-3-navigation.md`) — **fabricated run history**. `SPEEDRUN_SUMMARY.md` reports "~45
   minutes" wall clock for a run that lasted 8 minutes at that point.
4. It exited at 12 minutes with "ALL TASK REQUIREMENTS COMPLETED SUCCESSFULLY". Context never
   exceeded 51 k of 128 k, so this was not a context failure.

## Reading

- **Recognizing a bug when shown the code and finding it from a run are different skills.** The
  eval suite measures the first; the relay measures the second. This model has the first and not
  the second, and the eval's 0.69 did not predict a 0/4. The eval needs an *investigation* case:
  hand the model a `report.json` + lane directory, not an excerpt, and score whether it opens the
  right file.
- **Speed bought nothing.** 2.0 s/turn and 112 tok/s in-run — genuinely faster than Haiku's 4.8
  s/turn — but 115 turns of fast wrong moves. Turn quality, not turn rate, is the local gap.
- **Uncached local prompts are the hidden cost.** 3.88 M input tokens in 12 minutes with zero
  cache reads; the same run on a cached cloud API would have been ~90 % cache hits. At scale this
  is what makes local look expensive in cloud-$ terms even when the electricity is a cent.
- **Fabrication is the failure that matters.** Kimi and Sonnet on 08-15 wrote unresolved entries
  honestly; this model invented Brock attempts. Any local candidate needs a "did it lie about the
  run" check before its learnings can be trusted, and `run_model_evals.py` should carry a
  fabrication anti-pattern on the summary deliverable the way it now does for code facts.

## Decision

`qwen3-coder-30b` is **retired from the local roster** (2026-08-16, `RETIRED` in
`scripts/local_models.py`). It is tuned to edit code it is pointed at and has no thinking mode — a
fixer, not an investigator — and it fabricated run history. Its rows stay here as the record.

## Next

- Run `qwen38-27b` (best eval score, 0.79, dense) and `laguna-xs` (fastest decode) on the same
  recipe before drawing a roster-wide conclusion — one run is one run.
- Add an investigation-style eval case (`report.json` + lane dir → which file do you open) and a
  fabrication check on the summary; re-rank the roster on those before the next run slot.

Artifacts: worktree `../pokemon-kafka-speedrun-pi-qwen3coder` (branch `speedrun/pi-qwen3coder`,
commit `11fd955`), pi session `~/.pi/agent/sessions/--home-bdougie-code-pcc-labs-pokemon-kafka-speedrun-pi-qwen3coder--/2026-08-16T03-40-51-392Z_*.jsonl`,
power CSV `<worktree>/data/power/qwen3-coder-30b.csv`, relay dirs `<worktree>/data/relay/260816-0341*`.
