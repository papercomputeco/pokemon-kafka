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

Harness recipe (keep it constant across models so only the model varies): pi + `scripts/pi-ext/guardrails.ts`
(default bash timeouts, 40 KB tool-result cap, web tools blocked; load with `-e scripts/pi-ext/guardrails.ts`), the `operator_prompt_v2` mission
text, one worktree per run, capture via `tapesctl start --tapes-url http://localhost:8082 pi -- ...`.
Claude models can also be run on the Claude Code harness on the Max subscription (harness axis, no
API cost); when comparing *models*, keep the harness fixed.

Assumption going in: every capable model eventually plays Pokémon; the interesting differences are
strengths — who reads code vs. tunes knobs, who writes causal learnings, who stays inside the
context window, cost and speed per unit of progress.

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

128k of KV cache next to a ~20 GB model only fits on the 32 GB card with flash attention and a
q8_0 KV cache; install `scripts/ollama-ctx.conf` as a systemd drop-in once (needs sudo):

```
sudo mkdir -p /etc/systemd/system/ollama.service.d && sudo cp scripts/ollama-ctx.conf /etc/systemd/system/ollama.service.d/ctx.conf && sudo systemctl daemon-reload && sudo systemctl restart ollama
```
