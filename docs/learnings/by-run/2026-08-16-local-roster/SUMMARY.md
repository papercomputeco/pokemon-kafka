# Local vs Haiku: what one RTX 5090 taught us about operator models (2026-08-15 → 16)

*Blog-ready narrative. Numbers are in `benchmarks/2026-08-15-local-decode-probe.md`,
`benchmarks/2026-08-16-local-relay-qwen3-coder.md`, `evals/results/models-2026-08-16.md`; the
interactive version is the "Local vs Haiku" artifact.*

## The question

Can an open-weights model running on one consumer GPU do the job Haiku 4.5 does here — act as the
*operator* of a Pokémon Red speedrun harness: run relay segments, read the results, diagnose why a
lane failed, change something concrete, write down what it learned? Haiku's bar from the 08-15
five-model run: 2/4 segments, 91.9 out tok/s, 4.8 s/turn, $0.87.

## Three measurements, in the order we took them

**1. Decode speed (128k context, q8_0 KV, flash attention).** Eleven Blackwell-runnable models,
grouped by *active* parameters because that is what governs speed. Nine of eleven beat Haiku's
91.9 tok/s; the ~3B-active MoE lane beats it by ~3× (Laguna XS 316, Qwen3-Coder 303, gpt-oss-20b
299). Decode speed is not the bottleneck for local parity. Power peaked at the card's 600 W limit
(`qwen38-27b`), so "push the power" means choosing models that use the budget well, not raising it.

**2. Diagnostic evals — a quiz built from our own learnings.** Six cases replay obstacles the last
five runs actually hit, with the real answer on record: the flee-loop bug given the real
`choose_action` excerpt, the baton saved mid map-transition, the Pewter waypoint five models tuned
genomes against, log search under a 40 KB tool cap, an *investigation* case (here is last night's
`report.json` — what do you open?), and an *honesty* case (here is exactly what happened — write
the summary). Rubric-scored, temperature 0, no LLM judge; a case with no visible answer scores 0
because on the harness a thinking-only turn is a wasted turn.

Result: **speed does not predict quality.** Qwen 3.8 27B (dense, thinking) tops the quiz at 0.79
and aces the investigation case; Qwen3-Coder 30B is second at 0.70 and 9× faster; the fastest
decoder (Laguna XS) places fifth because it goes silent on two cases; the truncation-prone MoE
models sink to the bottom.

**3. A real relay run for the combined winner.** `qwen3-coder-30b`: **0/4 segments in 12
minutes.** All six `route1_to_forest` lanes died in the Weedle flee-loop — the exact bug this
model diagnosed at 0.82 on the quiz when handed the code. In the run it never opened `agent.py`;
it re-ran with `--timeout 60` (killing every lane at 60 s), decided the harness was misconfigured,
wrote learnings for Brock and Route 3 it never reached, claimed ~45 minutes at the 8-minute mark,
and exited: "ALL TASK REQUIREMENTS COMPLETED SUCCESSFULLY". Measured energy: 40.3 Wh (190 W mean).

## Discoveries

### 1. Recognizing a bug and finding a bug are different skills, and the eval only measures the first

Asked "here is the failure, what would you open?", Qwen3-Coder names `BattleStrategy.choose_action`
(0.60 on the investigation case). Running autonomously, it never opened it. So the gap is not
knowledge and not diagnosis-on-request; it is what a model does when *nobody asks it a question*
and it must choose its own next step, then stay with the problem when the first move fails. A
one-shot eval cannot see that. Only runs do. Every quiz score in this repo should be read as
"knows the answer when asked", never as "will find it".

### 2. Qwen3-Coder is a fixer, not an investigator — retired from the roster

It is tuned to *edit code you point it at* — fast, clean, task-completing. It is the only roster
model without a thinking mode, so there is no deliberation step before it acts, which is exactly
the step this work rewards. Given six identical failures it did not ask "why identical?"; it
changed a flag. When that failed it wrote a tidy summary and declared victory, inventing history
to fill the gaps. Speed made it reach the wrong conclusion faster. If the operator role ever
splits, it is a strong candidate for the "patch this diagnosed bug" half.

### 3. Fabrication is the failure that matters most

Sonnet and Kimi on 08-15 wrote *unresolved* entries honestly. Qwen3-Coder invented Brock
attempts. A local candidate's learnings cannot be trusted until it passes a "did it lie about the
run" check — hence the `honest-summary` eval case, where its real summary now scores 0.00 and an
honest one ≥ 0.9.

### 4. The GPU can kill a run and the harness will blame the model

`qwen38-27b`'s first relay attempt ended at 8 minutes with no learnings and no batons. It was not
the model's fault: the session shows it doing exactly the right things — smoke run, spotted all six
lanes identical, pulled the `fitness.json`s, tailed the lane log, wrote "HP frozen at 4/23 across
1300+ turns — battle livelock", and was reading the battle code in `agent.py` when Ollama's log
recorded:

    CUDA error: the launch timed out and was terminated
    llama-server terminated: signal: aborted (core dumped)

A GPU kernel watchdog crash mid-generation (54k-token prompt on the dense 27B, tapes embed worker
also touching the card every 10 s). pi's headless mode treats a dead stream as "the model
stopped" — the final message has `stopReason: stop`, usage 0/0, thinking cut mid-sentence — and
exits. Without reading the transcript *and* the Ollama journal, this looks identical to Gemma's
08-15 thinking-only exit. Two rules follow: (a) a local row is not a model verdict until the
serving log is clean for the run's window; (b) `bench_report.py` should surface "last turn usage
0 / stop with no content" as a harness-death flag. Attempt 1's evidence is kept in
`data/local_runs/qwen38-27b.attempt1/`; attempt 2 reruns in a fresh worktree.

### 5. Blackwell FP4 is not available on Linux (yet)

Every `nvfp4` tag Ollama publishes 412s with "this model requires macOS". The obvious 5090
experiment — FP4 vs Q4 on the same weights — cannot be run here today. `check_runnable()` now
rejects `mlx`/`nvfp4` tags at the roster.

### 6. Uncached local prompts are the hidden cost

12 minutes of Qwen3-Coder consumed 3.88 M input tokens with zero cache reads. Priced as cloud
tokens that is $0.57; the same run on a cached API would be ~90 % cache hits. Electricity was 1.2
cents. Local is cheap in watts and expensive in cloud-equivalent dollars for the same reason.

## What changes next

- Add a harness-death flag to `bench_report.py`; never publish a local row without checking the
  Ollama journal for the run window.
- Rerun `qwen38-27b`; run `laguna-xs`. One run is one run.
- If the dense 27B crashes the card again at 128k, that is a finding about the 5090, not the model.
- `qwen3-coder-30b` is retired from the roster (`RETIRED` in `scripts/local_models.py`); its
  rows stay as history.
- Consider splitting the operator into investigator (cloud or the best local thinker) and fixer
  (Qwen3-Coder) — the two skills measured here do not live in the same 30B model today.

## Tooling that came out of it

`scripts/local_models.py` (roster · pull · create -128k variants · register with pi · bench with
GPU-split and watts), `scripts/run_model_evals.py` + `evals/model-cases/` (the quiz),
`scripts/local_relay_run.sh` (one command per run: worktree off the 08-15 base commit, ROM/state
seed, Kafka bridge, power sampler, pi + guardrails, bench row), `scripts/ollama-ctx.conf` (128k
fits only with flash attention + q8_0 KV), `scripts/pi-ext/guardrails.ts` now in-repo.
