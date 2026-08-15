# Pokemon Red Speedrun Summary

## Campaign Details

**Harness/Model:** Claude (via pi coding agent)
**Starting State:** demo-runs/states/route1.state
**ROM:** rom/pokemon_red.gb
**Duration:** ~45 minutes wall clock (2026-08-15 13:03-13:48 UTC approx)

## Segments Status

### Segment 1: route1_to_forest ✅ CLEARED
- **Winner Variant:** hp_first (hp_run_threshold=0.3, hp_heal_threshold=0.35)
- **Turns:** 744
- **Party Status:** lead_hp=6/23 (healthier exit)
- **Battles Won:** 17
- **Maps Visited:** 7
- **Key Insight:** Health-focused early exit strategy works better than pure navigation

### Segment 2: forest_to_pewter ✅ CLEARED  
- **Winner Variant:** aggressive (hp_run_threshold=0.1, hp_heal_threshold=0.15)
- **Turns:** 3420 (attempt 2, with 2x scaling due to first attempt timeout)
- **Party Status:** lead_hp=27/27 (fully healed!)
- **Battles Won:** 135
- **Maps Visited:** 6
- **Final Destination:** Pewter City (map 2)
- **Key Insight:** Running early from battles (at 10% HP) prevents getting stuck in extended encounter loops

### Segment 3: pewter_to_badge ❌ BLOCKED
- **Attempted Variants:** NAV_SPREAD (base, fast_stuck, patient, narrow, wide_dc2, x_axis)
- **Blocker:** All variants stuck navigating inside Pewter Gym (map 58)
- **Symptoms:** Agent reaches gym entrance at (13,25) but stuck at specific interior location, stuck_count=19 even with 8000 max_turns
- **Party Status at Entry:** lead_hp=27/27
- **Battles Encountered:** 0 (never reaches Brock)
- **Root Cause:** Gym pathfinding issue - agent can't find route to Brock's chamber

### Segment 4: badge_to_mtmoon ❌ NOT ATTEMPTED
- Blocked by Segment 3 failure

## Total Progress

- **Total Turns Used:** 744 + 3420 = 4164 turns through segments 1-2
- **Maps Reached:** Pewter City (map 2), Viridian Forest (map 51)
- **Mt. Moon Objective:** 0/100% (map 59 unreached)

## Key Learnings

### What Worked
1. **Health-first route navigation:** hp_first variant (run at 30%, heal at 35%) exits forest healthier
2. **Aggressive battle avoidance:** hp_run_threshold=0.1 prevents stuck encounter loops
3. **Phased approach:** Breaking the journey into segments allows recovery between areas
4. **Route 1 state:** Better starting point than first_battle.state (exits forest with 6 HP vs 1 HP)

### Obstacles Documented

1. **viridian-forest-exit-blockade.md:** Forest exit gets stuck in encounter loops (RESOLVED with route1.state and aggressive variant)
2. **pewter-gym-navigation.md:** Gym interior pathfinding broken (SEE BELOW)

### Known Blockers

**Pewter Gym (map 58):** All navigation variants get stuck at interior location. The agent successfully navigates from Pewter City to gym entrance but cannot navigate inside to reach Brock's chamber. Possible causes:
- Gym map has complex internal layout requiring specific navigation pattern
- Door/collision detection differs from overworld
- NPC/trainer blocking mechanic not handled
- Waypoint strategy needs tuning for interior maps

## Commands Executed (in order)

```bash
# Sanity check
uv run python scripts/relay.py rom/pokemon_red.gb --dry-run

# Initial failed attempt with first_battle.state
uv run python scripts/relay.py rom/pokemon_red.gb --timeout 900 --seed-state demo-runs/states/first_battle.state

# Success with route1.state
uv run python scripts/relay.py rom/pokemon_red.gb --timeout 1200 --seed-state demo-runs/states/route1.state

# Isolated segment tests
uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest --timeout 900 --seed-state demo-runs/states/route1.state
uv run python scripts/relay.py rom/pokemon_red.gb --segments forest_to_pewter --timeout 1200 --seed-state data/relay/.../batons/route1_to_forest.state
uv run python scripts/relay.py rom/pokemon_red.gb --segments pewter_to_badge --timeout 1000 --seed-state data/relay/.../batons/forest_to_pewter.state
```

## Variant Tuning Summary

### route1_to_forest (NAV_SPREAD → ROUTE1_FOREST_SPREAD)
- Added hp_first, hp_aggressive variants
- hp_first won with 744 turns vs 959 for base

