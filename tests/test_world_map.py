"""Tests for the accumulated WorldMap occupancy grid + A* planner."""

from world_map import WorldMap


def _full(val=1):
    return [[val] * 10 for _ in range(9)]


# --- observe / walkable -------------------------------------------------------


def test_observe_stamps_window_at_player_coords():
    wm = WorldMap()
    grid = _full(1)
    grid[3][3] = 0  # wall NW of the player (one up, one left)
    wm.observe(5, px=10, py=10, grid=grid)
    # player at centre (row4,col4) -> (10,10); NW cell (row3,col3) -> (9,9)
    assert wm.walkable(5, 10, 10) == 1
    assert wm.walkable(5, 9, 9) == 0


def test_unknown_defaults_to_walkable():
    wm = WorldMap()
    assert wm.walkable(0, 1, 1) == 1  # never observed -> optimistic
    assert wm.walkable(0, 1, 1, default=0) == 0


def test_observe_keeps_per_map_separate():
    wm = WorldMap()
    wm.observe(0, 5, 5, _full(1))
    wm.observe(1, 5, 5, _full(0))
    assert wm.walkable(0, 5, 5) == 1
    assert wm.walkable(1, 5, 5) == 0


def test_observe_ignores_out_of_range_coords():
    wm = WorldMap()
    wm.observe(0, px=0, py=0, grid=_full(1))  # left/up of (0,0) would be negative
    assert wm.walkable(0, 0, 0) == 1
    assert all(x >= 0 and y >= 0 for (x, y) in wm.cells[0])  # no negative keys stored


# --- plan_step ----------------------------------------------------------------


def test_plan_step_none_at_target():
    wm = WorldMap()
    assert wm.plan_step(0, 5, 5, 5, 5) is None


def test_plan_step_straight_toward_target_on_empty_map():
    wm = WorldMap()  # everything unknown -> optimistic straight line
    assert wm.plan_step(0, 5, 5, 5, 0) == "up"
    assert wm.plan_step(0, 5, 5, 9, 5) == "right"
    assert wm.plan_step(0, 5, 5, 5, 9) == "down"
    assert wm.plan_step(0, 5, 5, 1, 5) == "left"


def test_plan_step_detours_around_a_known_wall():
    wm = WorldMap()
    m = wm.cells.setdefault(0, {})
    m[(5, 4)] = 0  # wall directly north of the player at (5,5)
    d = wm.plan_step(0, 5, 5, 5, 0)  # target is north, but straight up is blocked
    assert d in ("left", "right")  # must step around, never into the wall
    assert d != "up"


def test_plan_step_follows_a_long_fence_to_its_gap():
    wm = WorldMap()
    m = wm.cells.setdefault(0, {})
    # A horizontal fence at y=4 spanning x=0..9, with a single gap at x=8.
    for x in range(0, 10):
        m[(x, 4)] = 0
    m[(8, 4)] = 1
    # Player directly under the fence at (2,5): up is a wall, x<0 is off-map (dead end to the
    # left), so the only route north is rightward to the x=8 gap.
    d = wm.plan_step(0, 2, 5, 2, 0)
    assert d == "right"


def test_plan_step_boxed_in_takes_the_only_opening():
    wm = WorldMap()
    m = wm.cells.setdefault(0, {})
    m[(5, 4)] = 0  # up
    m[(4, 5)] = 0  # left
    m[(6, 5)] = 0  # right
    d = wm.plan_step(0, 5, 5, 5, 0)  # only "down" is open even though the goal is north
    assert d == "down"


def test_block_makes_a_tile_impassable_and_reroutes():
    wm = WorldMap()
    wm.block(0, 5, 4)  # the tile straight north of the player at (5,5)
    d = wm.plan_step(0, 5, 5, 5, 0)
    assert d in ("left", "right")  # routes around the blocked tile
    assert d != "up"


