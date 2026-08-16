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

### 5. Laguna XS matched Haiku's cadence and segments — and the quiz had ranked it fifth

Poolside's Laguna XS 2.1 (33B-A3B), the fastest decoder on the roster and only fifth on the eval
quiz (silent on two cases, weakest honest-summary), ran the relay for 40 minutes: **2/4 segments,
91.1 out tok/s in-run against Haiku's 91.9, 4.0 s/turn against 4.8, 77.5 Wh (2.3 ¢).** It hit
the same flee-loop wall as Qwen3-Coder and did not blame the harness: it manufactured a healed
seed state, cleared Route 1 → Forest and Forest → Pewter, then stalled on the known Pewter Gym
wedge like every 08-15 model. One honest, well-formed learning; no fabrication; no code fix. It
ended because the 128k window filled (`stopReason: length` at 130,820 tokens, 8.4 M uncached input)
while it was grepping the right file — a harness limit, not a judgement failure. So the quiz
mis-ranked it in the other direction: its truncations measured a thinking budget, not a behaviour.
Runs are the instrument; the quiz is the screen. See `benchmarks/2026-08-16-local-relay-laguna-xs.md`.

### 6. Qwen 3.8 fixed the bug — the first local model to change code — and then ran out of context

Attempt 2 (clean, no GPU errors): it reproduced the stall with a single 60-turn lane, diagnosed it
as an input-locked battle screen, wrote a 40-line battle-wedge watchdog in `agent.py`, ran the
relay tests and lint *before* trusting it, and re-ran the segment: **all six lanes cleared in 740
turns** (from 2000 stuck). Sonnet and Kimi were the only 08-15 models that changed code; Qwen 3.8
is the only local one, and it validated its change. Then the 128k window filled at turn 91 —
130,851 tokens, `stopReason: length`, exactly where Laguna died an hour earlier — with no learning
written and nothing committed. **1/4, 22 min, 156 Wh (406 W mean; a dense 27B at 128k runs the
card hot).** It is the local Sonnet, not the local Haiku: slow, expensive, and the one that does
the hard thing.

Two productive runs in a row ended on the same harness limit. pi compacts only after a 400; local
Ollama models return `length` instead; one compaction was not enough for either. A compaction
guard at ~75 % of the window is now the highest-value fix in this repo — both models had ~1.5 h of
budget left. See `benchmarks/2026-08-16-local-relay-qwen38-27b.md`.

### 7. "Stuck in the Pewter Gym" was the Pokémon Center all along

Every model that reached Pewter — five on 08-15, Laguna today — then "stalled in the Gym interior
at map 58". Map 58 is the **Pewter Pokémon Center** (`relay.py` says so: `PEWTER_GYM = 54`); the
08-15 Haiku learning mislabelled it and six write-ups repeated the label. What the lanes actually
do is walk into the Center, heal to full, then stand at (11,3) pressing "up" into the counter for
~3000 turns. Captured as a savestate and reproduced in isolation as `evals/cases/pewter-pokecenter-exit`
(stuck streak 2912/3000, 31 HP). The Brock leg has never been blocked by the Gym; it is blocked by
leaving the Pokécenter. Wedges make good evals — this one took ten minutes to turn into a
permanent regression case, and Qwen 3.8's battle-wedge watchdog was likewise checked against
`route1-flee-loop`: the loop breaks (Forest in 916 turns vs. never), the health criterion still fails.
A second new case, `low-hp-wild-battle`, seeds the agent *inside* the Weedle battle at 4/23 HP: on
`main` it sits there for 600 turns with 0 encounters; with the watchdog it wins 8 battles and is
still on Route 2 at 2 HP. Two different failures, one row each — the eval now tells "frozen" from
"alive but too weak", which is exactly the split between the wedge fix and the cap-and-fight fix.

### 8. Blackwell FP4 is not available on Linux (yet)

Every `nvfp4` tag Ollama publishes 412s with "this model requires macOS". The obvious 5090
experiment — FP4 vs Q4 on the same weights — cannot be run here today. `check_runnable()` now
rejects `mlx`/`nvfp4` tags at the roster.

### 9. Uncached local prompts are the hidden cost

12 minutes of Qwen3-Coder consumed 3.88 M input tokens with zero cache reads. Priced as cloud
tokens that is $0.57; the same run on a cached API would be ~90 % cache hits. Electricity was 1.2
cents. Local is cheap in watts and expensive in cloud-equivalent dollars for the same reason.

## What changes next

- Add a harness-death flag to `bench_report.py`; never publish a local row without checking the
  Ollama journal for the run window.
- Ship the compaction guard, then rerun Laguna and Qwen 3.8 — both have most of their budget left.
- Review Qwen 3.8's battle-wedge watchdog for `main`; it is a real fix with passing tests.
- Harness: trigger compaction at ~75 % of the window from the guardrails extension (pi only compacts on a
  400, and local models return `length` instead); remind the operator to commit deliverables early.
  **Done (feat/guardrails-compaction):** `scripts/pi-ext/guardrails.ts` now compacts at
  `PI_GUARD_COMPACT_AT` (default 0.75) of `contextWindow` from the `context` hook using pi's own
  `prepareCompaction`/`compact` + `appendCompaction`, and sends a one-shot nudge at `PI_GUARD_NUDGE_AT`
  (default 0.6). Verified on an 8k-window model: compaction fired at 6257/8000, next input dropped to
  2774, run continued to `stop`. (pi's own threshold compaction only runs at `agent_end`, i.e. after a
  headless run has already ended; `ctx.compact()` aborts the in-flight run, hence the `context`-hook path.)
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

