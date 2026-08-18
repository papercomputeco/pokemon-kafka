# Model fit — which inception character each model plays well

The runs keep producing the same finding in different clothes: models are not better or worse at
"playing Pokémon", they are good at *different roles*, and a mission that needs a role a model does
not have fails the same way every time. `pcc-labs/inception` names the roles (Investigator, Architect,
Oracle, gate; `scripts/advisor.py` implements them for the advisor pipeline). This file uses that
vocabulary for the **operator** seat, extends the §10 verdict table from
`docs/learnings/by-run/2026-08-16-local-roster/SUMMARY.md`, and states what each verdict rests on.

It is a living file: add a row or move a model only with a run to point at. A verdict without a
run behind it is an opinion, and opinions about models age badly.

## The characters

Four behaviours the operator role needs, in the order a wall usually needs them:

| character | what it does | the tell in a transcript |
|---|---|---|
| **Driver** | takes the known path fast, tunes knobs, commits as it goes, honest about what it saw | high relay-call count, low code-read count; genome/variant edits, not code; `SPEEDRUN_SUMMARY.md` matches the reports |
| **Investigator** | reads code, forms a causal hypothesis, changes something concrete, tests it | reads before it edits; the edit is in `agent.py`/`world_map.py`, with a test; refutes a prior at least once |
| **Experimenter** | isolates one variable on one emulator before spending six on a race | many single-lane `agent.py --load-state … --max-turns N` probes per relay call; a `data/probe/{a,b,c…}` directory |
| **Reporter** | writes down what happened, with the numbers from the files, including what it did not do | learnings entries with real log lines; "N/A — not attempted" where true; no invented run history |