def test_observe_does_not_unblock_a_failed_tile():
    wm = WorldMap()
    wm.block(0, 5, 4)
    grid = _full(1)  # collision grid claims everything (incl. 5,4) is walkable
    wm.observe(0, 5, 5, grid)
    assert wm.walkable(0, 5, 4) == 0  # the hard block survives the optimistic observation
    assert wm.plan_step(0, 5, 5, 5, 0) != "up"


def test_cross_step_advances_toward_edge_when_open():
    wm = WorldMap()
    assert wm.cross_step(0, 5, 5, "north") == "up"
    assert wm.cross_step(0, 5, 5, "south") == "down"


def test_cross_step_presses_off_the_known_edge_row():
    wm = WorldMap()
    m = wm.cells.setdefault(0, {})
    for x in range(0, 8):  # a fully mapped strip along the top: everything above is off-map
        m[(x, 0)] = 1
        m[(x, 1)] = 1
    assert wm.cross_step(0, 4, 0, "north") == "up"  # pressing off the edge row IS the crossing


def test_cross_step_sweeps_to_an_open_column_at_a_wall():
    wm = WorldMap()
    wm.observe(0, 5, 5, _full(1))  # the observed window around the player, as every turn stamps
    wm.block(0, 5, 4)  # north of the player's column is a (learned) wall
    wm.block(0, 4, 4)  # and the column to the left
    # the sweep must route around the blocks toward the window's unknown frontier; the right
    # column is a step closer than looping around the left block, so head right
    assert wm.cross_step(0, 5, 5, "north") == "right"


def test_accumulated_observations_inform_planning():
    wm = WorldMap()
    # Observe a window that reveals a wall directly north of the player.
    grid = _full(1)
    grid[3][4] = 0  # north of centre
    wm.observe(0, 5, 5, grid)
    d = wm.plan_step(0, 5, 5, 5, 0)
    assert d != "up"  # planner respects the remembered wall


def test_plan_step_fully_walled_falls_back_to_default():
    wm = WorldMap()
    for d in ((5, 4), (4, 5), (6, 5), (5, 6)):  # block all four neighbours
        wm.block(0, *d)
    assert wm.plan_step(0, 5, 5, 5, 0) == "up"  # greedy fallback finds nothing -> default


def test_dir_same_point_is_none():
    assert WorldMap._dir(5, 5, (5, 5)) is None


def test_cross_step_fully_boxed_nudges_forward():
    wm = WorldMap()
    for d in ((5, 4), (4, 5), (6, 5), (5, 6)):  # boxed in: no cell can advance toward the edge
        wm.block(0, *d)
    assert wm.cross_step(0, 5, 5, "north") == "up"  # nothing better known -> nudge forward


def test_greedy_picks_the_neighbour_closest_to_target():
    wm = WorldMap()
    assert wm._greedy(0, {}, 5, 5, 5, 0) == "up"  # open map: step toward the target (north)


# --- encounter-aware cost (grass avoidance) -----------------------------------


def test_mark_encounter_records_tile_per_map():
    wm = WorldMap()
    wm.mark_encounter(0, 3, 3)
    assert wm.is_encounter_tile(0, 3, 3)
    assert not wm.is_encounter_tile(1, 3, 3)  # per-map, like walkability
    assert not wm.is_encounter_tile(0, 9, 9)  # unmarked tile


def test_zero_encounter_cost_ignores_grass():
    wm = WorldMap()
    wm.mark_encounter(0, 5, 4)  # grass directly north of the player at (5,5)
    # default cost 0 -> behaves exactly like before: shortest path straight up.
    assert wm.plan_step(0, 5, 5, 5, 3) == "up"
    assert wm.plan_step(0, 5, 5, 5, 3, encounter_cost=0) == "up"


def test_encounter_cost_detours_around_known_grass():
    wm = WorldMap()
    wm.mark_encounter(0, 5, 4)  # grass on the straight path north to (5,3)
    # a 2-step straight path costs 2 + penalty; a 4-step detour costs 4. With a big
    # penalty the planner prefers the longer encounter-free route.
    d = wm.plan_step(0, 5, 5, 5, 3, encounter_cost=8)
    assert d != "up"
    assert d in ("left", "right")