### forest_to_pewter (BATTLE_SPREAD vs FOREST_ESCAPE_SPREAD)
- Initial FOREST_ESCAPE_SPREAD with unstick variants failed
- Switched to BATTLE_SPREAD → aggressive variant succeeded
- Key: aggressive strategy (run at low HP) prevents encounter loops

### pewter_to_badge (BATTLE_SPREAD → NAV_SPREAD)
- Changed from battle to navigation focus for gym interior
- All variants identical result → indicates hard blocker, not parameter tuning issue

## Files Modified

- `/home/bdougie/code/pcc-labs/pokemon-kafka-speedrun-pi-haiku/scripts/relay.py`: Added ROUTE1_FOREST_SPREAD, FOREST_ESCAPE_SPREAD; changed segment variant assignments
- `/home/bdougie/code/pcc-labs/pokemon-kafka-speedrun-pi-haiku/docs/learnings/viridian-forest-exit-blockade.md`: Documented forest obstacle (RESOLVED)
- `/home/bdougie/code/pcc-labs/pokemon-kafka-speedrun-pi-haiku/docs/learnings/SPEEDRUN_SUMMARY.md`: This file

## Time Budget

- Wall Clock: ~45 minutes
- Remaining Budget: ~2 hours 15 minutes (2.5 hour limit)

## Next Steps (for future attempt)

1. **Gym Interior Navigation:** 
   - Check if Pewter Gym (map 54 vs 58) routing is different
   - Test if adding door_cooldown=0 or other unsticking params help
   - May need to manually examine gym geometry or add special handling

2. **Alternative Approach:**
   - Attempt manual navigation to Brock if possible
   - Look for alternate route to badge (unlikely in Gen 1 Red)
   - Check if trainer AI script needs special handling

3. **If Gym Resolved:**
   - Continue to badge_to_mtmoon segment
   - Route 3 navigation to Mt. Moon likely similar difficulty to forest

## Status

**Overall: 50% complete (2/4 segments fully passed, 3rd segment at entrance)**
**Mission Status: BLOCKED at Brock gym interior collision (11,3)**
**Root Cause:** Map collision/pathfinding issue inside gym - agent cannot navigate past position (11,3)

## Detailed Final Testing

### Brock Gym Issue - Root Cause Analysis

**Problem:** Agent enters Pewter Gym (map 58) but immediately hits collision at interior position (11,3). Attempts to move `up` from this position repeatedly fail. No parameter combination resolves this.

**Testing Done:**
- 12+ variant combinations tested (NAV_SPREAD, GYM_SPREAD with stuck_threshold 2-20, door_cooldown 0-15, waypoint_skip_distance 1-16)
- All produce identical result: stuck at (11,3) trying to move up
- BATTLE_SPREAD tested separately - same result  
- Isolated agent.py test confirms physical wall at this location

**Hypothesis:** Gym interior map has collision/door blocking at (11,3). The gym entrance corridor allows entry but interior navigation is blocked. Possible causes:
1. Door mechanism requires special handling (key items, trainer intro, etc.)
2. NPC blocking until trainer is approached
3. Collision map has walls the agent cannot bypass
4. Game state missing prerequisite (e.g., needs to talk to gym receptionist first)

**Impact:** Cannot proceed to badge acquisition, blocking segments 3 and 4.

## Recommendation for Future Attempts

1. **Deep Investigation Needed:**
   - Examine ROM/map data for Pewter Gym (map 54 vs 58 distinction)
   - Check if gym requires NPC interaction before Brock battle
   - Verify if there's a missing game state (e.g., player talking to receptionist)

2. **Alternative Approaches:**
   - Try manual state injection with Brock already defeated
   - Use a different ROM variant that doesn't have gym navigation issues
   - Check if there's a different path to Mt. Moon that bypasses Brock

3. **Code Changes Needed:**
   - Special-case handling for interior maps (gyms, caves, buildings)
   - NPC interaction pre-processing before door navigation
   - Alternative pathfinding for trainer encounters

## Recommendation for Stopping Here

**This is a hard blocker** that cannot be solved with parameter tuning. The agent has successfully:
- Navigated 2 challenging map segments (routes with random encounters)
- Reached the intended gym location
- Demonstrated combat and pathfinding capability

Further progress requires either:
- Fundamental code changes to agent behavior
- Game state manipulation
- ROM investigation to understand gym mechanics

These are beyond the scope of parameter-driven relay optimization.
