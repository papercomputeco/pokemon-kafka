obstacle:      pewter-party-health (arriving at Brock with no HP and no way to get any)
category:      resource
symptom:       Every lane that reached the Pewter Gym reached it dying. Measured on unmodified
               `main` from the staged arrival (`data/probe/b`): lead enters map 54 at 32/48, the
               Gym's Jr. Trainer (Diglett L11 + Sandshrew L11) takes it to **3/48**, and the next
               contact is a whiteout — `MAP CHANGE | 54 -> 0`, respawn in Pallet Town, ~1100 turns
               to walk back. The staged `pre_brock_*` seeds carry 8 and 15 HP for the same reason.
               No lane in any prior run had ever entered the Pewter Pokemon Center (map 58).
failed:        -
  variant: BATTLE_SPREAD lanes (`hp_run_threshold` / `hp_heal_threshold` 0.15 - 0.5)
  failure: Both parameters gate on holding a healing ITEM; the lane holds none, so all six lanes
           take the identical branch and produce byte-identical fitness. Tuning a threshold cannot
           create HP.
  variant: `healer.py` / `--no-self-heal` (the repo's "heal")
  failure: Not an in-game heal at all — it is a genome parameter race between lanes. Every lane in
           this segment runs `--no-self-heal --no-in-run-heal` anyway. The word "heal" in this
           harness had never meant hit points, which is why nobody looked for a Center.
  variant: whiteout-as-heal (do nothing and let the game full-heal you at Pallet)
  failure: It IS a full heal, but it costs ~1100 turns of walking back plus the Viridian Forest
           re-crossing, and the lane re-enters the Gym at whatever HP the return trip leaves it —
           probe B never made it back to Pewter at all inside 1200 turns.
winner:        `scripts/agent.py::_pewter_heal_action`, a three-leg in-game Pokemon Center loop
               that runs before any other overworld decision and only while `badges & 0x01 == 0`:
               - map 2, lead HP ratio < `PEWTER_HEAL_GATE` (0.85): pilot to the Center door warp
                 (13,25) — read from the map's warp table, not guessed;
               - map 58: pilot to the nurse tile (3,3), then alternate `up`/`a` until HP is full,
                 then return `None` so the existing `_building_exit` walks the lane back out;
               - map 54, ratio < `PEWTER_GYM_RETREAT_GATE` (0.9): pilot to the nearest warp so a
                 lane that got chewed up by the Jr. Trainer LEAVES and heals instead of walking
                 into Brock at 12 HP.
               Bounded by `PEWTER_MAX_HEAL_TRIPS = 6` so a broken nurse dialog cannot become an
               infinite loop. Measured: 32/48 -> 48/48 in ~25 turns (`data/probe/c`), and in the
               winning relay lanes the retreat leg fires once after the Jr. Trainer.
why it worked: The fix was already in the game, on the map the lane was already standing on, ~25
               turns away — and the harness had spent four runs looking for it in the genome. The
               retreat gate is the half that actually wins the badge: healing before the Gym is
               not enough, because the Jr. Trainer sits between the door and Brock and takes
               12-30 HP, so the lane needs to be able to walk back OUT mid-Gym. The gates are
               deliberately high (0.85 / 0.9) rather than the genome's 0.15-0.5: turns are cheap
               here (a round trip is ~50) and a whiteout costs 1100 plus the badge.
generalizes:   1. Read the harness's vocabulary before trusting it. "self-heal" here is a genome
               race; the thing that restores HP is a building. A capability the agent has never
               used once in four runs is more likely missing than tuned wrong.
               2. Gate resource trips on a ratio and cap the number of trips — an unbounded
               "go heal" loop is a new wedge.
               3. Retreat is a first-class action. An agent that can enter a dangerous map but not
               leave it will convert every bad roll into a full restart.
               4. Get door coordinates from the game's own warp table (`memory.read_warps()`); the
               previous routes.json had the Center door mislabelled as a city waypoint, which is
               how lanes ended up wedged at the counter (evals/cases/pewter-pokecenter-exit.json).
artifacts:     scripts/agent.py (_pewter_heal_action, PEWTER_HEAL_GATE, PEWTER_GYM_RETREAT_GATE,
                 PEWTER_MAX_HEAL_TRIPS, PEWTER_CENTER_DOOR, POKECENTER_NURSE_TILE)
               data/probe/b/{agent.log,fitness.json} (3/48 -> whiteout, unmodified repo)
               data/probe/c/agent.log ("HEAL |" lines, 32 -> 48/48 in ~25 turns)
               data/probe/a/fitness.json (pre_brock_r8 seed: 8 HP, loses the Jr. Trainer fight)
               data/relay-brock-1/pewter_to_badge/base/agent.log ("RETREAT |" then the badge)