def test_encounter_tile_is_penalised_not_impassable():
    wm = WorldMap()
    for d in ((4, 5), (6, 5), (5, 6)):  # box in left, right, down
        wm.block(0, *d)
    wm.mark_encounter(0, 5, 4)  # the only open neighbour is grass
    # grass costs more than open ground but is still passable (unlike a wall), so when it is
    # the only way out the planner still steps onto it rather than freezing.
    assert wm.plan_step(0, 5, 5, 5, 0, encounter_cost=8) == "up"


def test_prefers_fewer_grass_tiles_among_equal_length_paths():
    wm = WorldMap()
    # Two 2-step paths from (5,5) to (6,4): via (5,4) or via (6,5). Make the (5,4)
    # route cross grass; the planner should take the other equal-length route.
    wm.mark_encounter(0, 5, 4)
    d = wm.plan_step(0, 5, 5, 6, 4, encounter_cost=8)
    assert d == "right"  # step to (6,5), avoiding the grass at (5,4)


# --- persistence (carry observations across runs) -----------------------------


def test_worldmap_roundtrips_through_dict():
    wm = WorldMap()
    grid = _full(1)
    grid[3][3] = 0  # a wall NW of the player
    wm.observe(5, 10, 10, grid)
    wm.block(5, 3, 4)
    wm.mark_encounter(7, 2, 2)

    restored = WorldMap.from_dict(wm.to_dict())

    assert restored.walkable(5, 10, 10) == 1
    assert restored.walkable(5, 9, 9) == 0  # observed wall survives
    assert restored.walkable(5, 3, 4) == 0  # hard block survives
    assert restored.is_encounter_tile(7, 2, 2)
    # A planner that learned a wall plans identically after a round-trip.
    assert restored.plan_step(5, 10, 10, 10, 5) == wm.plan_step(5, 10, 10, 10, 5)


def test_worldmap_save_load_file(tmp_path):
    wm = WorldMap()
    wm.observe(2, 8, 8, _full(1))
    wm.block(2, 8, 7)
    wm.mark_encounter(2, 9, 9)
    path = tmp_path / "world.json"
    wm.save(path)

    loaded = WorldMap.load(path)
    assert loaded.walkable(2, 8, 7) == 0
    assert loaded.is_encounter_tile(2, 9, 9)
    assert loaded.walkable(2, 8, 8) == 1


def test_worldmap_load_missing_file_is_empty():
    wm = WorldMap.load("/no/such/world-map-file.json")
    assert wm.cells == {} and wm.blocked == {} and wm.encounters == {}


# --- known_reachable / explore_step (forest exit-wedge fix) -------------------


def test_known_reachable_true_when_already_at_target():
    # Standing on the target is trivially reachable, even on a wholly unknown map.
    wm = WorldMap()
    assert wm.known_reachable(1, 5, 5, 5, 5) is True


def test_known_reachable_strict_about_unknown():
    wm = WorldMap()
    # A known-walkable corridor (0,0)->(2,0); (3,0) is unknown (never observed).
    for x in range(3):
        wm.cells.setdefault(1, {})[(x, 0)] = 1
    assert wm.known_reachable(1, 0, 0, 2, 0) is True
    # (4,0) is only reachable through the unknown (3,0): NOT known-reachable.
    assert wm.known_reachable(1, 0, 0, 4, 0) is False


def test_known_reachable_blocked_by_wall():
    wm = WorldMap()
    m = wm.cells.setdefault(1, {})
    m[(0, 0)] = 1
    m[(1, 0)] = 0  # wall
    m[(2, 0)] = 1
    assert wm.known_reachable(1, 0, 0, 2, 0) is False


def test_explore_step_heads_to_nearest_unknown():
    wm = WorldMap()
    m = wm.cells.setdefault(1, {})
    # An enclosed known corridor (0,0)->(3,0): walls above and below, so the only unknown frontier
    # is off the right end at (4,0) -> the agent must walk "right" to reach unexplored ground.
    for x in range(0, 4):
        m[(x, 0)] = 1
        m[(x, -1)] = 0
        m[(x, 1)] = 0
    m[(-1, 0)] = 0
    assert wm.explore_step(1, 0, 0) == "right"


