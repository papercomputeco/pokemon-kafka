# 2026-08-15 — local decode probe (RTX 5090, 128k ctx)

Not a game run: a pre-flight probe of the local roster before spending 2.5 h per model on the Mt.
Moon relay. Question: can a model that runs on this box get **comparable to Haiku 4.5** — 91.9 out
tok/s, 4.8 s/turn, 2/4 segments, $0.87 (2026-08-15 relay row)?

Setup: Ollama 0.32.13, `OLLAMA_FLASH_ATTENTION=1` + `OLLAMA_KV_CACHE_TYPE=q8_0`
(`scripts/ollama-ctx.conf`), every model rebuilt as `<alias>-128k` with an explicit `num_ctx`
(131072). Numbers from `uv run python scripts/local_models.py bench` — a 400-token generation on a
short operator-style prompt, best of two (first warms the load), power sampled at 2 Hz from
`nvidia-smi` during the probe. GPU % is `ollama ps` `size_vram / size`; anything under 100 spilled
to CPU and is disqualified before a run.

Rows are grouped by comparison class because decode speed tracks *active* parameters, not total
size. Compare within a group.

## moe-30b — ~30B total / ~3B active

| model | out tok/s | prompt tok/s | GPU % | resident GB | peak W | mean W |
|---|---|---|---|---|---|---|
| _Haiku 4.5 (target)_ | _91.9_ | | | | | |
| `laguna-xs-128k` | **315.8** | 7,662 | 100 | 20.9 | 354 | 340 |
| `qwen3-coder-30b-128k` | **302.7** | 15,189 | 100 | 25.6 | 359 | 341 |
| `gpt-oss-20b-128k` | **299.2** | 26,502 | 100 | 13.6 | 488 | 443 |
| `qwen35b-128k` (baseline) | 251.9 | 2,498 | 100 | 24.4 | 331 | 302 |
| `qwen36-35b-128k` | 255.6 | 2,596 | 100 | 24.4 | 349 | 321 |
| `glm47-flash-128k` | 242.7 | 12,302 | 100 | 23.0 | 359 | 335 |
| `nemotron35-lightning-128k` | 215.0 | 3,577 | 100 | 25.5 | 299 | 285 |

(`qwen36-35b` is a 35B MoE and sits with the MoE rows on speed; it is listed under `dense-27b` in
the roster only because that is where the roster put its generation, which the next revision should
fix.)

## dense-27b — full weights decoded per token

| model | out tok/s | prompt tok/s | GPU % | resident GB | peak W | mean W |
|---|---|---|---|---|---|---|
| _Haiku 4.5 (target)_ | _91.9_ | | | | | |
| `qwen38-27b-128k` | 130.0 | 643 | 100 | 17.9 | **602** | 233 |
| `muse-glimmer-128k` | 81.4 | 3,784 | 100 | 16.7 | 569 | 549 |
| `gemma4-31b-128k` | 67.3 | 1,583 | 100 | 20.8 | 573 | 546 |

## baseline — the 2026-08-15 rows, rebaselined at 128k

| model | out tok/s | prompt tok/s | GPU % | resident GB | peak W | mean W |
|---|---|---|---|---|---|---|
| `gemma4-128k` (E4B) | 233.9 | 6,580 | 100 | 4.1 | 380 | 345 |

Dropped from the roster after this probe: `qwen3:8b` — 48.3 tok/s at **81 % resident** (CPU spill).
Its native context is 40k, so a 128k q8_0 KV cache is larger than the model itself; it is slower
than models 4x its size and is not worth a run slot. The roster is now Blackwell-runnable only:
`check_runnable()` rejects `mlx` and `nvfp4` tags before a pull, and a test asserts no roster entry
carries them.

## Reading

- **Decode speed is not the bottleneck.** Every model kept on the roster beats Haiku's 91.9 out
  tok/s at 128k context except `gemma4-31b` (67); four clear it by ~3×. If a local run is slow end-to-end, the cause is turns and tool time,
  not tokens per second — which is what the 2026-08-15 rows (Qwen 20 tok/s at 64k) hid.
