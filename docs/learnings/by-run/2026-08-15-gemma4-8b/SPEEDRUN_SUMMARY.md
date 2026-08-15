# Pokémon Red Speedrun Relay Summary

**Harness/Model:** Gemma 4, operated by expert coding assistant.
**Total Segments Attempted:** 4
**Total Game Turns:** Unknown (Completed 2/4 segments)
**Wall Clock Time:** Significant time spent on simulations, but unable to complete the full relay.

## Achievements Summary

*   **route1_to_forest:** SUCCESS
    *   Winner Variant: `base`
    *   Turns: 908
    *   Baton State: `data/relay/260815-230505/batons/route1_to_forest.state`
*   **forest_to_pewter:** SUCCESS
    *   Winner Variant: `aggressive`
    *   Turns: 1302
    *   Baton State: `data/relay/260815-230519/batons/forest_to_pewter.state`
*   **pewter_to_badge:** FAILED (Unresolved)
    *   Winner Variant: None
    *   Segments Reached: N/A
    *   Blocks: The progression is blocked at Pewter City, specifically the gym battle with Brock or the navigation via Route 3. Multiple runs failed, indicating the current genome/variant set is insufficient to pass this high-variance mechanical obstacle.
*   **badge_to_mtmoon:** FAILED (Blocked)
    *   Reason: Missing baton state from the previous segment's failure.

## Commands Run in Order

1. `uv run python scripts/relay.py rom/pokemon_red.gb --dry-run --dry-run` (Sensibility Check)
2. `uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest --max-turns-scale 0.5 --timeout 900` (V-Forest Smoke Test)
3. *Changes made to scripts/relay.py: Updated BASE_GENOME for safer combat.*
4. `uv run python scripts/relay.py rom/pokemon_red.gb --segments route1_to_forest --max-turns-scale 0.5 --timeout 900` (V-Forest Run)
5. `uv run python scripts/relay.py rom/pokemon_red.gb --segments forest_to_pewter --seed-state data/relay/260815-230505/batons/route1_to_forest.state --max-turns-scale 0.5 --timeout 900` (Forest Run)
6. `uv run python scripts/relay.py rom/pokemon_red.gb --segments pewter_to_badge --seed-state data/relay/260815-230519/batons/forest_to_pewter.state --max-turns-scale 0.5 --timeout 900` (Pewter Attempt 1)
7. `uv run python scripts/relay.py rom/pokemon_red.gb --segments pewter_to_badge --seed-state data/relay/260815-230519/batons/forest_to_pewter.state --max-turns-scale 1.0 --timeout 1200` (Pewter Attempt 2 - Failed)
8. *Changes made to scripts/relay.py: Updated BASE_GENOME for extreme caution (hp_run_threshold: 0.05, hp_heal_threshold: 0.1).*
9. `uv run python scripts/relay.py rom/pokemon_red.gb --segments pewter_to_badge --seed-state data/relay/260815-230519/batons/forest_to_pewter.state --max-turns-scale 1.0 --timeout 1200` (Pewter Attempt 3 - Failed)
10. `uv run python scripts/relay.py rom/pokemon_red.gb --segments badge_to_mtmoon --seed-state data/relay/260815-231157/batons/pewter_to_badge.state --max-turns-scale 0.5 --timeout 900` (Mt. Moon Attempt - Blocked by missing state)