def test_explore_step_none_when_fully_mapped():
    wm = WorldMap()
    m = wm.cells.setdefault(1, {})
    # A fully-enclosed 1x1 known cell: walls on all sides, nothing unknown reachable.
    m[(5, 5)] = 1
    for nb in [(4, 5), (6, 5), (5, 4), (5, 6)]:
        m[nb] = 0
    assert wm.explore_step(1, 5, 5) is None


# --- warp/exit goal tiles read as walls by the collision grid ------------------
# A warp tile (a forest/door exit) is reported impassable by game_area_collision, so `observe`
# stamps it walkable=0. The planner must still be able to route a path that *ends* on its goal —
# you step onto a warp to use it — while never treating a hard-blocked (tried-and-failed) tile as
# steppable. Without this, the Viridian Forest exit (2,0) is unreachable and the agent never crosses.


def test_known_reachable_to_a_warp_goal_stamped_wall():
    wm = WorldMap()
    m = wm.cells.setdefault(51, {})
    for x in range(2, 6):
        m[(x, 1)] = 1  # known-walkable corridor along y=1
    m[(2, 0)] = 0  # the exit warp — collision grid calls it a wall
    # From the corridor, the warp goal is reachable: walk to (2,1), then step up onto the warp.
    assert wm.known_reachable(51, 5, 1, 2, 0) is True


def test_known_reachable_false_when_goal_is_hard_blocked():
    wm = WorldMap()
    m = wm.cells.setdefault(51, {})
    m[(2, 1)] = 1
    m[(2, 0)] = 0
    wm.block(51, 2, 0)  # tried to enter and failed twice — a real wall, not a warp
    assert wm.known_reachable(51, 2, 1, 2, 0) is False


def test_plan_step_steps_onto_an_adjacent_warp_goal_stamped_wall():
    wm = WorldMap()
    m = wm.cells.setdefault(51, {})
    m[(2, 1)] = 1  # standing here
    m[(2, 0)] = 0  # warp directly north, stamped wall
    # Greedy skips the "wall" goal and drifts away; only routing-onto-goal yields the step up.
    assert wm.plan_step(51, 2, 1, 2, 0) == "up"


def test_plan_step_does_not_step_onto_a_hard_blocked_goal():
    wm = WorldMap()
    m = wm.cells.setdefault(51, {})
    m[(2, 1)] = 1
    m[(2, 0)] = 0
    wm.block(51, 2, 0)  # a real wall — must not be entered even as a goal
    assert wm.plan_step(51, 2, 1, 2, 0) != "up"


# --- require_reach: the planner must admit an unreachable goal ------------------
# Regression for run 20260810-185357-7f79 (navigation-thrash): the exit (2,0) was sealed —
# every neighbour stamped a wall — so A* could never reach it. The memoryless fallback then
# flipped with the start tile: from (6,2) "best" was (6,1) -> "up"; from (6,1) best==start,
# so greedy broke the tie -> "down". Replanning from scratch each turn locked a two-cell
# limit cycle for 7600+ turns. ``require_reach=True`` makes plan_step return None instead
# of the flip-prone fallback, so the caller can fall through to frontier exploration.


def _sealed_pocket() -> WorldMap:
    """Miniature of the wedge: a closed stamped room around (6,1)..(7,3) and a goal (2,0)
    whose every neighbour is a stamped wall."""
    wm = WorldMap()
    m = wm.cells.setdefault(51, {})
    for x in range(5, 9):  # room perimeter x in [5,8], y in [0,4]
        for y in range(0, 5):
            m[(x, y)] = 0
    for x, y in [(6, 1), (6, 2), (6, 3), (7, 1), (7, 2), (7, 3)]:
        m[(x, y)] = 1
    m[(2, 0)] = 1  # the goal itself reads walkable...
    for nb in [(1, 0), (3, 0), (2, 1)]:  # ...but every approach tile is stamped a wall
        m[nb] = 0
    return wm


