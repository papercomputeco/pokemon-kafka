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

## The guard shipped — and corrected this file's own r3 row

`bench_report.py` now refuses to print a row for a run that died on the harness (exit 3), on three
flags: the **dead stream** in the session itself (final assistant turn, usage 0/0, nothing said), a
**kernel hang** (`NVRM: Xid`, `GPU is probably locked`, `GPU has fallen off the bus`) and an **Ollama
crash** (`CUDA error`, `llama-server terminated`, `core dumped`) inside the run window. See
`benchmarks/README.md` § The harness-death guard. Replayed over every session on this box:

| session | guard | outcome |
|---|---|---|
| `laguna-xs` r1, `laguna-xs` r2, `qwen3coder` | clean | row printed, unchanged from the published tables |
| `qwen38-27b` r3, r4, r5 | dead stream + kernel + Ollama | **no row** (exit 3) |

Three published rows in, three dead attempts out, on the evidence alone — no judgement call.

**The correction:** the table above calls r3 *self-inflicted* — the advisor pipeline loaded a second
model and Ollama evicted the relay's. The kernel disagrees, or rather adds to it. The full Xid list
for the weekend is four events, all `llama-server`, each one at the exact second a run's stream died:

```
Aug 15 21:27:01  NVRM: Xid (PCI:0000:01:00): 8, pid=923559   → qwen38-27b attempt 1
Aug 16 10:05:03  NVRM: Xid (PCI:0000:01:00): 8, pid=1773658  → r3   (last turn 10:05:03)
Aug 16 10:14:16  NVRM: Xid (PCI:0000:01:00): 8, pid=1816640  → r4   (last turn 10:14:16)
Aug 16 10:22:31  NVRM: Xid (PCI:0000:01:00): 8, pid=1834402  → r5   (last turn 10:22:31)
```

So the weekend was **four** GPU hangs, not three plus an eviction: on r3 the double model load is
most likely what pushed the card over, but what actually ended the run was the same Xid 8 as r4 and r5. The GPU lock
(PR #81) was still the right fix for the double load; the cause column was half the story. This is
the guard's first finding, and it is the argument for it — the r3 diagnosis was written by reading
the pi session and the Ollama log, which is exactly the evidence that *cannot* distinguish these
cases. The kernel log can, and now nothing gets a row without it.

The conclusion is unchanged and now better supported: **the card cannot sustain the dense 27B at its
stock 600 W limit.** Cap it (`sudo nvidia-smi -pl 480`) before r6.

The cap is now enforced rather than remembered: `qwen38-27b` carries `power_w=480` in the roster,
`local_models.py power qwen38-27b` checks the card's enforced limit against it, and the launcher
refuses to start until it says `ok` (`POWER_OVERRIDE=1` to run anyway — not a verdict row).
`scripts/nvidia-power-cap.service` makes the cap survive a reboot; see `benchmarks/README.md` § Power.

## r6 at 480 W: hung anyway — and the guard caught it, and the stack says why

First run with both guards live. Preflight: `enforced power limit: 480 W — ok qwen38-27b`. Then:

| attempt | wall | how it ended | power log | guard |
|---|---|---|---|---|
| r6 (13:27), **capped 480 W**, `num_batch 256` | 8.1 m, 32 turns | dead stream, same signature | mean 397 W, max 491 W, **71 of 98 samples ≥ 470 W**, the last five pinned at 480 | **no row**, exit 3: dead stream + kernel `Xid 8` 13:35:58 + Ollama `CUDA error` |

So the power hypothesis fails its test: the cap held (never over 491 W, no HW slowdown), the card
sat *at* the cap for most of the run, and it hung the same way. Capping lower is a guess with no
evidence behind it now. Evidence in `data/local_runs/qwen38-27b-r6.attempt/`.

Two things worth the eight minutes. **The run itself was the best local relay so far**: batons for
`route1_to_forest`, `forest_to_pewter` *and* `pre_brock` in under 8 minutes — 2/4 and inside the Gym
faster than any 08-15 model — plus two learnings committed on the branch, and it was mid-diagnosis of
the Brock fight ("Lv11 Geodude, HP 29→12→6 → faint, white-out, re-walk the whole journey") when the
card died. No row, but this is the model to get running.

**And the crash stack is the same in all five dumps.** Reading the Ollama journal past the
`CUDA error` line — which nothing had done before the guard forced the question — every core dump
(08-15 attempt 1, r3, r4, r5, r6) ends in:

```
ggml_cuda_error
llama_context::synchronize
llama_get_embeddings_nextn
common_speculative_impl_draft_mtp::process
```

That is **Ollama's MTP speculative decoding** for Qwen3.8 — the upstream Modelfile ships
`draft_num_predict 4`, and the load log says `adding speculative implementation 'draft-mtp'` (draft
acceptance 0.44–0.75, mean draft length ~3). Five for five in the draft path, on a card that has
never hung under any non-MTP model. Power was a correlate (the dense 27B is also the hottest model);
the MTP head is the suspect with the fingerprint.

`draft_num_predict 0` disables it — verified: Ollama logs `no implementations specified for
speculative decoding` and generates normally. It is now in the roster Spec for `qwen38-27b` and the
`-128k` variant is rebuilt. Cost: MTP was worth up to ~1.5–2× on decode, so r7 will be slower per token.

## Next (revised)

r7 = r6 with exactly one change: no MTP draft. Cap stays at 480 W so attribution is clean.
`RUN_TAG=qwen38-27b-r7 ASSIST=none scripts/local_relay_run.sh qwen38-27b main`. If r7 survives, r8
at 600 W (no MTP) says whether the cap ever mattered. If r7 hangs too, it is not power and it is not
MTP, and the next suspect is the Thunderbolt link under dense prompt processing — at which point
`qwen38-27b` is off this box until the driver or the enclosure changes.
