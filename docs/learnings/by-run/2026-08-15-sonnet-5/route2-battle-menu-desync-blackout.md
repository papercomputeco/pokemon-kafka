obstacle:      route2-battle-menu-desync-blackout
category:      battle
symptom:       Every `route1_to_forest` lane (all 6 NAV_SPREAD variants: base, fast_stuck,
               patient, narrow, wide_dc2, x_axis) hit a hard wall on Route 2 (map id 13),
               well before Viridian Forest (map id 51). Once a wild battle started there, the
               lane never returned to the overworld for the rest of its turn budget (0
               `OVERWORLD` log lines after entering battle; only 5 "Battle ended" events fired
               in an entire 4000-turn run). Player HP froze at a single critical value (e.g.
               4/23) for thousands of consecutive turns — `run` was chosen repeatedly (and
               burned its 3-attempt cap), then fell through to `fight`, but zero `MOVE |`
               lines were ever logged after that point: neither `run` nor `fight` was landing.
               `report.json` showed every lane's `final_map_id: 13`, `turns: 4000` (both the
               2000- and 4000-turn attempts) with no baton produced.
failed:        (1) Re-running the same command with a longer timeout/second attempt (relay's
               built-in 2x max_turns retry) — no effect, since the lane wasn't slow, it was
               stuck in a desynced battle menu forever. (2) All 6 NAV_SPREAD variants
               (stuck_threshold, door_cooldown, waypoint_skip_distance, axis_preference) —
               irrelevant, because the failure was inside battle handling, not overworld
               pathing; none of these params touch battle behavior. (3) Hypothesized "no
               potions in bag" as the root cause (bag_healing always None, hp_heal_threshold
               never triggers) — true but a red herring for *this* wall: HP was frozen, not
               declining, so the party wasn't being ground down by lost fights; the real bug
               was that button inputs for `run` (and subsequently `fight`) were not registering
               at all, most likely because Weedle/Rattata status moves (String Shot / Growl)
               leave extra text boxes that our fixed-timing `battle_menu_select("run")` +
               `wait(120)` sequence doesn't account for, silently eating the RUN menu press.
winner:        Made the `run` action confirm-and-retry like the existing `fight` action already
               did (using the same `_await_turn_resolved` helper), and added a stall watchdog
               for wild battles: once `_wild_fight_turns >= WILD_BATTLE_PATIENCE` and the lane
               keeps choosing RUN turn after turn without the battle ever resolving, every 4th
               stalled turn it now sends `unstick` (mash B) instead of RUN to clear a
               potentially desynced battle menu before trying RUN again. Genome diff: none
               required — this was a `scripts/agent.py` code fix, not a genome/variant tune.
                 - `run` branch: wrapped `battle_menu_select("run")` in a 3-attempt loop that
                   calls `_await_turn_resolved(...)` and backs out with `press("b")` if the turn
                   didn't resolve, mirroring the existing fight-retry comment about "the
                   fixed-timing menu occasionally catches mid-animation."
                 - `choose_action` wild-stall branch: added `_wild_stall_runs` counter, reset in
                   all the same places `_wild_fight_turns`/`_run_attempts` already reset (new
                   enemy species, real damage dealt, battle end), and every 4th stalled turn
                   returns `{"action": "unstick"}` instead of `{"action": "run"}`.
               Result: `route1_to_forest --max-turns-scale 0.5 --timeout 900` went from 0/6
               lanes succeeding (all stuck on Route 2 at 2000/4000 turns) to 6/6 lanes reaching
               Viridian Forest (map 51) in 750 turns each, winner `base`
               (`data/relay/seg1_smoke2/batons/route1_to_forest.state`).
why it worked: The agent's fight-turn code already knew menu selections can silently fail to
               register when a text box/animation is still playing ("observed ~50% of hits
               missing vs Brock, enemy HP frozen for many turns" — see the comment above the
               fight retry loop) and had a retry-with-confirmation loop to handle it. The `run`
               branch never got the same treatment — it fired the RUN button once and just
               hoped. On Route 2, back-to-back low-level encounters (Weedle/Rattata) with
               status moves produce more incidental text boxes than the Route-1 encounter
               table the code was originally tuned against, so the un-confirmed RUN press
               missed far more often, and the lane was left repeating the exact same frozen
               battle state (RUN chosen because HP never changes, HP never changes because RUN
               never actually executes) until the turn budget ran out. Confirming the RUN press
               the same way FIGHT is confirmed closes that gap; the periodic `unstick` add-on
               is a second line of defense for the case where even three confirm-retries land
               mid-animation, borrowed directly from the existing trainer-battle stall recovery
               a few lines below (which already does exactly this for battle_type 2).
generalizes:   Any time a lane's `fitness.json`/`agent.log` shows a *frozen* HP value repeated
               across hundreds/thousands of turns with the SAME action chosen over and over
               (not oscillating, not declining) and zero `OVERWORLD` lines after some map, treat
               it as a menu/input desync bug in `agent.py`'s battle-turn execution — not a
               genome/decision-variant problem, and not a "the strategy chose the wrong action"
               problem. The fix is almost always to make the desynced action self-confirming
               (retry against `_await_turn_resolved` or an equivalent "did the state actually
               change" check) rather than firing-and-hoping, and/or to add a periodic `unstick`
               (mash B) escape hatch to the stall guard. Reach for this before touching
               NAV_SPREAD/BATTLE_SPREAD genome knobs, since those only matter once actions are
               reliably executing.
artifacts:     data/relay/seg1_smoke/ (pre-fix failing run: 0/6 lanes, report.json shows
               final_map_id 13 turns 4000/2000 for every lane, agent.log tail shows the frozen
               "Player HP: 4/23 ... Action: run"/"Action: fight" loop with zero `MOVE |` lines).
               data/relay/seg1_smoke2/ (post-fix passing run: report.json winner "base", turns
               750, batons/route1_to_forest.state + .worldmap + .genome.json). Code fix:
               scripts/agent.py (`run` action retry loop + `_wild_stall_runs` watchdog).