def test_fallback_flip_reproduces_the_two_cell_limit_cycle():
    # Documents the fallback behaviour the wedge exposed: without require_reach the
    # planner keeps emitting the start-dependent flip pair.
    wm = _sealed_pocket()
    assert wm.plan_step(51, 6, 2, 2, 0) == "up"
    assert wm.plan_step(51, 6, 1, 2, 0) == "down"


def test_require_reach_returns_none_when_goal_is_sealed():
    wm = _sealed_pocket()
    assert wm.plan_step(51, 6, 2, 2, 0, require_reach=True) is None
    assert wm.plan_step(51, 6, 1, 2, 0, require_reach=True) is None


def test_require_reach_still_plans_when_goal_is_reachable():
    wm = WorldMap()  # empty map: goal optimistically reachable straight up
    assert wm.plan_step(0, 5, 5, 5, 0, require_reach=True) == "up"


# --- hard-block expiry ----------------------------------------------------------
# Upstream cause of the sealed-exit wedge (run 20260810-185357-7f79): a failed move into a
# *wandering NPC* hard-blocks its tile forever — blocks (1,17)/(2,18) severed the left exit
# corridor long after the bug catchers had moved on. Wall stamps self-correct because
# ``observe`` overwrites them, but ``blocked`` was permanent. Now each walkable
# re-observation of a blocked tile (the NPC is gone, the grid reads it open again) counts
# toward expiry; at ``block_expiry_observations`` the block is dropped and the tile becomes
# re-testable. A real ledge also expires, but its re-test just fails twice and re-arms the
# block — a couple of wasted presses every N sightings, in exchange for never sealing a map.


def _observe_tile(wm, map_id, x, y, walkable):
    """Stamp one observation window centred on (x, y) whose centre tile reads ``walkable``."""
    grid = [[1] * 10 for _ in range(9)]
    grid[4][4] = 1 if walkable else 0
    wm.observe(map_id, x, y, grid)


def test_hard_block_expires_after_walkable_reobservations():
    wm = WorldMap()
    wm.block_expiry_observations = 3
    wm.block(51, 2, 18)
    assert wm.walkable(51, 2, 18) == 0
    for _ in range(2):
        _observe_tile(wm, 51, 2, 18, walkable=True)
        assert wm.walkable(51, 2, 18) == 0  # not yet expired
    _observe_tile(wm, 51, 2, 18, walkable=True)
    assert wm.walkable(51, 2, 18) == 1  # NPC long gone: block dropped, tile re-testable


def test_hard_block_does_not_expire_while_observed_impassable():
    wm = WorldMap()
    wm.block_expiry_observations = 2
    wm.block(51, 2, 18)
    for _ in range(10):
        _observe_tile(wm, 51, 2, 18, walkable=False)  # NPC still standing there
    assert wm.walkable(51, 2, 18) == 0


def test_reblock_after_expiry_rearms_a_fresh_counter():
    wm = WorldMap()
    wm.block_expiry_observations = 2
    wm.block(51, 5, 5)
    for _ in range(2):
        _observe_tile(wm, 51, 5, 5, walkable=True)
    assert wm.walkable(51, 5, 5) == 1  # expired
    wm.block(51, 5, 5)  # re-test failed twice: it really is a ledge
    _observe_tile(wm, 51, 5, 5, walkable=True)
    assert wm.walkable(51, 5, 5) == 0  # fresh counter: one observation isn't enough


def test_block_expiry_progress_roundtrips_through_dict():
    wm = WorldMap()
    wm.block_expiry_observations = 3
    wm.block(51, 2, 18)
    _observe_tile(wm, 51, 2, 18, walkable=True)  # partial progress: 1 of 3
    wm2 = WorldMap.from_dict(wm.to_dict())
    wm2.block_expiry_observations = 3
    assert wm2.walkable(51, 2, 18) == 0
    for _ in range(2):
        _observe_tile(wm2, 51, 2, 18, walkable=True)
    assert wm2.walkable(51, 2, 18) == 1  # resumed at 1, expired at 3 — progress persisted