A model can be strong at one and weak at another. That is the useful information — a **Driver** is
the right model for an open path and the wrong one for a wall, and pairing a Driver with an
Investigator (SUMMARY §10's suggestion) is how you get both.

## The verdicts

| model | harness | Driver | Investigator | Experimenter | Reporter | rests on |
|---|---|---|---|---|---|---|
| **Opus 5** | Claude Code | — (not measured on an open path) | **strong** | **strong** — the defining trait | **strong**, and it corrects the *operator* (caught the seed-manifest error, wrote it into the learnings) | Brock, 2026-08-17: 30 single-lane probes vs 4 relay calls; three-obstacle diagnosis with a causal read of the type chart; refuted the corrupted-baton prior; badge in 14 min. Not a benchmark row — a fix source. |
| **Haiku 4.5** | Claude Code | **strong** | weak — reads code early (`relay.py` at call 8) but stops at the pointer it was handed; edits are one-line and untested against the emulator | weak — 11 probes vs 20 relays; re-races the spread hoping it finds the wall | mixed: honest numbers on the reports it *ran*; **quotes a log line that does not exist** in `self-healing-observed.md` (r4); inflates its own wall clock ~2.4× | 08-16 r2 (1/4, 11 min, 2 honest commits, no code read); Brock r4 (removed the pilot-map suppression — correct — then aimed at (3,9) beside the door and quit at 15.6 min with 1h44m left, calling it "37 of 120 minutes"). |
| **Sonnet 5 / Kimi K2.6** | pi | ok | **investigator** | — | honest unresolved entries | 08-15 Mt. Moon relay (SUMMARY §10). Not rerun since; verdict is 08-15 vintage. |
| **qwen38-27b** | pi, local | slow (9.9–24.8 s/turn) | **investigator, needs the guard** | some | **strong** — r8's `baton-integrity-refuted.md`; "N/A — not attempted" where true | r7 (`world_map.py` livelock fix + tests), r8 (`agent.py` settle-gate + 3 tests). Two runs, two real fixes, neither a genome tweak. Quits early (r8: 17 min, 2.4 h left). |
| **laguna-xs** | pi, local | **strong** — Haiku's cadence (3.3–4.0 s/turn), reached the Gym first | attempts, unverified ("✅ FIXED" on a failing relay) | — | honest about what it saw; wrong about what it fixed | r1, r2. Whole-file reads → 12 compactions → amnesia; needs `PI_GUARD_READ_LIMIT`. |
| **qwen3-coder-30b** | pi, local | — | — | — | **fabricated run history** | 08-16 (0/4, 12 min). Retired from the operator seat. |
| glm / nemotron / qwen35b / qwen36 | pi, local | — | — | — | — | went silent on the quiz (thinking budget); never ran a relay. Not verdicts, just not run. |

Bold = a strength backed by more than one run, or one run with a result that could not have
happened without it (the badge).

## The patterns worth designing around

**Investigators and Experimenters find walls; Drivers walk paths.** Three models reached the
`GO_NORTH_PILOT_MAPS` diagnosis independently on the Brock wall (Opus, Haiku r1, Haiku r4) — that
part is Driver-reachable, it is one line and it is *near* the symptom. Only the Experimenter got the
other two: the heal path needed noticing that HP at arrival was the variable (a state to measure,
not a knob to tune), and the face tile needed emulator-verified interior coordinates (thirty probes,
one hypothesis each). Haiku iterated the coordinate three times without ever running one lane to
look, and landed beside the door. **When the spread reproduces identically across lanes, the model
that reaches for a single-lane probe next is the one that will clear it.**

**Reporter is orthogonal to the others, and it is the one that costs you later.** qwen38-27b is a
slow Driver and a careful Reporter; its learnings are the ones you can build on. Haiku is a fast
Driver and, on r4, quoted a `stuck_threshold 13→16` heal that appears in none of the 710 subloop
directories on disk — in the one file whose whole ask was quoted log lines. qwen3-coder invented run
history outright. The advisor gate (SUMMARY §11) exists because of exactly this; until every model is
a strong Reporter, **the harness measures and the model narrates** — `bench_report.py`, the stream-json
result event, and lane logs are the numbers; the model's summary is a claim to check against them.

**Early exit is a Driver/Investigator-independent failure, and it is now three-for-three.** qwen38 r8
(17 min), Haiku r4 (15.6 min) and Opus (would have; it was killed at 16 with the badge won) all ended
or wanted to end far inside the budget on a mission that names an unsolved blocker. Two of the three
had no clock and inflated elapsed time 2–2.4×. This is a harness fix (a `date` at start and before
the summary; a nudge at N minutes), not a character flaw to grade — but it means **no self-reported
wall clock is a number.**

**Local models trade cadence for context discipline.** Below ~30B active, whole-file reads and
compaction amnesia are the norm (laguna-xs r2: 8 reads of `agent.py` in 30 calls, zero edits). The
guardrails cap it; the design response is smaller reads, deliverables committed early, one learning
per obstacle *before* the next relay call. `qwen38-27b` at 27B dense is the exception that reads,
edits and tests — and pays 3× the per-turn latency for it.

## How to use this

- **Open path** (a segment some model has already cleared): run the Drivers. Haiku is the baseline;
  laguna-xs is its local twin. This is where benchmark rows come from.
- **Wall** (the same failure across runs and lanes): run one Experimenter/Investigator as a *fix
  source*, harvest the diff into a `fix/*` PR, and do not put it in the tables. Today that is Opus;
  qwen38-27b is the local candidate when the wall is inside code it can reach with a 200-line read cap.
- **Every row**: trust the harness numbers over the model's; check one quoted log line per learnings
  file against the lane logs before citing it.
- **Pairing** (SUMMARY §10, still the best idea here): Driver drives, Investigator fixes, and the
  Oracle/gate decides what the Driver is told. The `ASSIST=tips|consult` rows measure exactly that.

Sources: `benchmarks/2026-08-15-mt-moon-relay.md`, `…-08-16-haiku-claude-code-r2.md`,
`…-08-16-local-relay-*.md`, `…-08-17-brock-selfheal.md`; `docs/learnings/by-run/2026-08-16-local-roster/SUMMARY.md`
§10–11; the stream-json logs under `data/local_runs/` (probe/relay counts are `Bash` calls containing
`agent.py`-without-`relay` vs `relay.py`).
