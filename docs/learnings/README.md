# Learnings — durable obstacle records

Each file records one obstacle in the shape issue #70 asks for (`obstacle / category / symptom /
failed / winner / why it worked / generalizes / artifacts`). Before burning compute on a new
obstacle, query this directory by **category** first.

| obstacle | category | status | produced by | one-line lesson |
|---|---|---|---|---|
| [route1-navigation-flee-loop](route1-navigation-flee-loop.md) | navigation · battle | cleared | pi + kimi-k2.6 (2026-08-15) | the wild-battle stall guard returned `run` forever; cap recovery attempts and fall back to the best move |
| [viridian-forest-turn-385-blackout](viridian-forest-turn-385-blackout.md) | navigation · battle | cleared | pi + kimi-k2.6 (2026-08-15) | in high-encounter mazes survival beats leveling: flee/heal at 50% HP; a healthy entry (17 HP) crosses in ~2.3k turns |
| [viridian-forest-1hp-entry-unresolved](viridian-forest-1hp-entry-unresolved.md) | navigation · battle | unresolved | pi + claude-haiku-4.5 (2026-08-15) | entering the forest at 1 HP cannot be rescued by genome spreads alone — the baton's health is the lever, not the forest genome |

## The 1-HP forest lesson (why two entries)

Two operators hit the same wall from opposite sides. Kimi fixed the flee-loop bug upstream, so its
Route 1 baton entered the forest at **17 HP** and `very_cautious` (`hp_run_threshold=0.5`,
`hp_heal_threshold=0.5`) walked out to Pewter in 2270 turns with 13 HP. Haiku sidestepped the same
bug by swapping the seed state, arrived at **1 HP**, and no forest genome could save it. Same map,
same code paths — the only difference was the health of the party that walked in.

Generalization for the relay: a segment's baton is only as good as its `lead_hp`. The relay already
picks the healthiest winner; the operator should treat a low-HP baton as a failure of the *previous*
segment, not a tuning problem for the next one.

Artifacts (local, gitignored like every savestate): `demo-runs/states/forest-entry-healthy-17hp.state`,
`demo-runs/states/forest-entry-1hp.state`, `demo-runs/states/forest-very-cautious.genome.json`.
Operator traces are in tapes; game events in Kafka `agent.game.events`.

## What we actually learned (2026-08-15, five operator runs)

### Route 1/2 flee loop — the first wall every model hit
All 12 lanes (6 variants × retry) freeze on map 13 at 4 HP choosing `run` forever. Two compatible
root causes, found independently:
- **Stall guard has no cap** (Kimi): once `_wild_fight_turns >= WILD_BATTLE_PATIENCE` the wild
  branch returns `run` unconditionally, and `run` turns don't advance the counter → infinite loop.
  Fix: cap stall-guard runs at 10, then fall back to the best move. Lanes reach the forest at 17 HP.
- **RUN is never confirmed** (Sonnet): `fight` already had confirm-and-retry because menu presses
  silently miss while a text box plays; `run` fired once and hoped. Route 2's Weedle/Rattata status
  moves produce more text boxes than Route 1, so RUN misses far more often → HP never changes → RUN
  again. Fix: confirm-and-retry RUN via `_await_turn_resolved` + `unstick` (mash B) every 4th
  stalled turn. Lanes reach the forest in 750 turns at 4 HP.
- **Why every variant failed identically**: the save state fixes the RNG and the parcel-quest pilot
  overrides navigation, so genome spreads cannot change the outcome. *Six identical failures means
  code, not config.* This is now `evals/cases/route1-flee-loop.json` (FAIL on main until a fix lands).

### Viridian Forest
- **Survival trumps leveling** (Kimi): `very_cautious` (flee/heal at 50 %) crosses in 2270 turns
  with 13 HP; base/aggressive/status-heavy thrash (500–670 stuck events, 62–181 encounters). Trigger:
  `stuck_count > 100` and `max_stuck_streak > 20` in a high-encounter maze → raise
  `hp_run_threshold`/`hp_heal_threshold`.
- **It is a length problem, not a decision problem** (Sonnet): a 4-HP, no-potion party needs
  thousands of turns; no HP threshold changes traversal length, so every variant hits the same
  `max_turns` cap. When all variants fail identically at the cap with high stuck/encounter counts
  and *no losses*, double the budget (the relay's automatic retry) before touching the genome.
- **A baton is only as good as its `lead_hp`** (Haiku, both harnesses): entering at 1 HP cannot be
  rescued by forest tuning; the lever is the previous segment. Both Haiku runs entered at 1 HP because
  they seed-swapped around the flee-loop bug instead of fixing it.

### Pewter / Brock — three defects, none fixed on main yet
- **Waypoint index resets to 0 on a fresh process** (Sonnet): a baton captured mid-city sends the
  party back to the "Enter from forest" door, re-triggers it, and the quest logic replays the early
  game. Fix (on `speedrun/pi-sonnet`): first-call nearest-waypoint by Manhattan distance, skipping
  waypoints whose note starts with "enter". Verified: first log line `WP: 0→(13,25)` → `WP: 1→(19,17)`.
- **Bad map data** (Sonnet; Kimi attempt 1 agrees): every lane parks at (17,11) pressing left into
  (16,11), the `routes.json` "Pewter Gym" waypoint — a wall (`stuck_turns` > 7,800). Kimi's attempt 1
  moved it to (16,17). Haiku called map 58 (the Poké Center) "the gym interior".
- **Mid-transition savestate** (Kimi): Pokémon Red updates `wCurMap` (0xD35E) before player
  coordinates in a gatehouse transition, so `--stop-on-map` saves with the player still at Route 2
  coordinates and the next segment loads into an inconsistent frame (warps to (16,12)/(16,13)/(18,34)
  by timing). Rule: never save on the first frame of a new map — require 2–3 settled frames (no map
  change, no battle, `text_box_active == False`), or snapshot the last clean backtrack frame.

### What each model is good at (same harness, same prompt)

| model | genuinely good at | watch out for |
|---|---|---|
| Sonnet 5 | Surgical code reading (`sed -n` ranges; 2 raw reads in 187 calls); finds *systemic* bugs beyond the one in front of it (waypoint reset); learnings carry mechanism + verification + rule; complete deliverables; fastest wall clock | Cost per unit of progress ($6.86 / 49 min at ~9 s/turn); its flee fix leaves lanes at low HP |
| Kimi K2.6 | Deepest single-cause diagnoses (flee-loop counter; `wCurMap`-before-coords); willing to grind (27 relay runs, 432 lanes); most reusable operator heuristic ("survival trumps leveling") | Slowest; uncached tokens make it the most expensive at scale (≥$26/h at list); needs context guardrails; missed the summary |
| Haiku 4.5 | Cheap and quick ($0.87, ~5 s/turn); tidy, on-time write-ups; correct *symptom* descriptions (the 1-HP baton); predictable across harnesses | Never opens the code — seed swaps and spreads; confidently wrong root causes; self-terminates at ~1 h declaring a "technical limit" |
| Qwen3.5-35B (local) | Real tool use at 20 tok/s on one GPU; formed a non-trivial hypothesis (world map never observes map 2) and edited toward it; $0.73 cloud-equivalent | Ollama `num_ctx` truncation is invisible to pi → lost the mission mid-run; off-format doc, no commits, ended on a text-only turn |
| Gemma4-8B (local) | 143 tok/s, working tool calls, follows the doc format once told to act every turn; cheapest ($0.15 equiv, ~5 Wh) | Ends turns after thinking without acting; tunes two numbers; pattern-matches obstacle names from the prompt onto what it saw |

The capability boundary is turning "all six lanes failed identically" into "so it's code, not
config": Sonnet and Kimi cross it, the other three don't.

## Per-run originals (2026-08-15, five models on the pi harness)

Unedited entries from each operator run live under `by-run/2026-08-15-<model>/`; the table above is
the curated set. Highlights worth reading in the originals:

| model | notable entries |
|---|---|
| [sonnet-5](by-run/2026-08-15-sonnet-5/) | `route2-battle-menu-desync-blackout` (a second, compatible root cause for the Route 1 flee loop), `pewter-waypoint-index-reset-loop` (real nav bug: waypoint index starts at 0 when loading mid-map), `brock-approach-deadend-unresolved` (the (16,11) Gym waypoint is a wall) |
| [kimi-k2.6](by-run/2026-08-15-kimi-k2.6/) | `pewter-corrupted-transition-save` (`--stop-on-map` saves on the first frame after `wCurMap` flips) |
| [haiku-4.5](by-run/2026-08-15-haiku-4.5/) · [haiku-4.5-claude-code](by-run/2026-08-15-haiku-4.5-claude-code/) | tidy but partly wrong root causes — useful as a contrast; the Claude Code run's `NEXT_STEPS.md` hypothesised the transition-save bug before Kimi confirmed it |
| [qwen3.5-35b](by-run/2026-08-15-qwen3.5-35b/) | free-form (its context was silently truncated by Ollama's `num_ctx`) |
| [gemma4-8b](by-run/2026-08-15-gemma4-8b/) | follows the format; files the Route 1 flee loop under the forest obstacle's name |

Regression evals derived from these live in [`evals/`](../../evals/README.md); dated benchmark
tables in [`benchmarks/`](../../benchmarks/README.md).