def test_block_loads_from_legacy_pair_format():
    # Worldmap files written before expiry stored blocked as bare [x, y] pairs.
    wm = WorldMap.from_dict({"blocked": {"51": [[2, 18]]}})
    assert wm.walkable(51, 2, 18) == 0


# --- map 37 cross_step wedge (issue #64) -----------------------------------------
# Red's house 1F (map 37) is the blackout respawn (51 -> 0 -> 37) and has NO north exit — the
# way out is the door warp at the bottom row. Piloting north there, the agent wedged at the
# top-left: (2,1) is an enterable dead-end pocket ((2,0), (1,1) and (3,1) all stamped walls),
# and phantom "walkable" tiles stamped beyond the real 8-tile-wide map (x >= 8) kept feeding
# the boundary sweep a fake exit column. cross_step's local fast path ("(2,1) is enterable ->
# up") and its global BFS ("dead end -> go around") disagreed, so the agent two-cycled
# (2,2) <-> (2,1) without progress — 41k+ turns of (2,2)+up / (2,1)+down in the 2026-08-15
# event stream, plus 17k+ parked (2,1)+up presses into the known wall (run 20260810-231918-5212
# and data/game/2026-08-15.jsonl). The geometry below is the agent's own persisted worldmap.


def _reds_house_worldmap() -> WorldMap:
    """Map 37 exactly as the wedged agent had learned it (persisted worldmap snapshot)."""
    rows = {
        0: "########???",
        1: "##.#....##.",
        2: "...........",
        3: "...........",
        4: "...##......",
        5: "...##......",
        6: "...........",
        7: "...........",
        8: "########..#",
        9: "########..#",
        10: "########???",
        11: "########???",
    }
    wm = WorldMap()
    m = wm.cells.setdefault(37, {})
    for y, row in rows.items():
        for x, ch in enumerate(row):
            if ch != "?":
                m[(x, y)] = 1 if ch == "." else 0
    return wm


def _real_house_walkable(wm):
    """Ground-truth oracle: the real house is 8x8; stamps inside it are accurate, everything
    beyond (the phantom x>=8 / y>=8 tiles) is off-map and every move into it fails."""
    cells = dict(wm.cells[37])
    return lambda t: 0 <= t[0] <= 7 and 0 <= t[1] <= 7 and cells.get(t) == 1


def _simulate_pilot_north(wm, map_id, start, real_walkable, turns):
    """Drive cross_step the way run_overworld does: apply each step against the *real* map and
    hard-block a tile after two consecutive failed presses into it (agent.py's two-fail rule)."""
    deltas = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
    pos, last_fail, visited = start, None, [start]
    for _ in range(turns):
        dx, dy = deltas[wm.cross_step(map_id, pos[0], pos[1], "north")]
        nxt = (pos[0] + dx, pos[1] + dy)
        if real_walkable(nxt):
            pos, last_fail = nxt, None
        else:
            if nxt == last_fail:
                wm.block(map_id, *nxt)
            last_fail = nxt
        visited.append(pos)
    return visited


def test_map37_pocket_two_cycle_breaks_out():
    # The wedge itself: from (2,2) the old code bounced (2,2)+up / (2,1)+down forever. The
    # fixed sweep may press the (2,0) warp hypothesis once (two presses, then hard-blocked),
    # but must then leave the pocket and sweep the top boundary column by column.
    wm = _reds_house_worldmap()
    visited = _simulate_pilot_north(wm, 37, (2, 2), _real_house_walkable(wm), turns=60)
    assert any(x >= 4 for x, _y in visited)  # escaped the pocket and swept east
    # Boundary columns get tested and permanently retired, not mashed forever.
    assert (4, 0) in wm.blocked[37] and (5, 0) in wm.blocked[37]


def test_map37_tried_wall_is_not_pressed_again():
    # The parked regime (2026-08-14: (2,1)+up streaks of 1341): (2,0) has already been pressed
    # and failed. Neither wedge tile may keep pointing back into a tried-and-failed tile.
    wm = _reds_house_worldmap()
    wm.block(37, 2, 0)
    assert wm.cross_step(37, 2, 1, "north") != "up"
    assert wm.cross_step(37, 2, 2, "north") != "up"


