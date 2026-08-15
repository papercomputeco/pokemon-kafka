obstacle:      brock-approach-deadend-unresolved
category:      navigation (blocks the battle obstacle: Brock)
symptom:       Even after fixing the waypoint-index-reset bug (see
               pewter-waypoint-index-reset-loop.md), every `pewter_to_badge` lane still fails to
               reach Brock. The plain waypoint Navigator paths the party to (17,11) in Pewter
               City, one tile east of the routes.json "Pewter Gym" waypoint (16,11), then
               presses "left" into (16,11) forever — `stuck_turns` climbs unbounded (observed
               past 7800) with the position frozen at (17,11) the entire time. `report.json`
               for every lane in both attempts (4000/8000 max_turns) shows `final_map_id: 2`,
               `badges: 0`, `encounters: 0`, `lead_hp: 0` (the party had also independently
               whited out from carried-over poison damage ticking during the long walk, and
               separately from this dead-end).
failed:        (1) Treating (16,11) as a normal building door approached sideways — real wall,
               confirmed by thousands of stuck turns with zero position change. (2) Treating
               (16,11) as a door entered by walking UP into it from the tile directly below,
               (16,12) — this DID move the sprite onto (16,11) without a wall block, but no map
               change ever followed (no warp fired), and continuing to press "up" past it just
               walked the party further north with no result, other than once coincidentally
               triggering `MAP CHANGE 2 -> 0` (Pallet Town) — closer inspection showed this
               was a whiteout (the party's HP had already ticked to 0 from a poison status
               picked up in the forest, with no potions/antidote in the bag and no Pokemon
               Center visit ever completed) landing at the same moment, not a real Gym warp: the
               destination coordinates (Pallet Town, near the player's house) don't match a Gym
               interior, and `has_pokedex()`/badge state were unaffected. (3) A hand-built
               "visit the Pokemon Center first, then the Gym, both approached from below" state
               machine — reverted: the "keep pressing up every turn once aligned" version
               oscillated between (16,12) and (16,11) when re-pathing on every turn interrupted
               a single already-in-flight approach, and even after fixing that oscillation, the
               party just kept walking further and further north (observed reaching (16,8) and
               beyond) without ever triggering a warp, meaning the assumed door coordinate
               (16,11) is unreliable and the code was walking through open ground, not into a
               building. (4) A generic "stuck > 60 turns → fall back to the persistent WorldMap
               frontier explorer (`explore_step`)" safety net — added and kept (harmless, and a
               reasonable general improvement), but it did not resolve this specific case: once
               added, `explore_step` reliably suggested "up" from (17,11) every 30 turns, and
               that direction ALSO failed to move the party, confirming (17,11) is a genuine
               narrow dead-end pocket (blocked on at least two sides: left into the presumed
               door, and up) reachable only from the direction the party arrived from — the
               local wall-learning (`world.block()`) never got the chance to record the "up"
               wall as a hard block, because the Navigator's own deterministic "left" presses in
               between kept resetting the two-consecutive-same-tile-failure counter, so
               `explore_step`'s optimistic BFS kept re-suggesting the same already-failed "up"
               direction instead of routing around it.
winner:        unresolved. Reverted all Pewter/Gym-specific coordinate assumptions back to the
               stock waypoint Navigator plus the generic stuck-escape fallback, since guessing
               exact building-approach coordinates without visual/ground-truth map data produced
               a worse regression once (an accidental whiteout misread as a door warp) and no
               net improvement otherwise.
why it worked: N/A — not resolved. The most likely explanation, unconfirmed: either (a) the
               routes.json waypoint `{"x": 16, "y": 11, "note": "Pewter Gym"}` documents the
               wrong tile for the real Gym door (the true entrance may be approached from a
               different column or a different side of the building entirely), or (b) the
               correct approach requires navigating around the building's footprint first
               (the Navigator's direct-line stepping walks straight at the building face instead
               of along the actual street), and the on-screen 9x10 A* (`Navigator._try_astar`)
               can't see far enough past the local screen window to route around it, while the
               whole-map WorldMap planner (`self.world`, used successfully for the Viridian
               Forest maze and for the initial-waypoint fix) was only ever tried with the same
               possibly-wrong coordinate, so it inherited the same failure.
generalizes:   When a lane gets wedged at a fixed position for many thousands of turns with a
               DIFFERENT direction recommended by multiple independent mechanisms (plain
               Navigator, on-screen A*, and the whole-map frontier explorer) that all fail to
               move the sprite, don't keep guessing alternate directions or coordinates by
               hand — that's a sign the target coordinate itself (from routes.json or any
               other static data source) is unverified/wrong for this map, not that the
               approach angle needs tweaking. The next concrete step (not attempted here due to
               time budget) would be to have a lane systematically explore the full Pewter City
               map with pure frontier exploration (`explore_step` alone, no waypoint target at
               all) until it discovers the real Gym warp by trial, then record the *actual*
               discovered coordinate back into routes.json for future runs — turning this into a
               one-time data-correction rather than a per-run pathing puzzle. Also generalizes
               the poison/whiteout finding: a itemless, already-poisoned party surviving Viridian
               Forest is on a clock even after reaching Pewter safely; visiting the Pokemon
               Center to cure status before approaching the Gym is necessary but the codebase
               currently has zero Pokemon-Center-interior interaction logic (no nurse dialogue
               state machine, unlike the existing Oak's-Lab state machine) — that's the concrete
               next feature to build, not another coordinate guess.
artifacts:     data/relay/seg3b/, seg3c/, seg3d/ (pewter_to_badge attempts after the waypoint-
               index fix, all showing the (17,11)-pressing-"left"-forever wedge in
               agent.log/report.json). data/relay/seg3_probe4/, seg3_probe5/, seg3_probe6/
               (manual probes of the below-door-approach and generic-explore-fallback attempts,
               including the DEBUG_EXPLORE-instrumented probe showing explore_step returning
               "up" every 30 turns with zero position change). No baton produced for this
               segment — the chain stops at `data/relay/seg2/batons/forest_to_pewter.state`.
