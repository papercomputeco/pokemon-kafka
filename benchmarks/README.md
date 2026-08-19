# Benchmarks

Dated results of operator-agent runs against this repo's game milestones. One file per run day
(`YYYY-MM-DD-<goal>.md`), append-only: never rewrite an old file, add a new dated one so progress
is visible over time.

Every table carries the same columns so files are comparable:

| column | meaning |
|---|---|
| segs | relay segments cleared (of 4 on the Mt. Moon chain) |
| wall | wall clock from first to last assistant turn |
| model time | sum of latency before each assistant turn (API + reasoning); the rest is tool time |
| turns / tools | assistant turns / tool calls |
| out tok/s | output tokens ÷ model time |
| s/turn | model time ÷ turns |
| input / cache read / output | tokens as reported by the provider |
| provider $ | what the provider reported (Ollama cloud is a flat subscription, local models and the Claude Max sub report $0 — not comparable) |
| cloud $ | the same tokens priced at published per-million cloud rates (`bench_report.py --rate-*`) — the cost to run this at scale; always fill this in |
| Wh / energy $ | local power from `scripts/power_sampler.py` (GPU + iGPU; CPU when RAPL is readable) integrated by `bench_report.py --power-log`, and `--kwh-price` |
| code fix | did the model change agent code (vs. only genome/config) |
| learnings / commits | `docs/learnings/*` entries and commits left on the run branch |

Local runs: start `uv run python scripts/power_sampler.py --out data/power/<run>.csv` before
launching the operator and stop it after; pass the CSV to `bench_report.py --power-log`.

How the numbers are produced: `scripts/bench_report.py <pi-session.jsonl>...` prints one row per
session from pi's transcript (`~/.pi/agent/sessions/<cwd-slug>/*.jsonl`). Game-side stats come from
each run's `data/telemetry/game/*.jsonl` (the same lines the Kafka bridge publishes).

## The harness-death guard — when there is no row

A run can be killed by the box instead of the model, and from pi's side the two are identical: the
stream goes silent and the last turn is written as an ordinary `stopReason: stop` with usage 0/0 and
nothing said. Four `qwen38-27b` attempts died this way to eGPU hangs on 2026-08-15/16
(`NVRM: Xid 8`, `CUDA error: the launch timed out`); as rows they would have read "the model quit at
3 minutes". So `bench_report.py` checks before it prints, and **refuses to emit a row (exit 3)** when
any of these hold:

| flag | where it comes from |
|---|---|
| dead stream | the session itself: final assistant turn, usage 0/0, no text and no tool call |
| kernel hang | `journalctl -k` in the run window: `NVRM: Xid`, `GPU is probably locked`, `GPU has fallen off the bus` |
| Ollama crash | `journalctl -u ollama` in the run window: `CUDA error`, `llama-server terminated`, `core dumped` |

The window starts at the run's first message and is padded only *forward* (`--hang-pad`, default
120 s): the hang that kills a run is logged at or just after its last turn, while the crash from the
run *before* this one is not this run's. (Padding backwards flagged the healthy `laguna-xs` r1 row,
which started two seconds after the previous model's Xid.) A journal that cannot be read is reported
as **unchecked**, never as clean — the row still prints, with a note saying it is not certified.

`local_relay_run.sh` captures both logs for the window into `data/local_runs/<tag>.{kernel,ollama}.log`
and passes them with `--kernel-log`/`--ollama-log`, so the check is reproducible after the journal
rotates. `--no-hang-check` skips the guard (a cloud run on a box whose GPU is busy with something
else); `--force` prints the row anyway — if you use it, label the row as an invalid attempt. **A
refused run is written up, not published**: see `2026-08-16-qwen38-27b-egpu-hangs.md`.

Harness recipe (keep it constant across models so only the model varies): pi + `scripts/pi-ext/guardrails.ts`
(default bash timeouts, 40 KB tool-result cap, web tools blocked, proactive context compaction at 75 % of the
model's `contextWindow` via pi's own compaction pipeline so a headless run no longer dies with `stopReason: length`,
plus a one-shot "commit your deliverables" nudge at 60 %; env knobs `PI_GUARD_COMPACT_AT=0.75`, `PI_GUARD_NUDGE_AT=0.6`,
`PI_GUARD_MAX_RESULT`, `PI_GUARD_DEFAULT_TIMEOUT`, `PI_GUARD_RELAY_TIMEOUT`; load with `-e scripts/pi-ext/guardrails.ts`),
the `operator_prompt_v2` mission text, one worktree per run, capture via `tapesctl start --tapes-url http://localhost:8082 pi -- ...`.
Claude models can also be run on the Claude Code harness on the Max subscription (harness axis, no
API cost); when comparing *models*, keep the harness fixed.

Assumption going in: every capable model eventually plays Pokémon; the interesting differences are
strengths — who reads code vs. tunes knobs, who writes causal learnings, who stays inside the
context window, cost and speed per unit of progress.

## Assisted vs unassisted rows