def test_cross_step_presses_an_untried_boundary_wall_once():
    # A stamped wall on the boundary row may really be a warp (the forest exit reads as a
    # wall), so the sweep presses it once — and a hard-block (tried twice, failed) retires
    # the candidate for good instead of letting the agent mash it.
    wm = _reds_house_worldmap()
    assert wm.cross_step(37, 2, 1, "north") == "up"  # test the warp hypothesis at (2,0)
    wm.block(37, 2, 0)  # ...it failed twice: a real wall
    assert wm.cross_step(37, 2, 1, "north") != "up"


def test_cross_step_still_presses_into_a_boundary_warp():
    # Forest-exit shape: the whole top row reads as trees/wall, but the tile overhead is the
    # (untried) exit warp. The sweep must step into it rather than drifting off to a frontier.
    wm = WorldMap()
    m = wm.cells.setdefault(51, {})
    for x in range(0, 8):
        m[(x, 0)] = 0
        m[(x, 1)] = 1
    assert wm.cross_step(51, 2, 1, "north") == "up"


# --- Route 1 south-entry flap (uncovered by the map 37 fix) -----------------------
# With Red's house passable, fresh runs reached Route 1 (map 12) — and ping-ponged between
# its south edge and Pallet Town 1,019 times in a 3,000-turn run. With the whole map known,
# the only real exit north is the x=10/11 passage at row 0; but a BFS that traverses unknown
# tiles optimistically wraps around the *known* west border wall through the unstamped void,
# finds a "gains ground" candidate in fantasy space a dozen steps away (vs ~40 through the
# real corridor), and the path's first step is `down` — off the south edge. The geometry
# below is the flapping agent's own persisted worldmap.


def _route1_worldmap() -> WorldMap:
    rows = {
        0: "#.....#..#.....#.",
        1: "#######..#######.",
        2: "#..............#.",
        3: "#..............#.",
        4: "#.....#........#.",
        5: "###########....#.",
        6: "#.....#........#.",
        7: "#.....#........#.",
        8: "#.....#........#.",
        9: "#######........#.",
        10: "#..............#.",
        11: "#..............#.",
        12: "#..............#.",
        13: "###########....#.",
        14: "#..............#.",
        15: "#..............#.",
        16: "#..............#.",
        17: "#..............#.",
        18: "#..............#.",
        19: "##.###.#########.",
        20: "#..............#.",
        21: "#..............#.",
        22: "#..............#.",
        23: "#########....###?",
        24: "#..............#?",
        25: "#..............#?",
        26: "#..............#?",
        27: "###...##########?",
        28: "#..............#?",
        29: "#..............#?",
        30: "#..............#?",
        31: "#..............#?",
        32: "#######..#######?",
        33: "#.....#..#.....#?",
        34: "#.....#..#.....#?",
        35: "#.....#..#.....#?",
        36: "???...#..#....???",
        37: "???####..#####???",
        38: "???...........???",
        39: "???##....####.???",
    }
    wm = WorldMap()
    m = wm.cells.setdefault(12, {})
    for y, row in rows.items():
        for i, ch in enumerate(row):
            if ch != "?":
                m[(3 + i, y)] = 1 if ch == "." else 0
    return wm


def test_cross_step_takes_a_sideways_probe_when_nothing_gains_ground():
    # Whole known boundary tried and retired, and the only remaining probe (an unknown
    # forward tile) sits level with the player: no candidate gains ground, so the sweep
    # falls back to the nearest probe anywhere rather than giving up.
    wm = WorldMap()
    m = wm.cells.setdefault(0, {})
    for x in range(0, 5):
        m[(x, 0)] = 0
        wm.block(0, x, 0)  # every boundary wall pressed twice and failed — retired
        m[(x, 1)] = 1
    for x in range(0, 6):
        m[(x, 2)] = 1  # row 2 reaches one column further east; (5,1) is unknown
    d = wm.cross_step(0, 2, 1, "north")
    assert d in ("down", "right")  # route toward the (5,2) probe under the unknown (5,1)