### 10. Compaction amnesia — where a model stops being a fit for the operator role

With the compaction guard, the Pewter fix and the battle watchdog all on `main`, Laguna XS ran
again (r2). It cleared Route 1 → Forest → Pewter, walked past the Pokécenter **into the Gym** — the
first run ever inside map 54 — fought a Gym trainer (`pre_brock.state`; not Brock — every lane then
wedged on the Gym's "pilot north" fallback flagged in PR #75), and wrote a learning that named that
bug on its own. Final row: 2/4 + inside the Gym, 36.7 min, 398 turns, 3.3 s/turn, 12 compactions,
204 Wh, ended by choice ("The fix is complete") — see `benchmarks/2026-08-16-local-relay-laguna-xs-r2.md`. Then it stalled in a new way:
it read `agent.py` whole via pi's `read` tool (each read hits the 40 KB cap ≈ 10k tokens), the
window filled, the guard compacted 100k → 15k every ~2 minutes, and each summary dropped what it
had just read — so it read it again. In its last 30 tool calls: 17 reads (agent.py ×8), one relay
call, zero edits. Alive, but not progressing.

Two halves, as before. **The harness half is cheap and now fixed:** guardrails caps un-ranged
`read` calls at `PI_GUARD_READ_LIMIT` (200 lines; the model pages with offset/limit), the same way
it already blocks `cat agent.log`. **The model half is a fit verdict**, and it should be written
down, not argued with:

| model | fit as the operator | why |
|---|---|---|
| Sonnet 5 / Kimi K2.6 (cloud) | investigator | read code, fixed code, honest unresolved entries |
| Haiku 4.5 (cloud) | driver, not investigator | fast, honest, tunes knobs; never opened the code |
| **qwen38-27b** (local) | investigator, needs the guard | the only local code fix, validated first; slow (9.9 s/turn), runs the card at 400 W |
| **laguna-xs** (local) | driver | Haiku's cadence and segments; honest; reached Brock; poor context discipline — whole-file reads, so it needs the read cap and forgets across compactions |
| qwen3-coder-30b (local) | not a fit — retired | fabricated run history, no investigation |
| glm/nemotron/qwen35b/qwen36 (local) | not a fit | went silent (thinking budget) on the quiz; not run |

The honest generalisation: below ~30B active, "reads the whole file" is a habit the harness has to
cap for the model, and "remembers across compactions" is something no local model here does. That
is a limitation to document and design around (smaller reads, deliverables committed early, a
learning written per obstacle *before* the next relay call), not one to keep re-testing. Where a
model is a **driver** — Haiku, Laguna — pair it with an investigator for the code fixes; where it is
an **investigator** — Sonnet, Qwen 3.8 — give it the budget and the guard. `qwen38-27b` on the
fixed `main` is the next run worth the electricity.

### 11. Advisors and a gate — the operator no longer grades its own homework

The operator wrote its own learnings; the fabricated Brock entries and Laguna's "✅ FIXED" were the
cost. `scripts/advisor.py` adds the missing roles after `pcc-labs/inception`: an **Investigator**
(write path — reads one session plus the worktree's ground truth, asks the Oracle first, dreams a
tip + eval + learning, repairs its own rubric), a **gate** (control vs treatment on fresh models; the
tip is the only variable; PASS needs mean lift and one model that can act on it), an **Oracle** (read
path — cites learnings, evals, benchmarks and tapes sessions or says NO PRECEDENT; exposed to the
operator as `consult`), and **promote** (only gated proposals reach `evals/`, `docs/learnings/`,
`docs/prompts/tips.md`).

Then the split that `pcc-labs/inception` #18 made at the source: the **Investigator** extracts the tip
and never writes the exam; a separate **Architect** (a different model) designs the eval from the tip
alone and hardens its rubric against probe answers it writes itself. Same session, four gate runs:
single-mind design failed twice (leaked answer; rubric ≠ own tip), split design failed once (a literal
rubric scored the exact command as 0), split + hardened design passed — Laguna 0 → 1.00, gpt-oss
0 → 1.00, Gemma already knew. The gate is the point; the roles are how you get a yes worth acting on.

First real pass over the Laguna r2 session with Qwen 3.8 as Investigator: it did *not* re-propose the
Gym bug — the Oracle already had it — and instead named the process failure: "declared the fix
complete after tests + lint; the relay report still shows `pewter_to_badge=None`". The gate rejected
its first two rubrics (one leaked the answer into the prompt so control already scored; one did not
match its own reference), the repair loop fixed the third, and the gated result was **Laguna
0.00 → 1.00 with the tip**, gpt-oss and Gemma 0 → 0.2. That tip is now the first line of
`docs/prompts/tips.md`. Both assists are **opt-in** (`ASSIST=tips|consult|both` on the launcher;
default `none`) so unassisted rows keep measuring the model alone — an assisted run answers "how much
does the accumulated knowledge help *this* model?", which is a different row, labelled as such.
