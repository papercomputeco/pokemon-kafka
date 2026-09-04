# Self-learning and wedge driving: what the infra already does, where I went around it, and the fix

Written after a day that won HM03 + HM04 and measured Route 20 and Seafoam to the boulder puzzle,
while also burning a session limit on process mistakes. This is the study the operator asked for:
the mechanics of the pipeline as built, the classes of mistake I made against it, and the smallest
changes that make each class structural rather than a matter of remembering.

## 1. The machinery, as it exists (read, not recalled)

`docs/expedition-spec.md` ranks three loops by measured evidence:

| loop | what drives it | verdict in the spec |
|---|---|---|
| genome subloop (`healer.py`, `alerts-consumer`) | fitness rules and Flink alerts → parameter races on knobs (`door_cooldown`, `bt_restore_threshold`, …) | ~2,000 patches, **zero attributable outcome changes** — "every wall so far was code, not a knob" |
| within-run hypothesis loop (`agent.py` backtrack snapshots, battle-wedge watchdog, `start_in_run_heal`) | stuck counters → snapshot restore / in-run heal | orbits a wall family |
| cross-run loop: run → learnings → merge → rerun (`discovery.py`, `advisor.py`) | escalation → Claude Code headless in a worktree, gates, PR; sessions → validated tips/evals through a gate | **the only loop that converges — and a human is the loop body** |

Pieces that matter for "wedge driving":

- **Flink → `pokedex/memory/observations.md`.** `docker/flink-sql/init.sql` raises `IN_PLACE_WEDGE`,
  `DOOR_STALL`, `POSITION_DEADLOCK`, `NO_PROGRESS`, `STUCK_STREAK_SPIKE`, `GAME_STUCK_LOOP`;
  `docker/alerts-consumer/consumer.py` writes them to the journal and maps each to **knob nudges**
  (`IN_PLACE_WEDGE → bt_restore_threshold=10`, `DOOR_STALL → door_cooldown=12`). So today's wedge
  driving is *parameter* healing — the loop the spec says never changed an outcome.
- **`discovery.run_evidence`** measures where a run wedged from its own event log (counts + decision
  trace), because "a human describing a replay names the wedge they happened to click".
- **`advisor.py`** exists precisely because operator-written `docs/learnings/` was "self-reported
  and unverified — fabricated Brock entries and FIXED claims without a passing segment". It adds an
  Investigator (reads one captured session + worktree truth), an Architect (designs the eval from the
  tip alone), and a gate. Nothing today went through it.
- **`supervisor.py`** (the expedition loop body) has a fingerprint ladder ending in `escalate` and a
  `write_exhaustion` that writes `docs/learnings/<map>-stuck-<run>.md` and emits
  `supervisor.exhausted`. It does **not** write the journal, the discovery queue, or the healer's
  state. The converging loop's human body was, today, me — and I was a lossy one.

## 2. The mistakes, classified against that machinery

| class | today's instances | why the infra didn't catch it |
|---|---|---|
| **A. A reading taken as a mechanism** | `connections: {west: 8}` read as passable; "observations.md is mostly test noise" from a tail; the fnm/stdin theories for dead legs; the static water model called solid | the doctrine says measure, but nothing *requires* a world claim in a mission/doc to cite a probe or a journal line |
| **B. Blind instrumentation** | `ps | grep 'pi -p'` never matched a process named `pi`; four legs declared dead, duplicates launched onto one baton | liveness was an ad-hoc grep, not code with a test |
| **C. Building beside the pipeline** | 51 `docs/learnings` files instead of the journal; engine fixes by hand in the main tree instead of `discovery.py`'s worktree+gates; no `advisor` gate on leg output | no guard said "this already exists"; the only guard I added today is the journal one |
| **D. Turn burn** | lint → rerun → lint → rerun; 25-turn chases of wrong theories; polling turns | nothing in the loop priced a turn |

## 3. The fixes, smallest structural piece first

1. **Exhaustion feeds the loops that learn.** `write_exhaustion` also appends an `[important]`
   journal line (`map=<id> exhausted … failure, tried, screenshot`) so `prior_observations` hands it
   to the next leg on that map automatically, and enqueues a discovery entry carrying
   `run_evidence` so loop 3 can pick it up with gates. *(journal half landed with this doc; the
   queue entry needs the queue schema read first, not guessed.)*
2. **Wedge alerts drive observation, not knobs.** In the supervisor, an `IN_PLACE_WEDGE` /
   `DOOR_STALL` for the current map is a trigger for `recon()` (talk, screenshot, item sweep) before
   any consult — because every wall that fell, fell to a fact, not a parameter.
3. **World claims cite evidence.** A mission prompt or journal line stating a map fact carries the
   probe name or the journal line it came from; `describe()` marks unsourced notes as `HYPOTHESIS`.
   This is the guard for class A.
4. **Leg liveness is code.** `scripts/legs.py list|launch|kill` — lists `pi` processes by the log
   they own (`/proc/<pid>/fd/1`), launches through the quoting-safe launcher, kills by PID.
   Tested. No more greps.
5. **Leg output goes through the advisor gate.** A finished pi session → `advisor investigate` →
   `design` → `gate`; only a gated tip becomes a journal line marked `validated`. Raw
   `docs/learnings` from a leg is a draft, never a fact.
6. **Engine fixes go through discovery.** When the ladder escalates, the evidence bundle goes to
   `discovery.py run`, which works in a worktree and proves the fix with gates and a fitness eval
   before a PR — the path the spec already built for "Opus fixes source".
7. **Price the turn.** Lint and run in one command; one monitor per leg; when a diagnosis fails
   twice, measure the mechanism instead of a third variant. These are habits, so they also go in
   `.claude/skills/expedition/SKILL.md` as rules, not intentions.

## 4. What this does not fix

Model judgement. A model — this one included — will still read a table as a mechanism. The
pipeline's answer is the right one: models propose, probes decide, gates admit. The work above is
making the expedition path obey that shape, which it did not.
