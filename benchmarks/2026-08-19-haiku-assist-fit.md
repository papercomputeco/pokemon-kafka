# 2026-08-19 — the first `assist=fit` row: does a model told its own tendency change it?

The experiment #95 was built for. Haiku 4.5 on Mt. Moon, everything identical to its 08-18
unassisted row — same seed (`badge1_gym_hp6.state`), same mission, same base wall, 2 h cap,
self-heal on — except `ASSIST=fit`: the mission carries `scripts/model_fit.py section` for this
model, i.e. its own measured character ("strong as driver; weak as experimenter, investigator"),
its own numbers ("0 probes in 9 relays, twice; early exit 2 of 2"), and the concrete counter-moves
("when two relays end on the same tile, the next command is ONE lane"; "state the furthest
coordinate before writing 'sealed'"). **Assisted row** — compare only with the same model's `none`
row; never into the model-vs-model tables.

## A/B, measured by `role_metrics.py` on both sessions

| run | wall | relays | probes | probe/relay | calls→1st relay | code commits | furthest | verdict quality | early exit |
|---|---|---|---|---|---|---|---|---|---|
| `none` (08-18) | 38.6 m | 9 | **0** | **0.0** | 11 | 0 (5 doc commits) | map 54 (4,13) — never left the Gym | "trap warp… gym **sealed**" (wrong) | yes (~80 m left) |
| `fit` (08-19) | 18.9 m | 4 | **13** | **3.25** | 53 | **4 of 8** | **map 2 (23,8) — Gym exited, east across Pewter** | "cannot progress past (23,8)" (correct, coordinate-first) | **yes (~100 m left)** |

$1.86, 121 turns, `success`. Worktree `speedrun/haiku-cc-mtmoon-fit`, 8 commits.

## What changed — three of the four target behaviours

1. **The probe habit took, immediately.** Its first game command was a single lane, and it ran six
   probes and two code fixes before its first relay (the `none` row raced at call 11 with zero
   probes ever). The probes found what yesterday's "trap warp" actually was: the building-exit rule
   not running in the post-badge gym state, plus no door cooldown — the lane stepped out and
   straight back in. Two `agent.py` fixes (`c1c4c91`, `dc439b0`), then waypoint work
   (`58c6841`, `da01669`, `7ecaba5`). **The Gym exit that consumed the entire `none` run is solved
   in this one**, by the model that "couldn't" investigate.
2. **The verdict discipline took.** No "sealed", no "trap warp". The Route 3 entry block is stated
   as a coordinate ("cannot progress past (23,8)") and the obstacle file leaves `winner: (pending)`
   / `why it worked: TBD` rather than asserting. That is the exact rule from its fit section.
3. **Reporter unchanged (was already fine):** 4 learnings files, 8 commits as it went, numbers match
   the reports.
4. **Early exit did NOT take — it got worse.** 18.9 minutes, ended by choice with ~100 left and an
   unsolved, named, *coordinate-located* blocker. The guidance said "keep working after the summary"
   and it wrote the final summary at ~17 minutes anyway. Three missions, five Haiku runs, five early
   exits; the paragraph moved probe/relay from 0.0 to 3.25 and moved the exit time not at all.

## Reading it honestly

- One run, one model, no seed variance: a suggestive result, not a law. The Brock-day pattern
  (misattribute → stop) failed to reproduce under `fit`; that is the strongest single-run evidence
  yet that **Haiku's zero-probe wall behaviour was a prompt artefact, not a capability limit** —
  it could probe, fix code from probe evidence, and locate a wall correctly the moment it was told
  that this is what it fails to do.
- Early exit looks like the opposite: robust to being named, twice now told in-mission with its own
  numbers. Whatever ends these runs at ~30 % of budget is not addressed by telling the model about
  it. That moves the fix to the harness (a continuation nudge at N minutes, or the launcher
  re-prompting on `success` with budget left) — mission text has now failed at this five times.
- Net wall progress vs the `none` row: real (gym exited, Pewter crossed) but bought partly with
  knowledge the `none` row lacked only by date, not by assist — the fit section contains no game
  facts. The behaviours changed are the ones the section names, which is the point of the design.

## Next

- This session is deliberately NOT folded into `measured{}`. Doing so was the first draft of this
  file, and it is a bug twice over: `update` replaces rather than merges (a partial list shrinks
  the history), and an assisted session in `measured` makes the assist measure itself — the block
  exists to describe the *unassisted* tendency that the fit section corrects against.
  `measured{}` stays: Haiku 2 unassisted sessions, probe/relay 0.0, early exit 2/2, with this row
  beside it as the assisted comparison. `update`'s docstring now says so.
- The symmetric experiment: `ASSIST=fit` on **qwen38-27b** (told: "state the furthest tile before
  any 'impossible'") on Route 3 — its wall was the inverse of Haiku's.
- Harness-side continuation is now the top early-exit lever; mission text is exhausted.
- Haiku's gym-exit fixes (`c1c4c91`, `dc439b0` on `speedrun/haiku-cc-mtmoon-fit`) overlap qwen38's
  Route 3 branch — reconcile the two before either merges.

Artifacts: `data/local_runs/haiku-cc-mtmoon-fit.claude.jsonl`, worktree branch
`speedrun/haiku-cc-mtmoon-fit` (8 commits), the exact section received is reproducible:
`uv run python scripts/model_fit.py section claude-haiku-4-5-20251001` at `references/model_fit.json`
@ the pre-update revision (6b48f7c).
