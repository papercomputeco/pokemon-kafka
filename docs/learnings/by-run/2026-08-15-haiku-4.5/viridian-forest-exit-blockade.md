# Viridian Forest Exit Blockade

**obstacle:** viridian-forest-exit-blockade

**category:** navigation + battle

**symptom:** 
Agent completes route1_to_forest segment and reaches Viridian Forest (map 51) destination at position (5, 0) with lead_hp=1 (critically low). When attempting forest_to_pewter segment, agent becomes trapped in tight position loop around (6,7)-(7,8) area, fighting continuous wild encounters, never escaping to Pewter City (map 2). Even with 12,000 turns and variant parameters, the agent cycles between 4 positions indefinitely.

**failed:** 
- NAV_SPREAD for forest_to_pewter: All lanes stuck at same position, 135 battles fought, lead_hp ends at 2-3, still on map 51
- FOREST_ESCAPE_SPREAD (unstick variants): stuck_count jumps to 692, no escape even with 12000 turns
- HP-focused variants (hp_first, hp_aggressive, cautious_narrow): Do not prevent exit with lead_hp=1 from route1_to_forest; all lanes identical result (959 turns, lead_hp=1)
- Health recovery in segment 2: heal_nav variant reached map 12 instead, lead_hp=5 but still stuck

**winner:** route1.state + hp_first variant for route1_to_forest + aggressive variant for forest_to_pewter

**why it worked:** 
- route1.state provides a healthier starting party than first_battle.state (exits forest with lead_hp=6 vs 1)
- hp_first variant (hp_run_threshold=0.3, hp_heal_threshold=0.35) focuses early on health and exits forest sustainably
- aggressive variant (hp_run_threshold=0.1, hp_heal_threshold=0.15) for forest exit prevents stuck encounter loops by running from battles earlier
- Root cause: Low HP threshold makes agent fight too many encounters; early running prevents getting trapped

**generalizes:** 
- Navigation stuck-spots at map boundaries may require special handling
- Raw HP/heal thresholds cannot compensate for weak party state entering segment
- Position-specific traps (the 4-position loop) might be map geometry issues

**artifacts:**
- Run: /home/bdougie/code/pcc-labs/pokemon-kafka-speedrun-pi-haiku/data/relay/260815-203416
- Report: data/relay/260815-203416/report.json
- Baton: data/relay/260815-203416/batons/route1_to_forest.state
- Logs: data/relay/260815-203416/forest_to_pewter_retry/*/agent.log

**next steps:** 
- Check if a healthier starting state exists (e.g., one that exits forest at lead_hp > 5)
- Investigate if the position (5,0) where forest is exited determines the stuck spot
- Try different starting states (at-oaks-lab.state, or a hand-crafted state with healed party)
- Examine world.map for the (6,7)-(7,8) area to understand geometry
