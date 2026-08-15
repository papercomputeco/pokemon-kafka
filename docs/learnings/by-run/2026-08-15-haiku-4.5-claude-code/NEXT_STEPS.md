# Next Steps for Pokemon Red Speedrun

## Current Status
- **Segment 1 (route1_to_forest)**: ✅ SUCCESS (959 turns, reached map 51 Viridian Forest)
- **Segment 2+ (forest_to_pewter onwards)**: ❌ BLOCKED by baton transition failure

## Critical Issue to Resolve
The baton saved at the end of segment 1 includes unresolved quest state. When loaded for segment 2, the agent:
1. Starts at map 51 as expected
2. Continues the interrupted quest sequence
3. Backtracks through Pallet Town → Viridian City → Route 1
4. Gets stuck in infinite flee loop on Route 1

**Root Cause**: `--stop-on-map` saves at the exact moment the target map is reached, but the agent is mid-quest and continues moving when the baton is loaded.

## Recommended Fixes (in priority order)

### Fix 1: Post-Stop Stabilization (RECOMMENDED)
Modify `relay.py` to add a grace/idle period after hitting the stop condition:
- After `--stop-on-map` condition is met, wait additional N turns
- Let the agent complete or reset its internal quest state
- Save baton only when agent reaches a stable state (overworld, no active quest)
- Implementation: Check for "OVERWORLD" log entries with low stuck count before saving

**Effort**: Medium (requires log parsing to detect stable state)  
**Likelihood of Success**: High

### Fix 2: Quest-Aware Segment Boundaries
Instead of `--stop-on-map`, use quest completion or badge acquisition:
- Segment 1: Stop when 1st gym badge is acquired (pewter_to_badge already uses --stop-on-badge)
- Segment 2: Stop when reaching Pewter City gym (map 54)
- This naturally creates clean game boundaries

**Effort**: Low (modify SEGMENTS dataclass, adjust game maps)  
**Likelihood of Success**: High

### Fix 3: Baton Validation/Repair
Create a post-processing tool that loads a baton and runs it forward until stabilized:
```python
# Pseudo-code
state = load_baton(path)
agent.load_state(state)
agent.run(max_turns=500)  # Let agent settle
# Check stability: low HP, not in battle, not moving
if is_stable(agent.state):
    save_baton(agent.state, path + ".repaired")
```

**Effort**: Medium-High  
**Likelihood of Success**: Medium (depends on detecting "stable" correctly)

### Fix 4: Different Seed States per Segment
Instead of using batons, use pre-made seed states for each segment:
- Create first_battle state versions at each key point (after forest, after Brock, etc.)
- Trade off baton continuity for guaranteed clean state boundaries

**Effort**: Low  
**Likelihood of Success**: Low (requires manual game state creation)

## Testing Strategy for Next Attempt

1. **Test Fix 1** first (low-risk, high-reward)
2. If Fix 1 doesn't work, implement **Fix 2** (simplest code change)
3. Run full chain: segments 1-4 with whichever fix works
4. Document turn counts, wall-clock time, and per-segment winners

## Code Changes Required

### If implementing Fix 1 (Post-Stop Stabilization)
```python
# In relay.py, after run_segment() returns a winner:
if winner is not None:
    # Run a short stabilization phase
    stabilized_state = stabilize_baton(
        winner["vdir"] / "stop.state",
        agent_path=SCRIPT_DIR / "agent.py",
        max_stabilize_turns=500,
        stability_threshold=50  # stuck_count < 50
    )
    baton = promote_winner(run_dir, seg, winner)  # Use current logic
```

### If implementing Fix 2 (Quest-Aware Boundaries)
```python
# Modify SEGMENTS:
SEGMENTS = (
    Segment("route1_to_forest", MAPS["VIRIDIAN_FOREST"], None, 4000, NAV_SPREAD),
    Segment("forest_to_pewter", MAPS["PEWTER_CITY"], None, 6000, BATTLE_SPREAD),
    # ... rest unchanged
)
# Change: Use destination maps based on game progression, not intermediate maps
```

## Success Criteria for Future Run

- [ ] Segment 1: route1 → Viridian Forest (map 51) in < 1200 turns
- [ ] Segment 2: Viridian Forest → Pewter City (map 2) in < 2000 turns with < 50% stuck streaks
- [ ] Segment 3: Pewter City → Brock badge (badge count = 1) in < 1500 turns
- [ ] Segment 4: Pewter → Mt. Moon entrance (map 59) in < 2000 turns
- [ ] **Total**: < 7000 turns, < 120 minutes wall-clock