Every row is **unassisted** unless it says otherwise: the model, the mission, the guardrails
(timeouts, result cap, read cap, compaction) and nothing that carries knowledge from other runs.
The advisors (`scripts/advisor.py`) can assist a run in two opt-in ways — gated tips appended to
the mission (`ASSIST=tips`), the `consult` Oracle tool (`ASSIST=consult`), and — new — the model's own
measured operator character (`ASSIST=fit`: `references/model_fit.json` rendered by
`scripts/model_fit.py section <model>`, which tells a Driver it is a Driver and what move to make
on a wall instead of re-racing; `all` = every assist) — and both launchers put the mode in the row
label (`assist=none|tips|consult|fit|both|all`). `fit` answers a specific question: **does knowing
its own tendency change a model's behaviour?** — measured by `scripts/role_metrics.py` on the
session (probe/relay, calls before the first relay, early exit) against the same model's `none`
row. `scripts/model_fit.py update <sessions...>` folds real sessions back into the `measured`
block, so the guidance a model receives carries its own numbers.
Assisted rows answer a different question ("how much does the accumulated knowledge help this
model?") and are compared only with each other or with the same model's unassisted row. Never
average them into the model-vs-model tables.

## Run modes

Every run is a point on two axes — harness (Claude Code / pi) × model source — and each dated
file should say which. Modes we run:

| mode | harness | models | notes |
|---|---|---|---|
| `claude` | Claude Code (Max sub) | Sonnet 5 / Opus 5 / Haiku 4.5 | harness axis; capture with `tapesctl start --tapes-url http://localhost:8082 claude -- ...` |
| `local` | pi | Ollama local roster (below) | start `power_sampler.py`; inference on the RTX 5090 |
| `all-pi` | pi | local + cloud, incl. Claude via pi's anthropic provider | the only mode that is a pure model-vs-model comparison |
| `cloud` | pi | Anthropic API + Ollama cloud | Ollama cloud allows **3 cloud models at a time** — plan batches |
| `mixed` (default) | Claude Code for Claude, pi for the rest | | tag rows with the harness; compare models only within pi rows |

Not in scope for now: OpenRouter (extra provider/keys) and stereOS VM isolation — worktrees are the
isolation unit.

## Local roster (Ollama on the RTX 5090)

Question: can an open model running on the box — pushing the GPU's power budget — get comparable to
Haiku 4.5 (91.9 out tok/s, 4.8 s/turn, 2/4 segments, $0.87)? `scripts/local_models.py` holds the
roster and the plumbing:

```
uv run python scripts/local_models.py list        # roster, what is pulled, what has a -128k variant
uv run python scripts/local_models.py pull        # ollama pull the base tags (some need Ollama ≥ 0.32)
uv run python scripts/local_models.py create      # <alias>-128k variants with an explicit num_ctx (default 128k)
uv run python scripts/local_models.py register    # add the variants to ~/.pi/agent/models.json
uv run python scripts/local_models.py bench       # decode tok/s, prompt tok/s, GPU %, VRAM, peak W
```

The roster is **Blackwell-runnable only**: `check_runnable()` rejects Apple-only distribution
formats (`mlx`, and the `nvfp4` FP4 builds Ollama's registry gates to macOS) before a pull, and
models that cannot stay GPU-resident at 128k are dropped rather than benched — `qwen3:8b` went for
this reason (40k native context, so 128k of KV outgrows the model; 81 % resident, 48 tok/s).

Models are grouped into **comparison classes** (`moe-30b`, `dense-27b`, `baseline`) because
decode speed tracks *active* parameters, not total size — a 30B-A3B MoE and a 27B dense model are
different questions even though both fit the card. Compare rows within a group; `list`/`bench` print
one table per group and every subcommand accepts a group name in place of aliases
(`... bench moe-30b`). Each bench table repeats the Haiku 4.5 target row so a group is read against
the thing it has to beat.

`bench` is the gate before a 2.5 h run: a model that shows **CPU spill** at 128k ctx or decodes under
~40 tok/s will not get near Haiku's cadence. `nvfp4` tags are Blackwell-native FP4 — the 5090 angle;
Blackwell `nvfp4` tags would be the obvious 5090 play, but Ollama's registry 412s them with "this\nmodel requires macOS" (checked 2026-08-15), so the Linux path is the plain Q4/MXFP4 tags. Same `num_ctx` for
every model you compare (128k from now on; the 2026-08-15 rows were 64k); Ollama truncates the *front* of the
prompt when it overflows, so `contextWindow` in `models.json` is set to the same value.

**Power.** The card is an RTX 5090 on a Thunderbolt eGPU, and it hangs (kernel `Xid 8`, "GPU is
probably locked") when a dense 27B pins it at the stock 600 W limit — four times on 2026-08-15/16, see
`2026-08-16-qwen38-27b-egpu-hangs.md`. The roster carries this as data: a `Spec.power_w` is the cap
that model needs, `list` shows it in the `power` column, and `local_models.py power [alias...]` reads
`nvidia-smi`'s enforced limit and exits 1 for any model whose cap is not applied. `local_relay_run.sh`
runs that preflight and **refuses to start** a refused model (`POWER_OVERRIDE=1` runs anyway; that row
is not a verdict). `nvidia-smi -pl` resets on reboot, so it is checked at every launch rather than
trusted from the last time; make it stick with the oneshot unit (needs sudo, once):

```
sudo cp scripts/nvidia-power-cap.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now nvidia-power-cap.service
```

or apply it for this boot only with `sudo nvidia-smi -pl 480`. Either way `local_models.py power
qwen38-27b` must say `ok` before r6.

128k of KV cache next to a ~20 GB model only fits on the 32 GB card with flash attention and a
q8_0 KV cache; install `scripts/ollama-ctx.conf` as a systemd drop-in once (needs sudo):

```
sudo mkdir -p /etc/systemd/system/ollama.service.d && sudo cp scripts/ollama-ctx.conf /etc/systemd/system/ollama.service.d/ctx.conf && sudo systemctl daemon-reload && sudo systemctl restart ollama
```
