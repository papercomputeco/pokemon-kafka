# 2026-08-16 — Mt. Moon relay, qwen38-27b r7: the first clean dense-27B row (no MTP draft, 480 W cap)

`RUN_TAG=qwen38-27b-r7 ASSIST=none scripts/local_relay_run.sh qwen38-27b main` — worktree off `main`
(`3d2aadd`: compaction guard, read cap, Pewter fix, battle watchdog, forest unseal, harness-death
guard). Sixth attempt at this model on the fixed repo, and the first to produce a row: attempts 1,
r3, r4, r5 and r6 all ended in a kernel `Xid 8` — see `2026-08-16-qwen38-27b-egpu-hangs.md`. r7 changes
exactly one thing from r6: Ollama's MTP speculative draft is off (`draft_num_predict 0`); the 480 W
cap that failed to save r6 stays so the attribution is clean. **Unassisted row** (`assist=none`).

## Scoreboard

| model | segs | wall | model time | turns | tools | out tok/s | s/turn | input tok | cache read | output tok | cloud $ | Wh | energy $ | max ctx | compactions | code fix | learnings | commits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **qwen38-27b r7** (local, 128k, no MTP, 480 W) | **2/4 + wins both Gym trainers** | 84.1 m | 72.9 m | 176 | 193 | 52.7 | 24.8 | 10.2 M | 0 | 230 k | $1.66 | **590.2** | $0.177 | 98 k | 4 | **yes — `world_map.py`, tested, verified against pre-fix** | 2 (1 cleared, 1 unresolved) | **3** |
| _qwen38-27b attempt 2 (2cd9240, 08-16)_ | 1/4 | 22 m | — | 91 | — | — | 9.9 | — | 0 | — | — | 156 | — | 130.9 k (`length`) | 0 | yes (battle watchdog) | 0 | 0 |
| _laguna-xs r2 (fixed main)_ | 2/4 + inside the Gym | 36.7 m | 22.2 m | 398 | 398 | 126.3 | 3.3 | 22.9 M | 0 | 168 k | $3.37 | 203.6 | $0.061 | 98 k | 12 | attempted (unverified) | 2 | 0 |
| _Haiku 4.5 (08-15)_ | 2/4 | 67 m | 5.9 m | 74 | 73 | 91.9 | 4.8 | 4.7 k | 3.5 M | 32 k | $0.87 | — | — | — | — | no | 3 + summary | 3 |

Power: 1006 samples over 84.1 min, GPU mean **421 W**, peak 498 W, **834 samples (83 %) at or above
470 W** — the card sat at its cap for most of the run and did not hang. Guard: kernel and Ollama
journals captured for the window (`data/local_runs/qwen38-27b-r7.{kernel,ollama}.log`), both clean;
last turn `stop` with 81.8 k in / 1.3 k out and a summary — ended by choice, not on context (max
98 k, 4 compactions) and not on the 3 h budget.

Speed is the price of no MTP: 52.7 out tok/s against attempt 2's ~90 (MTP was accepting 45–75 % of
its drafts at mean length ~3), and 24.8 s/turn — the slowest cadence on the board by 5×. It bought
84 minutes of a card that stays up. Cheapest run in cloud-equivalent dollars per commit so far.

## What happened

1. `route1_to_forest` and `forest_to_pewter` cleared inside the first minute (batons 13:51, launch
   13:50) — the harness fixes hold; nothing to investigate there.
2. `pewter_to_badge`: every lane entered the Gym and **froze at (7,11) pressing the north tile for
   23,876 of 24,000 turns**, `brock_won=None`, base lane 0 battles. The model ran the relay, read
   the report, pulled the lane logs, and named it: not a stuck (the agent *moves* every turn — it
   re-bumps a tile already in the `blocked` set), so `stuck_count` recovery never arms. It read
   `world_map.py`, found `cross_step`'s terminal `sweep(...) or fwd` returns a constant direction
   once the forward tile is retired, and shipped a sidestep-to-live-neighbour branch plus an
   `observe` bounds clamp (a stale map-54 header read was shrinking the map under the agent and
   blinding `explore_step`). Result on the retry relay: max stuck streak **23,876 → 51**, and the
   agent **beats both L11 Gym trainers** (19 battles won) — the first run in the project to do so.
3. It then did the thing SUMMARY §11 says the operator role rewards and no local model had done:
   wrote three `cross_step` tests, **checked them against `265309c^`** (two fail on the pre-fix code,
   pass on the fix), restored 100 % coverage, ran ruff, and only then wrote the learning as `cleared`.
   Its own `gym-fix-validation-gap.md` on the branch is the reason it did — the r2 tip that
   "declared complete after tests + lint; the relay report still shows `pewter_to_badge=None`" was
   *not* served (assist=none); the model reached the same discipline from the learnings directory.
4. Brock is still not found: all six post-fix lanes end at map 54 (4,5), badges 0, `brock_won=None`,
   15 HP, streak 51. The second learning, `pewter-gym-leader-unfound.md`, is marked **unresolved**
   with the exact numbers and reads the wall as "code, not config" — routing to the leader's room,
   not a genome. No fabrication anywhere in the run: the summary's claims match the report and the
   branch (checked: three commits, diffstat, `brock_won` values). One quibble: it committed the
   relay run output and the power CSV alongside the code (107 files) — the run worktree is off
   `main` before #88's `data/*` ignore.
5. Context discipline was fine this time: 31 `read` calls in 176 turns (r2 Laguna: 17 of its last
   30 tool calls were reads), 4 compactions, no re-reading loop. The read cap did its job.

## What it means

- **The MTP draft was the killer, not the watts.** Five hangs in the `draft_mtp` stack; zero in 84
  minutes without it at the same power profile r6 died under. `qwen38-27b` is runnable on this box.
  r8 (no MTP, stock 600 W) is the one remaining question — whether the cap matters at all — and it
  is worth one run because the cap costs decode speed too.
- **The investigator verdict from §10 stands, now with a full-length run behind it.** Attempt 2's
  pattern — reproduce, read the code, fix, test, then trust — repeated at 84 minutes with a code fix
  that survives adversarial checking (tests that fail on the parent commit). Sonnet, Kimi and Qwen 3.8
  are the three models on the board that have changed agent code; Qwen 3.8 is the only one that runs
  on the box, and now the only one whose fix came with a pre-fix/post-fix test pair.
- **The harness-death guard earned its keep in one day**: it refused r6 (correctly) and passed r7
  (correctly), and forcing the journal read is what turned up the stack that fixed the hangs.
- Slow. 24.8 s/turn is 5× Haiku, 7.5× Laguna. As a *driver* it would be a poor trade; as the
  investigator behind a driver (§10's split) it is exactly the model to pair.

## Next

- Review `265309c` (`world_map.py` sidestep + bounds clamp) and `4219d7c` (tests) for `main` —
  `pewter_to_badge` lanes now win the Gym trainers; that is a real fix with real tests. Cherry-pick
  from `speedrun/pi-qwen38-27b-r7`, leaving the run-output commit behind.
- Turn the leader-unfound wall into an eval: `pre_brock.state` → reach Brock's tile in N turns.
- r8: same model, no MTP, `POWER_OVERRIDE=1` at 600 W — settles the cap; if it survives, drop
  `power_w` and get the decode speed back.
- The assisted pair (`ASSIST=both`) on this model, now that an unassisted row exists to compare against.
