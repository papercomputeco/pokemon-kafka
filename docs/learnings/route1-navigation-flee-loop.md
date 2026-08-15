obstacle:      route1-navigation-flee-loop
symptom:       Agent reaches Route 2 (map 13) with low HP (4/23), tries to run from Weedle, fails to escape, and enters an infinite run loop (1317+ turns) until max_turns is exhausted. All variants produce identical fitness because the deterministic save state drives the same quest path and RNG seed.
category:      navigation | battle
failed:        -
  variant: base genome (stuck_threshold=13, hp_run_threshold=0.2)
  failure: Same flee-loop because the stall-guard run path in choose_action has no cap; once _wild_fight_turns>=10 it returns "run" forever without checking _run_attempts.
  variant: fast_stuck / patient / narrow / wide_dc2 / x_axis
  failure: Identical results because the parcel_quest GO_NORTH phase overrides navigator decisions with deterministic pilot("north"); battle RNG is fixed by the save state.
winner:        Updated BASE_GENOME to notes.md autotuned values (stuck_threshold=11, door_cooldown=6, waypoint_skip_distance=2, hp_run_threshold=0.25, hp_heal_threshold=0.3, etc.) plus a stall-run cap in agent.py BattleStrategy.choose_action: after 10 stall-guard run attempts, fall back to fight with move_index 0.
why it worked:  The notes genome shifts the low-HP run threshold from 0.2 to 0.25, which changes when the agent tries to flee vs fight. More importantly, the flee-loop cap prevents the agent from burning all turns when escape RNG is unfavorable; falling back to fight lets Scratch land damage, break the stall counter, and eventually KO the Weedle. Without the cap, the stall-guard path returns "run" unconditionally once _wild_fight_turns>=10, creating an infinite loop because "run" turns do not advance _wild_fight_turns.
generalizes:   When a wild battle stalls (no enemy HP progress for WILD_BATTLE_PATIENCE turns), always cap the recovery run attempts and fall back to the highest-damage move; never let a single recovery heuristic consume the entire turn budget.
artifacts:     data/relay/260815-190913/batons/route1_to_forest.state, data/relay/260815-190913/report.json, data/relay/260815-190913/route1_to_forest/*/agent.log
