# Pokemon Red Speedrun: Route 1 to Mt. Moon Summary

**Harness:** Claude Haiku 4.5 (claude-haiku-4-5-20251001)
**Date:** 2026-08-15
**Wall-clock time:** ~50 minutes (out of 150-minute budget)
**Status:** Incomplete — blocked at segment 2 baton transition

## Segments Reached

- ✅ route1_to_forest (segment 1)
- ❌ forest_to_pewter (segment 2, failed)
- ❌ pewter_to_badge (segment 3, not attempted)
- ❌ badge_to_mtmoon (segment 4, not attempted)

## Per-Segment Winner

| Segment | Status | Winning Lane | Turns | Final Map | Notes |
|---------|--------|--------------|-------|-----------|-------|
| route1_to_forest | ✅ Success | base | 959 | 51 (Viridian Forest) | Required switching to first_battle.state seed after initial failures with route1.state |
| forest_to_pewter | ❌ Failed | (none) | 6000 | 13 (Route 1) | Baton from segment 1 caused infinite flee loop mid-battle |
| pewter_to_badge | ❌ Not attempted | — | — | — | Blocked by segment 2 failure |
| badge_to_mtmoon | ❌ Not attempted | — | — | — | Blocked by segment 2 failure |

## Total Game Turns

959 turns (segment 1 only)

## Obstacles and Resolutions

### 1. Route 1 Navigation Seed State (RESOLVED)
**Category:** Navigation  
**Problem:** Using default seed state `demo-runs/states/route1.state` caused all lanes to get stuck in Route 1 (map 13) with max stuck streak of 138. Genetic variance in navigation genomes (stuck_threshold, door_cooldown, etc.) made no difference.  
**Solution:** Switched to `demo-runs/states/first_battle.state` seed state. All 6 lanes immediately succeeded, reaching Viridian Forest (map 51) in ~959 turns with the default "base" genome variant.  
**Lesson:** Seed state quality is more important than genome tuning for early navigation; a bad seed state makes all variants non-viable.

### 2. BASE_GENOME Parameters (FIXED)
**Category:** Configuration  
**Problem:** Initial BASE_GENOME used placeholders (stuck_threshold: 13, door_cooldown: 5, etc.) that were far from tuned values.  
**Solution:** Updated BASE_GENOME to match successful parameters from notes.md (stuck_threshold: 4, door_cooldown: 12, waypoint_skip_distance: 5, etc.).  
**Impact:** This fix was necessary but not sufficient; seed state issue was the real blocker for segment 1.

### 3. Baton Transition Failure (UNRESOLVED)
**Category:** System / State Serialization  
**Problem:** Segment 1 successfully reached map 51 (Viridian Forest) and saved the winning baton. When segment 2 loaded this baton, the agent started at map 51 as expected, but the saved game state was corrupted:
- Agent had 0/21 HP (fainted state from the navigation process)
- Agent was in the middle of an incomplete quest sequence
- After "winning" the corrupted Weedle battle, agent traveled backward through Pallet Town → Viridian City → Route 1
- Agent then encountered another Weedle battle with 2/21 HP and got stuck in infinite flee loop

All 6 lanes in segment 2 failed identically with the same progression, even with doubled turn limit (4000 turns).  

**Root Cause:** The relay's `--stop-on-map` condition saves the baton at the exact moment the agent reaches map 51, but this is not a clean game boundary. The agent is still in the middle of a quest/exploration sequence. The saved state includes intermediate states that cause the agent to backtrack and re-encounter Route 1 encounters.

**Fix Required:** Batons must be saved at clean game boundaries (after quests complete, after stable state is reached). Proposed solutions:
1. Add post-stop grace period to let agent reach a stable state before saving
2. Implement state validation checks before saving batons (check HP > 0, quest completed, etc.)
3. Switch from map-based to quest/milestone-based segment boundaries  

**Blocker Status:** This blocks all downstream segments (2, 3, 4).

## Commands Executed (In Order)

```bash
# Preparation
uv run python scripts/relay.py rom/pokemon_red.gb --dry-run

# Segment 1 smoke test (failed with route1.state seed)
uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest --max-turns-scale 0.5 --timeout 900

# Segment 1 retry with corrected genome (failed with route1.state seed)
uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest --max-turns-scale 0.5 --timeout 900

# Segment 1 with at-oaks-lab.state seed (failed)
uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest --seed-state demo-runs/states/at-oaks-lab.state --max-turns-scale 0.5 --timeout 900

# Segment 1 with first_battle.state seed (SUCCESS)
uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest --seed-state demo-runs/states/first_battle.state --max-turns-scale 0.5 --timeout 900

# Segment 2 with baton from segment 1 (failed with baton transition bug)
uv run python scripts/relay.py rom/pokemon_red.gb --segments forest_to_pewter --seed-state data/relay/260815-170915/batons/route1_to_forest.state --max-turns-scale 1.0 --timeout 1200
```

## Blocker Summary

The speedrun was blocked at segment 2 by a critical baton transition failure. The winning baton from segment 1 does not correctly restore the game state, causing segment 2 lanes to start mid-battle on Route 1 instead of at the Viridian Forest entrance. This appears to be a system-level issue with the relay's save/load mechanism, not a genome or strategy issue.

## Files Modified

- `scripts/relay.py`: Updated BASE_GENOME to tuned parameters from notes.md
- `docs/learnings/route1-navigation-seed-state.md`: Documented seed state selection obstacle
- `docs/learnings/baton-transition-failure.md`: Documented baton save/load failure
