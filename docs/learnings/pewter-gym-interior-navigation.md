obstacle:      pewter-gym-interior-navigation (map 54, door mats -> Brock's tile)
category:      navigation
symptom:       Once the party is healthy enough to survive the Gym, the lane still never reaches
               Brock. Three distinct wedges, all inside a 10x14 room: (a) the agent two-cycles
               (4,2)<->(4,6) for 1400 turns without ever fighting anything; (b) with naive
               centre-column waypoints it ping-pongs through the Gym door (map 2 <-> 54) for 2000
               turns and logs **zero** battles; (c) with correct waypoints it stands ON Brock's
               face tile and presses A into empty air. r7's fitness reported 840 stuck events at
               (4,5) — the same tile — so this is the wall those runs actually died on.
failed:        -
  variant: default behaviour, no routes.json entry for map 54 (data/probe/c)
  failure: `parcel_quest` still owns the agent (the parcel is undelivered) and map 54 was in
           `GO_NORTH_PILOT_MAPS`, so every overworld decision returns `pilot("north")`, which is
           `WorldMap.cross_step` sweeping for a NORTH MAP EDGE. The Gym has no north edge — row
           y=0 is solid wall — so the sweep walks the boundary forever. 1400 of 1500 turns spent
           two-cycling, `stuck_count: 140`, 0 battles.
  variant: straight climb up the centre column, waypoints (4,10)->(4,6)->(4,2)->(5,1) (probe D)
  failure: (4,5) is occupied by the Gym's Jr. Trainer, who faces AWAY (north). Walking into a
           trainer's back does not start the battle and does not move the player, so the step
           "fails", the WorldMap learns a hard block, A* re-routes back out the door, comes back
           in, and repeats: 2000 turns, 0 battles, 47 map changes between 2 and 54. The only two
           routes past y=5 are x=4 (blocked by his body) and x=8.
  variant: correct waypoints, no engagement fix (probe E)
  failure: Reaches (5,1) in ~15 turns and then loses it. A* arrives along the y=1 row from the
           west, i.e. facing LEFT into the wall at (4,1), so `a` opens nothing; and with the quest
           inactive the `BacktrackManager` fires 89 restores that walk the lane back down the room
           it just climbed. 2500 turns, badges 0.
winner:        A six-waypoint east detour in `references/routes.json` "54", plus two one-line
               behavioural changes:
               - remove `PEWTER_GYM` from `parcel_quest.GO_NORTH_PILOT_MAPS` so the quest returns
                 `None` on map 54 and the waypoints get a vote at all;
               - `_quest_nav_active = True` while on map 54 without the badge, which is what gates
                 `BacktrackManager` restores off;
               - `_brock_engage_action`: on Brock's row (y<=2, 3<=x<=7) alternate a facing press
                 (up/left/right/down) with `a` until the battle starts.
               Route: (4,10) -> (4,8) -> (8,8) -> (8,4) -> (5,4) -> (5,2) -> (5,1).
               Measured: door mats to battle start in **~15 turns**, 6/6 relay lanes.
why it worked: The room's geometry was already in the lane's own memory and nobody had looked at
               it. Reading `data/probe/{c,d}/world.map` back shows rock rows at y=3,5,7,9 with
               gaps only at x=4-5 (y=3, y=9) and x=1,3-4,8 (y=5, y=7) — so x=8 is a second,
               unblocked ladder past the Jr. Trainer, and the whole obstacle is one column of
               detour. Adding a routes.json entry does double duty: it supplies the waypoints AND
               it suppresses `_building_exit`, which had been treating the Gym as a building to
               escape from. The facing fix matters because "stand on the tile and press A" is only
               correct if you arrived from the right side; cycling the four directions costs at
               most 8 turns and is orientation-independent.
generalizes:   1. When a lane wedges in a room, dump its own `world.map` before writing any
               waypoints — the agent has usually already mapped the room it is failing to cross.
               2. `pilot("north")` / `cross_step` is only meaningful on maps that HAVE a north
               edge. Interiors are exit-by-warp; a quest phase that pilots a compass direction must
               be scoped to overworld maps or it silently preempts every other navigator.
               3. A blocking NPC is indistinguishable from a wall unless it is facing you. Prefer
               a detour over a trainer sprite; do not assume bumping one starts a fight.
               4. A waypoint list that ends ON the target tile still needs an interaction policy —
               position is not orientation.
artifacts:     references/routes.json ("54" — waypoints and the geometry comment)
               scripts/parcel_quest.py (GO_NORTH_PILOT_MAPS)
               scripts/agent.py (_brock_engage_action, _quest_nav_active on map 54)
               data/probe/c/{agent.log,world.map} (the north-pilot sweep)
               data/probe/d/agent.log (2000 turns, 0 battles, centre-column wedge)
               data/probe/e/agent.log (on-tile, wrong facing, 89 backtrack restores)
               data/relay-brock-1/pewter_to_badge/base/agent.log (the 15-turn winning path)
