obstacle:      route3-mtmoon-untested
category:      navigation
symptom:       N/A — never attempted. `badge_to_mtmoon` requires a `batons/pewter_to_badge.state`
               baton (produced only after Brock is beaten), which was never produced because
               `pewter_to_badge` did not complete (see brock-approach-deadend-unresolved.md).
failed:        N/A — not attempted.
winner:        unresolved / not attempted.
why it worked: N/A.
generalizes:   Once `pewter_to_badge` produces a baton, run
               `uv run python scripts/relay.py rom/pokemon_red.gb --segments badge_to_mtmoon
               --seed-state <run_dir>/batons/pewter_to_badge.state --timeout 1200`. The
               NAV_SPREAD variants (same ones that got route1_to_forest across in one attempt)
               are the segment's decision spread — start there; if it wedges the same way the
               Pewter Gym approach did (a fixed position, multiple mechanisms recommending
               directions that don't move the sprite), apply the same diagnosis discipline from
               brock-approach-deadend-unresolved.md before hand-tuning genome knobs: confirm
               whether the target waypoint in routes.json for Route 3 / Mt. Moon's entrance is
               itself correct before assuming the pathing logic is at fault.
artifacts:     None — no run directory exists for this segment.