def test_cross_step_does_not_chase_candidates_through_the_unknown_ocean():
    # Entering from Pallet at the south corridor, the sweep must head north through known
    # ground, never south off the edge toward a phantom route around the border wall.
    wm = _route1_worldmap()
    assert wm.cross_step(12, 10, 35, "north") == "up"
    assert wm.cross_step(12, 11, 35, "north") == "up"


# --- map bounds: the collision window reads garbage beyond the real map edge ------
# Route 2 (map 13, 20x72 tiles) exposed the flap's twin: standing on the south boundary row
# (8,71), the observation window stamped phantom walkable rows 72-75 below the real map, so
# with every genuine candidate exhausted the explore fallback chased the phantom southern
# "frontier" — and the physical press exited the map (731 Viridian<->Route 2 crossings in a
# 3,000-turn run). The game knows the loaded map's true size (wCurMapWidth/Height); once the
# WorldMap records it, off-map garbage can neither be stamped nor treated as frontier.


def _route2_worldmap() -> WorldMap:
    """Map 13 as the flapping agent had learned it — phantom rows 72-75 included."""
    rows = {
        40: "..####....####",
        41: "..####....####",
        42: "..####....####",
        43: "###.##########",
        44: "...........#..",
        45: "...........#..",
        46: "...........#..",
        47: "########...#..",
        48: "...........#..",
        49: "...........###",
        50: "...........#..",
        51: "...........#..",
        52: "............#.",
        53: "......########",
        54: ".....########.",
        55: ".....########.",
        56: "......#######.",
        57: "............#?",
        58: "............#.",
        59: "............#.",
        60: "##..........#.",
        61: "#######.######",
        62: "##..........#.",
        63: "##..........#.",
        64: "##..........#.",
        65: "##...#......#.",
        66: "##..........#.",
        67: "##..........#.",
        68: "##..........#.",
        69: "##........####",
        70: "#######...####",
        71: "#######...####",
        72: "#######...####",
        73: "#######..#####",
        74: "???####...####",
        75: "???####...####",
    }
    wm = WorldMap()
    m = wm.cells.setdefault(13, {})
    for y, row in rows.items():
        for x, ch in enumerate(row):
            if ch != "?":
                m[(x, y)] = 1 if ch == "." else 0
    return wm


def test_bounds_stop_the_sweep_walking_off_the_trailing_edge():
    # With the real 20x72 bounds known, the phantom rows below y=71 are off-map: neither the
    # sweep nor the explore fallback may answer "down" from the south boundary row.
    wm = _route2_worldmap()
    wm.bounds[13] = (20, 72)
    assert wm.cross_step(13, 8, 71, "north") != "down"
    assert wm.explore_step(13, 8, 71) != "down"


def test_observe_records_bounds_and_clips_garbage_stamps():
    wm = WorldMap()
    # Player at the south-east corner of a tiny 8x8 map: the window rows/cols beyond the
    # edge carry garbage "walkable" reads that must not be stamped.
    wm.observe(37, 7, 7, _full(1), bounds=(8, 8))
    assert wm.bounds[37] == (8, 8)
    assert all(x < 8 and y < 8 for (x, y) in wm.cells[37])


def test_pressing_off_the_real_edge_is_still_the_crossing():
    wm = WorldMap()
    m = wm.cells.setdefault(0, {})
    for x in range(0, 8):
        m[(x, 2)] = 1
        m[(x, 3)] = 1
    wm.bounds[0] = (8, 4)  # the map really ends at y=3
    assert wm.cross_step(0, 2, 3, "south") == "down"  # off the last row IS the crossing


def test_bounds_roundtrip_through_dict():
    wm = WorldMap()
    wm.observe(13, 5, 5, _full(1), bounds=(20, 72))
    wm2 = WorldMap.from_dict(wm.to_dict())
    assert wm2.bounds == {13: (20, 72)}
