obstacle:      pewter-corrupted-transition-save
category:      state-save | navigation
symptom:       The forest_to_pewter segment saves its stop.state during a map transition (13→2 at ~18,35). The saved position is outside Pewter City bounds. When pewter_to_badge loads the baton, the game auto-corrects or warps the player to (16,12), (16,13), or (18,34) depending on emulator timing. From these positions the navigator oscillates because waypoint 0 (18,22) is behind the agent and the at_target fix on waypoint 4 (16,13) only fires when current_waypoint==4.
failed:        -
  variant: base genome (door_cooldown=8, stuck_threshold=11)
  failure: Loads at (18,34) after auto-correction. Navigator still sees current_waypoint=0 target=(18,22) so it tries to move “down/right” back toward the south of the city, but the tile at (18,33) is a wall/boundary and the agent gets stuck pressing into it.
  variant: cautious (hp_run_threshold=0.35)
  failure: Same root cause — the corrupted starting position breaks the ordered waypoint assumption.
  variant: with proximity waypoint skip (added in this session)
  failure: Proximity skip sets current_waypoint to 4 when at (16,12), which is adjacent to waypoint 4 (16,13). However once the agent steps onto (16,13) the exact-match check increments current_waypoint to 5. On the next turn back at (16,12) current_waypoint==5 triggers end-of-route logic, but the agent is not standing ON the last waypoint, so next_direction returns None → fallback to “a”.
winner:        None found — the obstacle is unresolved.
why it failed:  Pokemon Red updates wCurMap (0xD35E) before player coordinates during a gatehouse/map transition. A save state taken on the first frame after map_id==2 shows the player still at Route 2 coordinates. Loading that state places the emulator in an inconsistent transition frame. PyBoy.tick(120) before saving was tried but allowed the agent to walk off map 2 before the save happened; removing the tick kept the transition frame intact but still corrupted.
generalizes:   When a segment ends on a map-change boundary, never save on the first frame where the new map_id appears. Require at least 2–3 settled frames (no map change, no battle, text_box_active==False) before calling pyboy.save_state(). A better fix is to snapshot the most-recent clean backtrack frame instead of the live emulator state.
artifacts:     data/relay/260815-204958/batons/forest_to_pewter.state, data/relay/260815-204958/report.json, data/relay/260815-204958/pewter_to_badge/*/agent.log
