obstacle:      route1-navigation-seed-state
category:      navigation
symptom:       Lanes get stuck in infinite flee loops on Route 1 (map 13); stuck streak reaches 138 in 2000-4000 turns; max HP 4/23, backtrack_restores=0
failed:        route1.state seed: agent starts with low HP (4/23), gets stuck in Weedle flee loop; at-oaks-lab.state seed: same failure pattern
winner:        first_battle.state seed: all lanes successfully reached Viridian Forest (map 51) in ~959 turns with base genome
why it worked:  first_battle.state provides a better starting position after the initial scripted intro battles, avoiding the stuck flee loop that plagued route1.state
generalizes:   seed state choice is critical - a bad seed state can make an otherwise sound genome non-viable; when Route 1 navigation fails across all variants, check seed state validity before tweaking genome parameters
artifacts:     data/relay/260815-170915/report.json (segment 1 success with first_battle.state), data/relay/260815-170420/report.json (segment 1 failures with route1.state)
