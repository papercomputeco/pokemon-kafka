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

Harness recipe (keep it constant across models so only the model varies): pi + `guardrails.ts`
(default bash timeouts, 40 KB tool-result cap, web tools blocked), the `operator_prompt_v2` mission
text, one worktree per run, capture via `tapesctl start --tapes-url http://localhost:8082 pi -- ...`.
Claude models can also be run on the Claude Code harness on the Max subscription (harness axis, no
API cost); when comparing *models*, keep the harness fixed.

Assumption going in: every capable model eventually plays Pokémon; the interesting differences are
strengths — who reads code vs. tunes knobs, who writes causal learnings, who stays inside the
context window, cost and speed per unit of progress.
