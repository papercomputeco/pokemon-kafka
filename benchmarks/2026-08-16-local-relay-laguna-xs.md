# 2026-08-16 — Mt. Moon relay, laguna-xs (Poolside Laguna XS 2.1, local, 128k) on the pi harness

Second local relay run of the day; same recipe as `2026-08-16-local-relay-qwen3-coder.md`
(`scripts/local_relay_run.sh laguna-xs`: worktree off `2cd9240`, `operator_prompt_v2`, seed
`route1.state`, guardrails, tapes, Kafka bridge, power sampled for the whole run). Laguna was the
fastest decoder on the roster (316 tok/s) and only fifth on the eval quiz (0.45, silent on two
cases, weakest honest-summary) — the run was the test of whether raw speed survives a real loop.

## Scoreboard

| model | segs | wall | model time | turns | tools | out tok/s | s/turn | input tok | cache read | output tok | provider $ | cloud $ | Wh | energy $ | max ctx | code fix | learnings | commits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| laguna-xs (`laguna-xs-128k`, local RTX 5090) | **2/4** | 40.0 m | 6.6 m | 98 | 97 | **91.1** | **4.0** | 8.42 M | 0 | 36 k | local | $0.85 (Poolside list 0.10 / 0.20) | **77.5** | $0.023 | **130,820** | no (genome + seed-state work) | 1 (well-formed, honest) | 0 |
| _Haiku 4.5 (08-15, reference)_ | 2/4 | 67 m | 5.9 m | 74 | 73 | 91.9 | 4.8 | 4.7 k | 3.5 M | 32 k | $0.87 | $0.87 | — | — | — | no | 3 + summary | 3 |
| _qwen3-coder-30b (earlier today)_ | 0/4 | 12 m | 3.9 m | 115 | 114 | 112.2 | 2.0 | 3.88 M | 0 | 26 k | local | $0.57 | 40.3 | $0.012 | 51 k | no | 3 fabricated + summary | 1 |

Power: 488 samples over 40.8 min, GPU mean **114 W**, peak 602 W. Ended with `stopReason: length`
at 130,820 input tokens — the **128k window filled** (one pi compaction, not enough); the model
was mid-investigation, not done.

## What happened

1. Dry run, segment-1 smoke: the same six-lane flee-loop wall (Route 2, lead 4–12 HP) that stopped
   qwen3-coder. Laguna did not blame the harness. It ran `agent.py` directly from `route1.state`
   with short budgets, tried `hp_run_threshold`/`hp_heal_threshold` genomes, and then **built a
   healed seed state** (`--save-state-on-map`, saved on Route 2 at 12/23 HP) and re-ran the segment
   from it — every lane cleared to Viridian Forest, winner `base` in 519 turns.
2. `forest_to_pewter` from that baton: first pass all lanes stuck in the forest at 6000 turns;
   second pass at 12000 turns, `aggressive` reached Pewter (4496 turns, 1 HP). **2/4.**
3. `pewter_to_badge`: every lane reaches map 58 and stalls at 4000/8000 turns with *healthy* HP
   (42–51). **Map 58 is the Pewter Pokémon Center, not the Gym** (`relay.py`: `PEWTER_GYM = 54`);
   the 08-15 Haiku learning (`pewter-gym-navigation.md`) mislabelled it and the label stuck. What
   the lanes actually do: walk in, heal, then stand at (11,3) pressing "up" into the counter for
   ~3000 turns. Reproduced in isolation as `evals/cases/pewter-pokecenter-exit.json`
   (`max_stuck_streak` 2912 of 3000). Laguna's last actions were grepping `relay.py` for the
   `pewter_to_badge` waypoints — the right thread — when the context ran out.
4. One learning written, `viridian-forest-route1-blackout.md`: correctly-shaped, causal ("seed
   state started at 12/23 because the party had already fought on Route 1 … be healthy before tall
   grass"), honest artifacts. **No fabrication.** No `SPEEDRUN_SUMMARY.md`, no commit — the context
   died before the deliverables; the mission said commit as you go and it did not.

## Reading

- **Haiku's cadence, exactly, on a $2k card.** 91.1 out tok/s in-run vs Haiku's 91.9; 4.0 s/turn
  vs 4.8. Same segments (2/4), same wall as the Sonnet/Haiku band. This is the first local row
  that is *comparable* to Haiku on the game axis rather than merely faster on decode.
- **It behaved like an operator.** Worked around the flee-loop by changing the seed state instead
  of arguing with the harness; scaled turn budgets when a segment stalled; wrote an honest
  learning. It did not read `agent.py`'s battle code, so it never *fixed* the flee-loop — the
  workaround is a genome-and-state answer, the "tunes knobs" style the 08-15 write-up called out
  for Haiku and Gemma. Sonnet/Kimi's code-reading advantage still stands.
- **Context, not judgement, ended the run.** 8.42 M input tokens uncached; the window filled at
  130,820 and pi's single compaction did not save it. The 08-15 note that pi "compacts only after
  a 400" bit again on a local model that returns `length` instead of 400. Two harness fixes: a
  guardrails-side compaction trigger at ~75 % of `contextWindow`, and a reminder to commit
  deliverables early — both are harness work, not model work.
- **The eval quiz mis-ranked it.** Fifth on the quiz (silent on two cases; the honest-summary case
  scored 0.33) — yet in the run it was honest and productive. Truncation on the quiz measured a
  thinking budget, not a behaviour; the run is the better instrument for this model.
- **Energy is now real.** 77.5 Wh for 2/4 segments in 40 min — 2.3 cents. Cloud-equivalent $0.85
  is almost entirely uncached input.

## Next

- Rerun with a compaction guard (or `contextWindow` set below `num_ctx` so pi compacts before the
  model returns `length`) — this model has more run in it.
- The Brock leg is blocked by the Pokécenter exit wedge, not the Gym; fix that (the eval will flip
  from XFAIL) and give Laguna the leg from its own `forest_to_pewter` baton.

Artifacts: worktree `../pokemon-kafka-speedrun-pi-laguna-xs` (branch `speedrun/pi-laguna-xs`,
uncommitted `docs/learnings/viridian-forest-route1-blackout.md`), pi session
`~/.pi/agent/sessions/--home-bdougie-code-pcc-labs-pokemon-kafka-speedrun-pi-laguna-xs--/2026-08-16T04-27-*.jsonl`,
batons `<worktree>/data/relay/260816-045315/batons/{route1_to_forest,forest_to_pewter}.state`,
power CSV `<worktree>/data/power/laguna-xs.csv`.
