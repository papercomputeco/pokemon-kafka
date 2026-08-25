# Skill-matrix knowledge harvest (2026-08-22, running notes)

Per the operating rule: every slot increases recorded Mt. Moon knowledge, win or lose.
Mined from each worktree's game-event stream (the Kafka bridge sinks), not from fitness alone.

## kimi-k2.6:cloud / mtmoon_clear (slot spent, no clear)

- Fitness said "entrance spring"; the stream says the lanes ALSO reached **B2F (61), 18 tiles**,
  as deep as (18,31), (31,12), (14,32). Final-position rows hide mid-run depth.
- 59<->15 spring: 126,573 transitions across the slot — the dominant budget sink.
- **New wedge fingerprint: map 59 (5,8) x7963 + (5,5) x4260 stuck events — the NW ladder mouth
  to B1F.** The lane found the correct door and hammered it. Candidate mechanisms: approach
  direction, sprite at the lip, or another engine rule the grid can't express (cf. the 08-21
  "ladders are not warps/walls" amendment). This is the next thing to measure live.
- Zero overworld samples on B1F (60) despite 2,913 on B2F — consistent with 60's ~25-cell
  pocket being a fast pass-through between ladders (08-20 report), unconfirmed.
- Secondary 1F wedge cluster: (2-5, 20-21) and (10,22) — SW region.

## qwen3.5:397b-cloud / mtmoon_1f_to_b1f (cleared, 54 turns, arrived 6/55 HP)

- First relay burned 6000 turns on the spring; second landed a fast line at heavy HP cost.
  Same wall, opposite recovery profile to kimi (101 turns, 39 HP, attempt 1).

## qwen3.5:397b-cloud / mtmoon_clear (slot spent, no clear, rc=4)

- Also reached BOTH underground floors: B1F (60) 15 tiles (669 events — so 60 IS sampled when
  dwelt on; kimi's zero-60 was genuinely a fast pass-through), B2F (61) 15 tiles / 6,168 events.
- Same budget sink: 59<->15 spring x127,853.
- Different wedge geography from kimi: SW cluster (5,20),(5,21),(2,21),(9,24),(10,22) — no
  ladder-mouth hammering. Two models, two distinct 1F wedge maps, one shared spring.
- Emerging structural read: lanes that pop back to 59 respawn near the entrance mat and
  re-spring; the supervisor's own fingerprint ("no genome knob moves a spring; code or route")
  points at a deterministic entrance-mat step-off / cave truth-step as the eventual fix if no
  model in this batch solves it.

## muse-glimmer / mtmoon_clear (slot expired rc=124, no clear)

- Never went underground: 7 tiles on 1F, zero events on 60/61. 380,515 spring transitions —
  the whole slot on the doorstep. Wedge tiles ARE the entrance mats (14,35)/(15,35) plus the
  Route 4 side (18,15)ish.
- Ranking within the puzzle column so far: kimi (B2F, 18 tiles, ladder-mouth diagnosis) >
  qwen397 (B2F, 15 tiles) >> muse-glimmer (doorstep). Matches screen order (0.55/0.50/0.35).

## nemotron35-lightning / mtmoon_clear (slot expired rc=124, no clear)

- 1F coverage 51 tiles (2nd best), zero underground. Spring: 1,055,675 transitions — the worst
  spring bleed of the batch by 3x, i.e. it kept relaunching the same springing relay rather
  than diagnosing. Wedges in the SW cluster (5,20)/(5,21)/(10,22), same as qwen397.
- Puzzle depth ranking now: kimi (B2F/18) > qwen397 (B2F/15) >> nemotron (1F/51, all surface)
  > muse (doorstep/7).

## gemma4-31b / mtmoon_clear (slot expired rc=124, no clear) — TWO NEW FACTS

1. **The NW (5,5) ladder is enterable** — gemma's nav leg used it (206t route). kimi's 12K stuck
   events there were approach/technique, not an engine anomaly. Hypothesis retired.
2. **Second spring discovered: 60<->61, x77,743.** Same mechanism as the entrance spring —
   warp lands the lane on the destination ladder mat; a step back re-triggers. gemma had the
   batch's best underground dwell (B1F 19 tiles, B2F 10 tiles) and died oscillating between
   floors, never within reach of the east exit (max x on 15: 18 = the west door).

Mountain's defense now fully mapped: spring #1 (59<->15 entrance, killed muse+nemotron),
spring #2 (60<->61 inter-floor, killed gemma), attrition. One fix class covers both:
step OFF the landing mat after any warp before generic navigation resumes.

## qwen38-27b / mtmoon_clear (slot expired rc=124, no clear) + nav (CLEARED, best line 49t/36HP)

- Only model whose first clear-attempt did NOT die on the entrance spring (wall: no-fingerprint).
- Committed `obstacles.md` in its nav worktree — the batch's most valuable single artifact: it
  independently names all four mechanisms (O1 seed-mat trap; O2 ROOT CAUSE "no planner owns
  59/60" — _mtmoon_action returns None inside 59 so the lane blind-cycles; O3 the seven 1F
  trainer sprites with coordinates; O4 tile-pair edge property, per-cell grids over-report).

## Salvage inventory (uncommitted worktree edits — the laguna lesson, avoided this time)

- kimi (clear wt): 78-line `_mtmoon_clear_action` + wLastMap logging on map changes. Real
  fix-shaped code, unfinished.
- gemma (clear wt): minimal ladder-target pilots for 59/60/61 (+ find_warps_to_15.py helper).
- qwen38 (nav wt): obstacles.md COMMITTED (see above).
- All worktrees preserved under ../pokemon-kafka-speedrun-pi-skl-* for the fix work.

## The composite fix spec (assembled from the batch, no model finished it alone)

1. Step OFF the landing mat after any warp (kills both springs: 59<->15 and 60<->61).
2. Give _mtmoon_action targets inside 59/60/61 — truth-step through the floors (qwen38's O2,
   gemma's targets, the Route 3 playbook).
3. Route around the seven 1F trainer sprites (qwen38's O3 coordinates).
4. Plan with tile-pairs (already in rom_truth.path_on_map).
