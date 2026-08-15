obstacle:      viridian-forest-turn-385-blackout
category:      navigation | battle
symptom:       Blackout wall preventing passage near the exit of Viridian Forest.
failed:        Initial base genome configurations failed to clear the blackout wall, regardless of the variant. The issue seems to stem from suboptimal resource management (HP/Potions) relative to the complexity of the obstacle.
winner:        base (with improved base genome: hp_run_threshold: 0.15, hp_heal_threshold: 0.3)
why it worked: The default base genome was too aggressive/optimistic regarding party health. By slightly lowering the default HP run and heal thresholds, the baseline decision logic forces the agent to heal/manage resources earlier and more cautiously, allowing it to weather the blackout sequence successfully.
generalizes:   For mandatory choke point battles, always ensure the baseline model prioritizes health management (healing/rest) over maximizing immediate progress, especially when failure requires complex resource cycling.
artifacts:     data/relay/260815-230505/report.json
