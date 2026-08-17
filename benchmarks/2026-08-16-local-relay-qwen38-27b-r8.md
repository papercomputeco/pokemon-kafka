# 2026-08-16 — qwen38-27b r8: stock 600 W, no MTP draft — the cap was never the cause

`RUN_TAG=qwen38-27b-r8 ASSIST=none POWER_OVERRIDE=1 scripts/local_relay_run.sh qwen38-27b main`,
worktree off `main` (`d851b05`). One variable changed from r7: the card back at its **stock 600 W**
(`sudo nvidia-smi -pl 600`), MTP draft still off. The preflight refused, as designed, and the run went
ahead under `POWER_OVERRIDE=1` — the launcher logged *"running uncapped; do not publish this row as a
verdict"*, which is why this file is an **experiment**, not a model row for the comparison tables.

## The result

| run | MTP draft | cap | wall | how it ended | GPU power |
|---|---|---|---|---|---|
| attempt 1, r3, r4, r5 | **on** | 600 W | 2.7 – 8.3 m | `Xid 8` | mean ~406 W, peaks 602-610 |
| r6 | **on** | 480 W | 8.1 m | `Xid 8` | mean 397 W, 71/98 samples ≥ 470 |
| r7 | off | 480 W | 84.1 m | ended by choice | mean 421 W, 83 % ≥ 470 |
| **r8** | off | **600 W (stock)** | **16.8 m** | **ended by choice** | **mean 509 W, max 608, 161/210 (77 %) ≥ 590** |

r8 spent three quarters of its life above 590 W — the regime that killed four runs in under nine
minutes — and the kernel log for the window is clean. The guard passed the row. **The 480 W cap was
a correlate, not the cause; Ollama's MTP speculative draft was.**

The caveat, stated plainly: r8 is 17 minutes, not 84. It beat every 600 W death time by 2×+ while
pinned in the same power band, which is why the conclusion is drawn — but it is one short run, and a
future `Xid` under a long uncapped run would reopen it. That is a cheap thing to be wrong about: the
harness-death guard refuses the row automatically, so the failure mode is a lost run, not bad data.

**Roster change:** `power_w` is removed from `qwen38-27b`. The `power` preflight, the `Spec.power_w`
field and the launcher gate all stay — the mechanism works and is tested; nothing on the roster needs
a cap today. Capping cost speed: r8 decoded at **61.4 out tok/s vs r7's 52.7** (+17 %) and ran
11.1 s/turn vs 24.8 (the turn figure is confounded — r7 carried far bigger contexts and 4 compactions).

## The row it produced

| model | segs | wall | model time | turns | tools | out tok/s | s/turn | input tok | output tok | cloud $ | Wh | energy $ | max ctx | compactions | code fix | learnings | commits |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| qwen38-27b r8 (local, 128k, **uncapped**, no MTP) | 2/4 | 16.8 m | 14.1 m | 76 | 88 | 61.4 | 11.1 | 3.68 M | 51.9 k | $0.57 | 148.7 | $0.045 | 89.7 k | 1 | yes — `agent.py` settle-gate, 3 tests | 4 (by-run) | 2 |

Segments: `route1_to_forest` winner `base` 868 turns / 7 HP; `forest_to_pewter` winner `very_cautious`
1045 turns / 12 HP; `pewter_to_badge` none (4000 and 8000 turns, 24 battles won, `brock_won=None`,
badges 0); `badge_to_mtmoon` not attemptable without the badge baton.

## What the model did with 17 minutes

Ended **by its own choice** at 16 min ("far inside the 2.5 h budget"), which is the one debatable
call of the run — it had 2.4 h left and a named, unsolved blocker. What it did with the time was
investigator work, not knob-tuning:

- **A code fix with tests** (`b5b283f`, `scripts/agent.py`): the relay stop/baton state is now dumped
  only once the overworld reads as settled (position inside the live `read_map_bounds()` header,
  polled ≤240 frames), and refused otherwise, so a bad save scores a miss instead of handing the next
  segment a warp-to-anywhere state. 3 regression tests.
- **Refuted a standing theory with evidence.** The 2026-08-15 "corrupted transition baton" story does
  not explain the Brock failure: pre- and post-fix `forest_to_pewter` batons are byte-identical
  (md5 `343f2e45…`) and (18,35) is inside the live Pewter header. Written up as
  `baton-integrity-refuted.md` so the next operator does not misattribute a navigation bug to the
  state manager. *Refuting a plausible prior is rarer here than proposing a new one.*
- **Named the Brock blocker as a triad**: no map-54 interior waypoints in `references/routes.json`;
  a single self-poisoned Charmander at 8 HP by the door; no in-game heal path (`healer.py` is a
  parameter race, and the lanes run `--no-self-heal`). All six lanes byte-identical because
  BATTLE_SPREAD varies wild-flee only, never navigation.
- **Honest about what it did not do.** `route3-to-mtmoon.md` reads "N/A — not attempted", explains
  the baton dependency, and declines to guess coordinates. Every number in its final summary matches
  the reports (checked: winner lanes, turns, `brock_won`, badges). No fabrication.

Two runs, two different real fixes (r7: `world_map.py` livelock; r8: `agent.py` baton settle-gate),
both with tests, neither one a genome tweak. The §10 verdict — **investigator, not driver** — is now
backed by four independent runs.

## Next

- Both fixes want review for `main`: `speedrun/pi-qwen38-27b-r7` (`265309c`, `4219d7c`) and
  `speedrun/pi-qwen38-27b-r8` (`b5b283f`). Cherry-pick the code and tests, leave the run-output commits.
- The Brock triad is the wall now, and r8 named the cheapest lever: map-54 interior waypoints in
  `routes.json` from emulator-verified coordinates, plus a heal path before the Gym.
- `ASSIST=both` on this model — two unassisted rows now exist to compare against.
- The cap question is closed unless an `Xid` returns; if one does, the guard will say so.
