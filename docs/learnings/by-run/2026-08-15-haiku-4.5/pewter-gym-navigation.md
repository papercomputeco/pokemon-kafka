# Pewter Gym Navigation Blockade

note: map 58 is the Pewter **Pokémon Center**, not the Gym (the Gym is map 54; the Center door is (13,25), the routes.json waypoint the lanes walked into) — the "interior wedge" below is the agent pressing into the nurse's counter. Fixed by the building-exit rule; see `evals/cases/pewter-pokecenter-exit.json`.

**obstacle:** pewter-gym-navigation-blockade

**category:** navigation

**symptom:**
Agent successfully reaches Pewter Gym (map 58) at entrance position (13, 25) but immediately gets stuck trying to navigate interior. All variant parameters produce identical result: stuck at interior location with max_stuck_streak of ~7893 turns (agent bounces in ~4-position loop), never triggers Brock battle or badge acquisition. Even with max_turns scaled to 8000, agent doesn't progress beyond initial entry.

**failed:**
- NAV_SPREAD (all 6 variants): base, fast_stuck, patient, narrow, wide_dc2, x_axis — all stuck at map 58 interior
- Varying stuck_threshold (4-16): No improvement
- Varying door_cooldown (2-12): No improvement  
- Varying waypoint_skip_distance (1-16): No improvement
- Axis preference changes (x vs y): No improvement

**winner:** unresolved

**why it worked:** (waiting for solution)

**generalizes:**
- Interior gym/building maps may have different pathfinding requirements than overworld
- Simple navigation parameters cannot resolve all stuck scenarios
- May require special handling for trainer encounters or building mechanics

**artifacts:**
- Run: /home/bdougie/code/pcc-labs/pokemon-kafka-speedrun-pi-haiku/data/relay/260815-204936
- Report: data/relay/260815-204936/report.json
- Baton: data/relay/260815-204936/batons/pewter_to_badge.state (input from forest_to_pewter)
- Logs: data/relay/260815-204936/pewter_to_badge_retry/*/agent.log
- Fitness: data/relay/260815-204936/pewter_to_badge_retry/*/fitness.json

**detailed analysis:**

Entry Position: (13, 25) on map 2 (Pewter City) → (13, 25) on map 58 (Pewter Gym)

Stuck Positions (cycling pattern):
- (13, 4), (11, 3), (10, 3), (8, 3), (6, 3), (5, 3), (4, 3), (3, 3), (2, 3)
- Agent moves up from (13, 25) but bounces back and forth between these x-positions around y=3

Fitness Snapshot:
```json
{
  "turns": 8000,
  "battles_won": 0,
  "maps_visited": 2,
  "final_map_id": 58,
  "stuck_count": 19,
  "max_stuck_streak": 7893,
  "encounters": 0,
  "brock_won": null,
  "badges": 0
}
```

Interpretation:
- stuck_count=19 but max_stuck_streak=7893 suggests one very long stuck episode
- battles_won=0 and encounters=0 means agent never starts a Brock battle
- Agent uses most of 8000 turns stuck (7893 / 8000 = ~99%)

**next steps:**
1. Examine Pewter Gym geometry (world.map output or map data)
2. Check if gym has special mechanics (doors, trainers, level locks)
3. Consider if gym_entrance (map 54) vs gym_interior (map 58) routing is issue
4. Try hybrid approach: battle-focused variants to trigger encounter
5. If all else fails: manual state injection or skip gym
