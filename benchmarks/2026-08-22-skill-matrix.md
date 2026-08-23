# 2026-08-22 — the per-skill model matrix: battle / navigation / puzzle, 6 models, Mt. Moon stands

The first benchmark asking *which model for which part of the game*, run two ways: a
regex-scored screen over 13 diagnostic cases (minutes, `evals/results/models-2026-08-22.md`),
then expedition slots on three skill-isolated legs (pi harness, no Claude anywhere, escalation
pre-seeded off; one slot per model per leg, enforced by marker). Legs: **battle** =
`pewter_to_badge` from the pre-Brock baton (15 m); **navigation** = `mtmoon_1f_to_b1f` (25 m);
**puzzle** = `mtmoon_clear` (50 m) — anomalies that demand live observation over confident
theory. Expedition-mode rows: compare within this table only.

## The matrix

| model | battle | navigation | puzzle (depth when failed) |
|---|---|---|---|
| kimi-k2.6:cloud | ✅ 11 t, att 1 | ✅ 101 t / 39 HP, att 1 | ❌ **B2F, 18 tiles** — deepest |
| qwen3.5:397b-cloud | ✅ | ✅ 54 t / 6 HP, att 2 | ❌ B2F, 15 tiles |
| muse-glimmer | ✅ | ✅ 54 t / 6 HP, att 2 | ❌ doorstep (7 tiles of 1F) |
| nemotron35-lightning | ✅ | ✅ 101 t / 39 HP | ❌ 1F only (51 tiles); worst spring bleed (1.06 M transitions) |
| gemma4-31b | ✅ | ✅ 206 t / 32 HP via the **NW (5,5) ladder** | ❌ best underground dwell (B1F 19 + B2F 10 tiles); killed by the **second spring** |
| qwen38-27b | ✅ | ✅ **49 t / 36 HP — best line** | ❌ only model whose attempt 1 did NOT die on the entrance spring; committed the root-cause diagnosis |

**Battle: 6/6, near-identical rows.** The fight never dips below any genome threshold — the leg
is an execution baseline, not a discriminator (qwen38's 0.39 screen-battle score cost nothing).
**Navigation: 6/6, three solution families** — conservative 101 t/39 HP (kimi, nemotron),
aggressive 54 t/6 HP (qwen397, muse — both after a sprung first relay), and gemma's 206 t/32 HP
through the NW ladder. qwen38's 49 t/36 HP dominates on both axes.
**Puzzle: 0/6. Mt. Moon stands.**

## The screen predicted the expedition

Puzzle-column depth ordered exactly as the screen's puzzle scores: kimi (0.55) > qwen397 (0.50)
> the rest — and muse-glimmer (0.35) never left the doorstep. The two screen anti-patterns
(rewrite-the-reference, block-the-stalled-tile) were hit by kimi on paper and mirrored by
nemotron in the field (a million spring transitions of relaunch-without-diagnosis). Screens are
floors, not verdicts — but this one ranked a 50-minute behaviour from a 30-second question.

## What the mountain taught (event-stream harvest, `data/local_runs/skill-matrix-harvest.md`)

Mined per slot from each worktree's `agent.game.events` sink — fitness rows hid most of this:

1. **Two springs, one mechanism.** The entrance spring (59↔15) everyone knew; gemma's slot
   exposed a **second inter-floor spring (60↔61, 77 k bounces)**. A warp lands the lane on the
   destination mat; a step back re-triggers. Stuck detection never fires — the map keeps changing.
2. **The NW (5,5) ladder is enterable** (gemma used it). kimi's 12 k stuck events there were
   technique, not an engine anomaly. Hypothesis retired.
3. **B1F is a fast pass-through pocket** — confirmed by qwen397's dwell samples.
4. **The root cause is written down, by a model**: qwen38's committed `obstacles.md` names it —
   `_mtmoon_action` returns None inside 59, no route data exists for 59/60, so lanes blind-cycle
   into the mats. Plus the seven 1F trainer-sprite coordinates and the tile-pair risk.
5. **Salvage**: kimi left a 78-line `_mtmoon_clear_action` draft; gemma left ladder-target
   pilots. Uncommitted but preserved; worktrees kept.

## The composite fix spec (no model finished it alone; together they wrote it)

Step off the landing mat after every warp (kills both springs) + truth-step targets through
59→60→61→Route 4 (the Route 3 playbook) + sprite-aware pathing (already in
`rom_truth.path_on_map`). This is the next fix-source item; the rows above stay honest as
"no model solved the spring unaided in 50 minutes."

## Discipline notes

- Battle leg's six-genome spread returned identical fitness (fight too short to trip any
  threshold) — `report_inert_spread` called it out as designed.
- One slot per model per leg enforced via `.slot-used` markers after a relaunch deadlock
  (process-name self-matching in the waiters; fixed).
- Cloud legs initially died to the launcher's `-128k` suffix; aliases containing `:` now pass
  through verbatim.

## Postscript, same day: the mountain falls

The composite fix — implemented after the batch, exactly as the spec above prescribed — clears
Mt. Moon deterministically: **all six relay lanes CONQUERED `mtmoon_clear`, winner 880 turns,
seed to Route 4 (27,3) at 25 HP.** The baton (`route4_east_hp25`) faces Cerulean. Two more
engine-authority lessons surfaced during implementation, both now in the code:

- **A viewport observation can sever a one-wide corridor forever.** A wandering B2F Rocket,
  observed once beside a ladder mat, persists as a learned wall until re-observed — which never
  happens once the planner routes around it. The dungeon walk ignores learned zeros
  (`use_learned=False`); transient bodies are the refusal machinery's job.
- **The fossil doorway is a body, not a wall.** B2F's only corridor runs through the fossil
  tiles (12,6)/(13,6); pre-blocking ROM sprites plans around a passage the live game opens
  after the Super Nerd event, and no plan remains. The dungeon walk blocks nothing but
  engine-discovered, expiring walls (`use_sprites=False`) and presses into bodies — the A-press
  clears dialogs, battles get fought, real walls hard-block and expire.

The `truth_refuse_strikes` spread is genuinely live on this leg (`fast_stuck` 944 t / 12 HP,
`wide_dc2` 913 t vs the 880 t / 25 HP majority) — the first segment where the NAV spread
differentiates end-to-end.

The benchmark verdict above is unchanged: no model cleared it unaided in a 50-minute slot; the
models collectively wrote the spec, and the harness executed it.
