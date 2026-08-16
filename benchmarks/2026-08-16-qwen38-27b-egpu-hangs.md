# 2026-08-16 — qwen38-27b on the fixed `main`: three attempts, three GPU deaths (no row)

`qwen38-27b` (Qwen3.8 27B dense, the local investigator; only local model to fix code, see
`2026-08-16-local-relay-qwen38-27b.md`) was rerun on the fixed `main` (compaction guard, Pewter fix,
battle watchdog, read cap) to get its unassisted baseline. It never got there. **There is no row**;
this file records why so nobody averages a dead stream into the tables.

| attempt | wall | how it ended | cause | evidence |
|---|---|---|---|---|
| r3 (10:52) | 8.3 m | dead stream (`stopReason: stop`, usage 0/0, thinking cut mid-sentence) | **self-inflicted**: the advisor pipeline loaded `qwen38`+`gpt-oss` on the same card mid-run; Ollama evicted the relay's model | `data/local_runs/qwen38-27b-r3.attempt/` |
| r4 (11:11) | 2.7 m | dead stream, same signature | **GPU hang**: kernel `NVRM: Xid 8 (GPU stopped processing) … RC watchdog: GPU is probably locked`; Ollama `CUDA error: the launch timed out` | `…/qwen38-27b-r4.attempt/xid.log` |
| r5 (11:17), `num_batch 256` | 5.2 m | dead stream, same signature | **GPU hang**, `Xid 8` again; power log pinned at **600 W (the limit) for the last 10 samples** before the hang | `…/qwen38-27b-r5.attempt/` |

Same failure yesterday (attempt 1, `benchmarks/2026-08-16-local-relay-qwen38-27b.md`). Never once on
the MoE models (`laguna-xs` r1/r2, `qwen3-coder`), whose GPU mean is 114–341 W; `qwen38-27b`'s
mean is ~406 W with peaks at 602–610 W, and `nvidia-smi` shows 235 s of accumulated **SW power
capping** on the card. This is an RTX 5090 on a Thunderbolt eGPU: sustained pinning at the 600 W
limit under dense-27B prompt processing hangs it (Xid 8 = GPU stopped processing, not a compute-time
watchdog — there is no display on the card).

## What this means

- **Hardware limit, not a model limit.** `qwen38-27b`'s one clean run (r2 attempt 2, 22 min) was the
  best local investigation of the weekend. It cannot be benchmarked on this box at the stock power
  limit. Fix: `sudo nvidia-smi -pl 480` (needs root; resets on reboot) — cap the card below the
  hang region and rerun. `num_batch 256` alone was not enough.
- **Runs need a Xid check.** `bench_report.py` should refuse to emit a row when the kernel log has
  an `Xid` in the run window, the same way the Ollama-journal rule (SUMMARY §4) applies. Every one of
  these looked like "the model quit" from the pi side.
- **GPU lock (shipped, PR #81)**: r3 was mine. `scripts/local_relay_run.sh` now writes
  `data/local_runs/GPU_BUSY` and `advisor.py` / `run_model_evals.py` refuse to load models while it exists.

## Next

Cap the card, rerun `RUN_TAG=qwen38-27b-r6 ASSIST=none scripts/local_relay_run.sh qwen38-27b main`
with the power sampler confirming the ceiling held, then the assisted pair (`ASSIST=both`).
