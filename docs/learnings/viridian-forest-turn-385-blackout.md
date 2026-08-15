obstacle:      viridian-forest-turn-385-blackout
category:      navigation | battle
symptom:       Lanes enter Viridian Forest (map 51) with ~L7-L9 starter and get stuck for thousands of turns; max_stuck_streak 45-145, stuck_count 500+, final_map_id remains 51 after 6000 turns. Base/cautious/aggressive/status_heavy/cautious_narrow all black out or thrash in place.
failed:        -
  variant: base (hp_run_threshold=0.25)
  failure: Fights too many wild battles; 134 encounters, 599 stuck events, lead_hp drops to 5. The forest maze with frequent encounters drains HP until the agent is too weak to navigate out.
  variant: cautious (hp_run_threshold=0.35)
  failure: Similar pattern — 181 encounters, 587 stuck events, ends at (25,21) in map 51 with 12 HP but still trapped.
  variant: aggressive (hp_run_threshold=0.1)
  failure: Fights even more aggressively; 62 encounters but 513 stuck events. Low flee threshold means it never escapes when surrounded.
  variant: status_heavy (status_move_score=5.0)
  failure: 128 encounters, 672 stuck events. Prioritizing status moves doesn't help in the forest where raw damage + survival is needed.
  variant: cautious_narrow (hp_run_threshold=0.35 + waypoint_skip_distance=1)
  failure: 118 encounters, 621 stuck events. Narrow waypoints don't compensate for the HP drain.
winner:        very_cautious variant with genome diff: hp_run_threshold 0.25→0.5, hp_heal_threshold 0.3→0.5. Turns: 2270, lead_hp: 13, final_map_id: 2 (Pewter City).
why it worked:  Raising the flee threshold to 0.5 means the agent runs from almost every wild encounter while HP is below 50%, preserving health for the navigation thrash. With 13 HP remaining at Pewter, the party is healthy enough to continue. The forest is not a place to grind — it's a place to survive and exit quickly.
generalizes:   In high-encounter maze areas (forests, caves), survival trumps leveling. When stuck_count climbs above 100 and max_stuck_streak exceeds 20, increase hp_run_threshold and hp_heal_threshold to flee earlier and preserve HP for navigation.
artifacts:     data/relay/260815-190939/batons/forest_to_pewter.state, data/relay/260815-190939/report.json, data/relay/260815-190939/forest_to_pewter/*/agent.log