- **Group membership is a measurement, not a label.** `muse-glimmer:30b` is published as a 30B
  agentic model and was rostered as MoE; it decodes at 81 tok/s drawing 549 W mean — dense-model
  behaviour (`ollama show` reports 27.9B on a `muse-glimmer` architecture, no sparse routing). It
  now sits in `dense-27b`, where it is the slowest entry that still beats nothing: it is *below*
  Haiku's 91.9 tok/s.
- **Poolside's Laguna XS 2.1 is the fastest thing on the box** — 315.8 tok/s at 340 W, 33.4B-A3B
  with a 262k native context, so the 128k harness constant costs it nothing. It is the only model
  here built explicitly for local agentic coding; first pick for a relay run.
- **MoE is the fast lane.** Every ~3B-active model clears 240 tok/s; the dense 27-31B models land at
  130 and 67. `gemma4-31b` is the slowest *and* the hungriest (546 W mean) — a bad trade unless its
  answers are markedly better.
- **The card, not the model, sets the ceiling.** `qwen38-27b` touched the 600 W cap
  (`power.max_limit` = 600 W, default = 600 W, so there is no headroom to raise). Peak W is a
  short spike; mean W over the probe is what the energy column should use.
- **Prompt throughput on this probe is noisy.** The prompt is short, so a cold load can report
  absurd numbers (nemotron measured 22.6 prompt tok/s cold, 3,577 warm). Trust the out tok/s column
  and re-run with `--repeat 3` before believing a prompt-side outlier.
- **q8_0 KV + flash attention is what makes 128k fit.** Every roster model stayed 100 % resident;
  the one that did not (`qwen3:8b`) was dropped rather than run at a different context, since a
  different `num_ctx` would not be comparable anyway.
- **`nvfp4` is not available on Linux.** Every Blackwell FP4 tag (`qwen3.8:27b-nvfp4`,
  `muse-glimmer:30b-nvfp4`, `nemotron-3.5-lightning:30b-a3b-nvfp4`, `qwen3.6:27b-coding-nvfp4`) 412s
  from Ollama's registry with "this model requires macOS" — the FP4-vs-Q4 A/B is not runnable here.
  The plain Q4/MXFP4 tags are the Linux path, and `mlx`/`nvfp4` tags are now blocked at the roster.

## Follow-on: does speed predict diagnosis quality? (no)

`scripts/run_model_evals.py` scored the same models on four learnings-derived diagnostic cases the
same day (`evals/results/models-2026-08-16.md`). The ranking barely correlates with tok/s:

| model | eval overall | no answer | out tok/s | wall s |
|---|---|---|---|---|
| `qwen38-27b` | **0.79** | 0 | 141 | 99.8 |
| `qwen3-coder-30b` | **0.69** | 0 | 290 | 10.6 |
| `muse-glimmer` | 0.61 | 0 | 80 | 172.2 |
| `gemma4-31b` | 0.61 | 0 | 66 | 118.2 |
| `gpt-oss-20b` | 0.57 | 0 | 292 | 26.2 |
| `laguna-xs` | 0.42 | 2 | 303 | 41.1 |
| `glm47-flash` | 0.06 | 3 | 223 | 71.4 |

The fastest decoder on the box (`laguna-xs`, 316 tok/s) placed 7th because it spent its whole
output budget thinking and emitted no visible answer on two of four cases. `qwen3-coder-30b` is the
standout on the combined axes: second on quality, answered every case, and did it in 10.6 s of wall
clock — 9x faster than the model above it. `gpt-oss-20b` scored 0.00 on the code-reading case by
fabricating a code fact (claimed wild battles are `battle_type == 0` while the excerpt in its own
prompt shows `== 1`), which is worse than being slow.

## Next

Relay runs (`local` mode): `qwen3-coder-30b` went first (fast *and* answers) and was retired from
the roster after it — see `2026-08-16-local-relay-qwen3-coder.md`; `qwen38-27b` (best diagnoses)
and `laguna-xs` (fastest decode) follow — with `power_sampler.py` running, so
the Wh and energy-$ columns are measured rather than estimated. Pending pulls:
Thinking Machines' Inkling is deliberately not on the roster: the flagship is 975B-A41B and even
`Inkling-Small` (276B-A12B) is ~75 GB at its smallest quant, so it cannot stay GPU-resident on a
32 GB card. It belongs to a `cloud` batch (Tinker API), not a local one.
