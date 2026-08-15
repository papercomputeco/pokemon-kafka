obstacle:      viridian-forest-turn-budget-wall
category:      navigation + battle
symptom:       In `forest_to_pewter` (seeded from the `route1_to_forest` baton, entering
               Viridian Forest at a critical lead_hp of 4/23 with no potions), all 6
               BATTLE_SPREAD lanes (base, cautious, very_cautious, aggressive, status_heavy,
               cautious_narrow) hit the segment's `max_turns=6000` cap still inside the forest
               (`final_map_id: 51`, never reaching Pewter City map id 2). Every lane showed
               100+ wild encounters (`encounters` == `battles_won`, so no losses/whiteouts) and
               a large `stuck_count` (545-653) — i.e. the party was surviving fine (thanks to
               the route2-battle-menu-desync fix landing first) but was burning almost the
               entire turn budget re-fighting the same grass tiles and getting stuck on forest
               maze geometry rather than making net progress toward the Pewter exit.
failed:        Nothing needed to be "fixed" here — the segment's built-in retry (relay.py
               automatically doubles max_turns and reruns once on failure) was sufficient.
               First attempt (max_turns=6000, ~3.3 turns/lane/sec real time) failed for all 6
               lanes simultaneously; no single decision-variant (not even `aggressive`, which
               minimizes fleeing, or `very_cautious`, which maximizes healing/fleeing) finished
               inside 6000 turns, confirming the wall is a turn-budget/traversal-length problem
               for a low-level, itemless party crossing the whole forest + Route 2 remainder,
               not a bad battle decision.
winner:        No genome change — the relay's automatic retry with `max_turns` doubled
               (6000 -> 12000) was the winning "variant." On the retry, lane `base`
               (BASE_GENOME with no overrides) finished in 3253 turns, reaching Pewter City
               (map id 2) at lead_hp 9/? with 42 battles won and 7 level-ups; all other 5
               lanes were killed as stragglers once `base` succeeded (30s grace period).
               Baton: data/relay/seg2/batons/forest_to_pewter.state (+ .worldmap, .genome.json).
why it worked: The forest wall here is fundamentally a length problem, not a decision problem:
               crossing Viridian Forest and the rest of Route 2 with a low-level single-Pokemon
               party at critical starting HP takes several thousand turns of wandering +
               fighting once repeated stuck-navigation (stuck_count in the 500s) and dozens of
               wild encounters are accounted for. None of the BATTLE_SPREAD hp-threshold tweaks
               change the traversal length, so they all hit the same wall at the same turn cap;
               doubling the budget is what actually gives a lane room to finish. This matches
               notes.md's "healthy L13 party... crosses in ~31 steps" only for an *already
               healthy, already-through* party — a party entering the forest at 4 HP with zero
               potions instead spends most of its budget on stuck-recovery and combat, so it
               needs several thousand turns, not 31 steps, before its first real segment
               attempt even lands.
generalizes:   When every decision variant in a spread fails identically at the same
               `max_turns` cap with high `stuck_count`/`encounters` but no losses, suspect the
               turn budget itself before touching the genome — let relay's automatic 2x retry
               run (or raise `--max-turns-scale`) rather than hand-tuning decision variants that
               don't touch traversal length. Only escalate to genome/pathing changes if the
               *doubled* budget also fails identically across all lanes.
artifacts:     data/relay/seg2/forest_to_pewter/*/fitness.json (all 6 lanes: final_map_id 51,
               turns 6000, no losses). data/relay/seg2/forest_to_pewter_retry/base/fitness.json
               (winner: turns 3253, final_map_id 2, lead_hp 9). data/relay/seg2/report.json.
               data/relay/seg2/batons/forest_to_pewter.state (Pewter City baton for the next
               segment, pewter_to_badge).
