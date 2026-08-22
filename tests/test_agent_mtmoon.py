"""The badge_to_mtmoon leg: Badge 1 in hand, out the Gym, out the city to the road, then the
mountain warps wherever the road is.

Ground truths from the 2026-08-18 probes (pokedex/log7.md, log17.md): the gym door mats warp to
LAST_MAP (0xFF), and the city's live warp table is the buildings (52/54/56/58) plus two open-map
warps (29,13)->55 and (7,29)->57 — the road, under an id this leg must not assume. So hop
selection is "the non-building exit on 2", "the warp to 59 on the road", and nothing is baked in
— which is also exactly what a wrong guess cost before (400 turns swallowed on map 54).
"""

from unittest.mock import MagicMock

from agent import MT_MOON_1F_MAP, PEWTER_CITY_MAP, PEWTER_GYM_MAP
from memory_reader import OverworldState
from test_agent import _make_agent

# The city's real warp table from the MTMOON-MISS probe (log17.md) plus the two open-map exits.
CITY_WARPS = [
    (14, 7, 52),  # Museum
    (19, 5, 52),  # Museum
    (16, 17, 54),  # Gym
    (29, 13, 55),  # open map (east side)
    (23, 17, 56),  # Mart
    (7, 29, 57),  # open map (west side)
    (13, 25, 58),  # Center
]
GDOOR = [(4, 13, 0xFF), (5, 13, 0xFF)]  # the gym's door mats -> LAST_MAP


def _ag(tmp_path):
    ag = _make_agent(tmp_path)
    ag._pilot_to = MagicMock(return_value="up")  # one step toward the target; None = standing on it
    return ag


# ---- gates -------------------------------------------------------------------------------------


def test_mtmoon_is_inert_before_the_badge(tmp_path):
    """The whole Pewter machinery (heal trip, Brock engage) belongs to the pre-badge leg."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=GDOOR)
    assert ag._mtmoon_action(OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1, badges=0)) is None


def test_mtmoon_is_inert_on_the_destination(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(0, 23, PEWTER_CITY_MAP), (3, 21, 2)])
    assert ag._mtmoon_action(OverworldState(map_id=MT_MOON_1F_MAP, x=1, y=1, badges=1)) is None


def test_city_with_unreadable_warp_table_starts_the_edge_hunt(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(40, 36))
    ag._pilot_to = MagicMock(return_value="right")
    assert ag._mtmoon_action(OverworldState(map_id=PEWTER_CITY_MAP, x=12, y=20, badges=1)) == "right"


def test_city_with_no_open_exit_starts_the_edge_hunt(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(0, 13, PEWTER_CITY_MAP)])  # only warps back to itself
    ag.memory.read_map_bounds = MagicMock(return_value=(40, 36))
    ag._pilot_to = MagicMock(return_value="right")
    assert ag._mtmoon_action(OverworldState(map_id=PEWTER_CITY_MAP, x=12, y=20, badges=1)) == "right"


def test_city_edge_hunt_wraps_and_exhausts(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(40, 36))
    ag._pilot_to = MagicMock(return_value="up")
    st = OverworldState(map_id=PEWTER_CITY_MAP, x=39, y=20, badges=1)  # at the east edge
    assert ag._mtmoon_action(st) == "right"  # probe ten (log24): the east edge IS Route 3
    for _ in range(12):  # the off-edge press wedges; after the stall threshold the phase advances
        ag.last_overworld_state = st
        ag._mtmoon_action(st)
    ph = ag._mtmoon_edge[PEWTER_CITY_MAP]
    assert ph["i"] == 1  # advanced to the south edge
    ph["tried"] = 99  # every edge of the map failed
    # The city is a spring: an exhausted hunter re-arms and re-tries the east road door
    # (probes ten/twelve/seventeen), keeping the 2 <-> 14 loop alive until the crossing lands.
    assert ag._mtmoon_action(st) == "right"


def test_noncity_map_with_no_warp_at_all_edge_hunts(tmp_path):
    """Route 3 in this image has an EMPTY warp table (t14 probe) — for it the edge IS the only exit.
    Phase 3 is the east edge (29,8) with these mock bounds, so standing on it presses off."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(30, 16))
    ag._pilot_to = MagicMock(return_value="left")
    ag._mtmoon_edge = {14: {"i": 3, "stuck": 0, "tried": 0, "best": None}}
    st = OverworldState(map_id=14, x=29, y=8, badges=1)  # Route 3, at the east edge
    assert ag._mtmoon_action(st) == "right"  # step off into whatever the engine links there


def test_defers_when_bounds_unreadable_and_warps_are_dead(tmp_path):
    """Mid-transition (no bounds) with no warp-table exit: don't guess — let normal nav own the turn."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(3, 3, PEWTER_CITY_MAP), (5, 5, 55), (8, 8, 58)])
    ag.memory.read_map_bounds = MagicMock(return_value=None)
    assert ag._mtmoon_action(OverworldState(map_id=55, x=1, y=1, badges=1)) is None


def test_center_is_deferred_to_the_heal_flow(tmp_path):
    """On the Center this branch never fights the counter for the door: heal, then walk out"""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(3, 3, 2)])
    assert ag._mtmoon_action(OverworldState(map_id=58, x=3, y=1, badges=1)) is None


def test_city_heals_once_before_hunting(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=CITY_WARPS)
    st = OverworldState(map_id=PEWTER_CITY_MAP, x=12, y=20, badges=1)
    assert ag._mtmoon_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 13, 25)  # the Center door, heal first
    ag._pilot_to.reset_mock()  # second city visit: the heal is a one-shot, back to the exit list
    st2 = OverworldState(map_id=PEWTER_CITY_MAP, x=12, y=20, badges=1)
    assert ag._mtmoon_action(st2) == "up"
    ag._pilot_to.assert_called_with(st2, 7, 29)


def test_route3_march_scans_blocked_rows(tmp_path):
    """The Route 3 east march walks the corridor row and, when an east press fails, scans the
    wall column row by row (up first) instead of bumping blindly -- a column wall with any
    gap gets crossed (probes nineteen/twenty-one, log49/51.md)."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(70, 18))

    def mk(x, y):
        return OverworldState(map_id=14, x=x, y=y, badges=1)

    assert ag._route_march(mk(3, 8), 70, 18) == "right"  # open field: press east
    assert ag._route_march(mk(13, 8), 70, 18) == "down"  # near the first wall: approach its row
    assert ag._route_march(mk(13, 12), 70, 18) == "right"  # on the row: press east
    # a solid wall ahead: free press, then the row scan steps up and re-probes east
    assert ag._route_march(mk(5, 12), 70, 18) == "right"
    assert ag._route_march(mk(5, 12), 70, 18) == "up"  # east blocked at this row
    assert ag._route_march(mk(5, 11), 70, 18) == "right"  # re-probe at the next row
    assert ag._route_march(mk(5, 11), 70, 18) == "up"  # still blocked: keep scanning


def test_route3_march_sweeps_an_edge_then_works_the_next(tmp_path):
    """On an edge: press off, bump along the edge; a full sweep with no warp advances to the
    next stage, and after all three edges the march hands over."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(70, 18))
    st = OverworldState(map_id=14, x=69, y=8, badges=1)  # east edge (bw-1 = 69)
    assert ag._route_march(st, 70, 18) == "right"  # enter edge mode, probe the row
    m = ag._mtmoon_march
    m["x"], m["y"] = 68, 8  # a free turn again (lane shifted)
    m["t"] = 18 * 2 + 6  # a full sweep of the east edge...
    assert ag._route_march(st, 70, 18) == "down"  # ...on to the south edge
    st2 = OverworldState(map_id=14, x=30, y=0, badges=1)  # north edge (stage two)
    m["stage"] = 2
    m["x"], m["y"] = 30, 1
    m["t"] = 70 * 2 + 6
    assert ag._route_march(st2, 70, 18) is None  # all three edges swept: hand over


def test_mtmoon_on_route3_prefers_the_march(tmp_path):
    """With the table empty, the march runs before the (station-based) edge hunter."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(70, 18))
    ag._pilot_to = MagicMock(return_value="up")
    st = OverworldState(map_id=14, x=5, y=8, badges=1)
    assert ag._mtmoon_action(st) == "right"  # the march, not the pilot


# ---- hop selection: the exit is read from the live table, never assumed ------------------------


def test_gym_exits_through_the_door_mats_warping_to_last_map(tmp_path):
    """The real gym door mats warp to LAST_MAP (0xFF, "back where we came from"), NOT to map 2 —
    a strict dest==2 filter matched nothing and probe one (log7.md) wedged for 400 turns."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=GDOOR)
    st = OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1, badges=1)
    assert ag._mtmoon_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 5, 13)  # nearest mat


def test_city_takes_the_westernmost_open_exit_not_a_building(tmp_path):
    """Westbound: the east-side exit (29,13)->55 is a dead-end room that warps straight back to
    its mat (probe four, log18.md bounced 2<->55 for 600 turns); the western (7,29)->57 is the road.
    Every building (52/54/56/58) is the wrong way."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=CITY_WARPS)
    ag._mtmoon_healed = True  # the center hop is a one-shot; past it, the exit list applies
    st = OverworldState(map_id=PEWTER_CITY_MAP, x=12, y=20, badges=1)
    assert ag._mtmoon_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 7, 29)  # westernmost open exit


def test_city_prefers_the_western_exit_when_they_straddle(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(29, 13, 55), (7, 29, 57)])
    st = OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=14, badges=1)  # near the EAST exit
    ag._mtmoon_action(st)
    ag._pilot_to.assert_called_with(st, 7, 29)  # westernmost still wins


def test_road_takes_the_moon_warp_not_the_exit_back_to_pewter(tmp_path):
    """Whatever id the road has, the only thing that matters is a warp to the cave (59)."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(
        return_value=[
            (0, 23, PEWTER_CITY_MAP),  # back to the city (where we came from)
            (2, 21, MT_MOON_1F_MAP),  # the cave
            (63, 30, 12),  # the long way to Route 1
        ]
    )
    st = OverworldState(map_id=55, x=10, y=25, badges=1)  # the id is whatever the game says it is
    assert ag._mtmoon_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 2, 21)


def test_first_turn_after_landing_settles_before_reading_warps(tmp_path):
    """Probe five (log19.md): reading warps on the first turn after a map change returned the
    previous map's table (the city's) while standing on 57 — the bounce loop followed."""
    ag = _ag(tmp_path)
    ag.last_overworld_state = OverworldState(map_id=PEWTER_CITY_MAP, x=7, y=29)
    ag.memory.read_warps = MagicMock(return_value=[(3, 21, MT_MOON_1F_MAP)])
    assert ag._mtmoon_action(OverworldState(map_id=57, x=7, y=29, badges=1)) is None
    ag._pilot_to.assert_not_called()


def test_offroad_defers_when_every_warp_is_backwards_or_inward(tmp_path):
    """An off-road map whose warps only lead back (city) or to itself has no forward hop — hand
    control back to normal nav instead of bouncing."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(3, 3, PEWTER_CITY_MAP), (5, 5, 55), (8, 8, 58)])
    assert ag._mtmoon_action(OverworldState(map_id=55, x=1, y=1, badges=1)) is None


def test_road_follows_a_forward_open_warp_when_no_cave_warp_is_listed(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(3, 3, PEWTER_CITY_MAP), (5, 5, 12)])
    st = OverworldState(map_id=55, x=4, y=4, badges=1)
    assert ag._mtmoon_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 5, 5)


def test_on_the_warp_tile_it_nudges_without_replanning(tmp_path):
    """Warps fire on the step into the tile; a read on the tile is mid-transition, so don't plan."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=GDOOR)
    st = OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=13, badges=1)
    assert ag._mtmoon_action(st) == "down"
    ag._pilot_to.assert_not_called()


def test_pilot_none_fallback_still_yields_an_action(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=GDOOR)
    ag._pilot_to = MagicMock(return_value=None)
    assert ag._mtmoon_action(OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1, badges=1)) == "down"


# ---- the caller, the bounce reset, and the paths the 08-18 run never took ----------------------


def test_choose_overworld_action_routes_through_the_mtmoon_leg(tmp_path):
    """With the badge in hand the leg owns the turn before the pre-badge Pewter machinery."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=GDOOR)
    st = OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1, badges=1)
    assert ag.choose_overworld_action(st) == "up"


def test_route3_bounce_rearms_the_city_door_without_a_prior_hunt(tmp_path):
    """A lane can reach 14 without ever edge-hunting (a forward warp chain, a --seed-worldmap
    baton): the re-arm must bootstrap the hunter dict, not index it into an AttributeError."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(70, 18))
    ag.last_overworld_state = OverworldState(map_id=14, x=3, y=8, badges=1)
    st = OverworldState(map_id=14, x=4, y=8, badges=1)
    assert ag._mtmoon_action(st) == "right"  # the march proceeds; no crash
    assert ag._mtmoon_edge[PEWTER_CITY_MAP] == {"i": 0, "stuck": 0, "tried": 0, "best": None}
    assert ag._mtmoon_all_edges is None


def test_route3_bounce_resets_an_exhausted_city_hunter(tmp_path):
    """The city is a spring (log47.md): a bounce back from 14 re-arms its east road door."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(70, 18))
    ag._mtmoon_edge = {PEWTER_CITY_MAP: {"i": 2, "stuck": 5, "tried": 4, "best": 3}}
    ag.last_overworld_state = OverworldState(map_id=14, x=3, y=8, badges=1)
    ag._mtmoon_action(OverworldState(map_id=14, x=4, y=8, badges=1))
    assert ag._mtmoon_edge[PEWTER_CITY_MAP]["tried"] == 0


def test_city_heal_hop_steps_in_from_the_door_mat(tmp_path):
    """Standing exactly on the Center's mat: step in without replanning; the heal flow takes over."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=CITY_WARPS)
    st = OverworldState(map_id=PEWTER_CITY_MAP, x=13, y=25, badges=1)
    assert ag._mtmoon_action(st) == "down"
    ag._pilot_to.assert_not_called()


def test_dead_end_interior_walks_back_out_and_is_marked_tried(tmp_path):
    """A house/lobby whose only warps go LAST_MAP: back to its door, and the city hop skips it."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(5, 7, 0xFF)])
    st = OverworldState(map_id=55, x=2, y=2, badges=1)
    assert ag._mtmoon_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 5, 7)
    assert 55 in ag._mtmoon_tried_exits


def test_offmap_edge_hunt_bootstraps_its_own_phase_state(tmp_path):
    """First edge hunt on a map that never went through the city path creates the dict itself."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(20, 20))
    ag._pilot_to = MagicMock(return_value="right")
    st = OverworldState(map_id=55, x=5, y=5, badges=1)
    assert ag._mtmoon_action(st) == "right"
    assert 55 in ag._mtmoon_edge


def test_edge_hunt_reports_exhaustion_once_and_defers(tmp_path):
    """Every edge tried: hand the map back to normal nav, logging the miss once per map."""
    ag = _ag(tmp_path)
    ag.memory.read_map_bounds = MagicMock(return_value=(20, 20))
    ag._mtmoon_edge = {55: {"i": 0, "stuck": 0, "tried": 4, "best": None}}
    st = OverworldState(map_id=55, x=5, y=5, badges=1)
    assert ag._mtmoon_edge_hunt(st) is None
    assert ag._mtmoon_all_edges == 55
    assert ag._mtmoon_edge_hunt(st) is None  # second call: same verdict, no re-log


def test_edge_hunt_wedge_on_the_last_phase_exhausts(tmp_path):
    """A wedge on the final (west) phase rolls the tried count past the edge list: hand over."""
    ag = _ag(tmp_path)
    ag.memory.read_map_bounds = MagicMock(return_value=(20, 20))
    ag._mtmoon_edge = {55: {"i": 3, "stuck": 11, "tried": 3, "best": 0}}
    st = OverworldState(map_id=55, x=5, y=5, badges=1)
    assert ag._mtmoon_edge_hunt(st) is None
    assert ag._mtmoon_edge[55]["tried"] == 4


# ---- the Route 3 march: the south/north stages and the scan edge cases -------------------------


def _mk14(x, y):
    return OverworldState(map_id=14, x=x, y=y, badges=1)


def test_route3_march_defaults_to_the_south_stage(tmp_path):
    """No explicit start stage: probes 20/22/23 sealed the east side solid, so south goes first."""
    ag = _ag(tmp_path)
    assert ag._route_march(_mk14(5, 5), 70, 18) == "down"
    assert ag._mtmoon_march["stage"] == 1


def test_route3_march_presses_off_the_south_edge_within_the_sweep(tmp_path):
    ag = _ag(tmp_path)
    assert ag._route_march(_mk14(5, 17), 70, 18) == "down"
    assert ag._mtmoon_march["t"] == 1


def test_route3_march_bumps_along_a_blocked_south_edge(tmp_path):
    """Stuck on the same tile in an edge stage: a short bump run sideways, re-pressing as it goes."""
    ag = _ag(tmp_path)
    st = _mk14(5, 17)
    ag._route_march(st, 70, 18)  # arrive: press off the edge
    assert ag._route_march(st, 70, 18) == "right"  # blocked: bump run starts (seg rotation)
    assert ag._route_march(st, 70, 18) == "right"  # the run continues from the same tile
    assert ag._mtmoon_march["run"] == 6


def test_route3_march_bump_runs_flip_at_the_map_bounds(tmp_path):
    """Each bump direction that would leave the map flips to the stage's other escape."""
    # move "up" at the north bound (stage 1: bump_a=left, so up flips to left)
    ag = _ag(tmp_path)
    st = _mk14(5, 0)
    ag._route_march(st, 70, 18)
    ag._mtmoon_march["seg"] = 1  # next rotation lands on back="up"
    assert ag._route_march(st, 70, 18) == "left"
    # move "left" at the west bound (flips to bump_b="right")
    ag2 = _ag(tmp_path)
    st2 = _mk14(1, 5)
    ag2._route_march(st2, 70, 18)
    ag2._mtmoon_march["seg"] = 2  # next rotation lands on bump_a="left"
    assert ag2._route_march(st2, 70, 18) == "right"
    # move "right" at the east bound (flips to back="up")
    ag3 = _ag(tmp_path)
    st3 = _mk14(68, 5)
    ag3._route_march(st3, 70, 18)
    ag3._mtmoon_march["seg"] = 0  # next rotation lands on bump_b="right"
    assert ag3._route_march(st3, 70, 18) == "up"
    # move "down" at the south bound (stage 2: segs right/left/down; down flips to bump_a="right")
    ag4 = _ag(tmp_path)
    ag4._mtmoon_start_stage = 2
    st4 = _mk14(5, 17)
    ag4._route_march(st4, 70, 18)
    ag4._mtmoon_march["seg"] = 1  # next rotation lands on back="down"
    assert ag4._route_march(st4, 70, 18) == "right"


def test_route3_scan_detects_the_wall_crossing(tmp_path):
    """A row scan that actually gets past the wall logs the crossing row and resumes east."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag._route_march(_mk14(5, 12), 70, 18)  # free press east
    ag._route_march(_mk14(5, 12), 70, 18)  # blocked: scan starts, step up
    ag._route_march(_mk14(5, 11), 70, 18)  # new row: re-probe east
    assert ag._route_march(_mk14(6, 11), 70, 18) == "right"  # it moved: wall crossed at y=11
    assert ag._mtmoon_march["scan"] in (0, 1)  # scan survives; the march is eastbound again


def test_route3_scan_tops_out_then_bottoms_out(tmp_path):
    """Up sweep exhausted at y=0 flips to the down sweep; down sweep exhausted ends the scan and
    charges the whole edge as swept (t past the sweep budget)."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    st_top = _mk14(5, 0)
    ag._route_march(st_top, 70, 18)  # free press east
    ag._route_march(st_top, 70, 18)  # blocked at the top row: scan starts
    assert ag._route_march(st_top, 70, 18) == "down"  # up sweep can't go up: flip to down sweep
    assert ag._mtmoon_march["scan"] == 2
    st_bot = _mk14(5, 17)
    ag._route_march(st_bot, 70, 18)  # moved rows: re-probe east
    assert ag._route_march(st_bot, 70, 18) == "right"  # bottom row blocked too: scan closes
    assert ag._mtmoon_march["scan"] == 0
    assert ag._mtmoon_march["t"] == 18 * 2 + 6 + 1  # the edge is charged as fully swept


def test_route3_march_realigns_the_approach_rows(tmp_path):
    """The x=14/15 wall opens around row 12 (log50.md); past x=20 hug the mid-band."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag._route_march(_mk14(14, 14), 70, 18)  # free press east
    assert ag._route_march(_mk14(15, 14), 70, 18) == "up"  # 13<=x<20, below row 12: climb to it
    assert ag._route_march(_mk14(25, 16), 70, 18) == "up"  # x>=20, hugging the south bound: lift
    assert ag._route_march(_mk14(25, 2), 70, 18) == "down"  # x>=20, hugging the north bound: drop


def test_route3_march_east_stage_presses_off_its_edge_within_the_sweep(tmp_path):
    """Stage zero at the east bound with sweep budget left: keep pressing east for the adjacency."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag._route_march(_mk14(69, 8), 70, 18)  # arrive at the east bound
    assert ag._route_march(_mk14(69, 9), 70, 18) == "right"  # moved a row: press off again
    assert ag._mtmoon_march["t"] == 1


# ---- ROM-truth navigation ----------------------------------------------------------------


def _truth_agent(tmp_path):
    """An agent wired to a 4x4 synthetic truth: map 14 open, north edge at x=1 leads to map 15."""
    import rom_truth

    ag = _make_agent(tmp_path)
    grid = ["0100", "1111", "1111", "1111"]
    truth = {
        "tile_pairs": [],
        "maps": {
            "14": {
                "width": 4,
                "height": 4,
                "tileset": 0,
                "grid": grid,
                "tiles": None,
                "warps": [],
                "sprites": [],
                "grass": [],
                "connections": {"north": 15},
            },
            "15": {
                "width": 4,
                "height": 4,
                "tileset": 0,
                "grid": ["1111"] * 4,
                "tiles": None,
                "warps": [[0, 0, MT_MOON_1F_MAP, 0]],
                "sprites": [],
                "grass": [],
                "connections": {"south": 14},
            },
            str(MT_MOON_1F_MAP): {
                "width": 4,
                "height": 4,
                "tileset": 0,
                "grid": ["1111"] * 4,
                "tiles": None,
                "warps": [],
                "sprites": [],
                "grass": [],
                "connections": {},
            },
        },
    }
    ag._truth, ag._truth_pairs, ag._truth_mod = truth, set(), rom_truth
    return ag


def _ow(map_id, x, y, **kw):
    return OverworldState(map_id=map_id, x=x, y=y, badges=1, party_count=1, **kw)


def test_truth_step_walks_toward_the_edge_that_leaves_the_map(tmp_path):
    ag = _truth_agent(tmp_path)
    # (1,3) -> the only open north-edge cell is (1,0), so the step is straight up.
    assert ag._truth_step(_ow(14, 1, 3), MT_MOON_1F_MAP) == "up"
    assert ag._truth_step(_ow(MT_MOON_1F_MAP, 0, 0), MT_MOON_1F_MAP) is None  # already there


def test_truth_step_walks_off_the_edge_once_standing_on_it(tmp_path):
    """An edge hop fires no warp: the engine hands the player over only when they walk off that
    side. Arriving at the exit tile and planning again yields a one-cell path — the crossing that
    ended on Route 3's (57,0) then stalled there for the rest of the run."""
    ag = _truth_agent(tmp_path)
    assert ag._truth_step(_ow(14, 1, 0), MT_MOON_1F_MAP) == "up"


def test_truth_step_presses_a_to_clear_a_challenge_before_blaming_the_map(tmp_path):
    """A stalled step is a wall or a trainer mid-challenge, and ``text_box_active`` reads False for
    the latter. Pressing A on the odd misses clears the dialogue; only a step that still fails is
    a wall. Scoring the freeze as a refusal sealed Route 3's crossing at (11,6)."""
    ag = _truth_agent(tmp_path)
    st = _ow(14, 1, 3)
    assert ag._truth_step(st, MT_MOON_1F_MAP) == "up"
    ag.turn_count += 1
    assert ag._truth_step(st, MT_MOON_1F_MAP) == "a"  # did not move: dismiss, do not block
    assert ag.world.blocked.get(14, {}) == {}


def test_truth_step_blocks_a_tile_the_engine_keeps_refusing(tmp_path):
    ag = _truth_agent(tmp_path)
    st = _ow(14, 1, 3)
    for _ in range(ag._TRUTH_REFUSE_STRIKES + 2):
        ag._truth_step(st, MT_MOON_1F_MAP)
        ag.turn_count += 1
    assert (1, 2) in ag.world.blocked.get(14, {})  # the step it never completed


def test_truth_step_forgets_misses_once_the_lane_moves(tmp_path):
    ag = _truth_agent(tmp_path)
    assert ag._truth_step(_ow(14, 1, 3), MT_MOON_1F_MAP) == "up"
    ag.turn_count += 1
    assert ag._truth_step(_ow(14, 1, 2), MT_MOON_1F_MAP) == "up"  # moved: progress, not a refusal
    assert ag._truth_misses == {}


def test_truth_refuse_strikes_is_evolvable(tmp_path, monkeypatch):
    """The knob the ROM-truth legs actually turn. Route 3 reads no other navigation parameter, so
    without this a NAV spread over stuck_threshold/waypoint_skip_distance returns six identical
    lanes — six lanes' compute for one lane's information."""
    import json as _json

    from test_agent import _make_agent

    monkeypatch.setenv("EVOLVE_PARAMS", _json.dumps({"truth_refuse_strikes": 3}))
    assert _make_agent(tmp_path)._truth_refuse_strikes == 3
    monkeypatch.delenv("EVOLVE_PARAMS")
    ag = _make_agent(tmp_path)
    assert ag._truth_refuse_strikes == ag._TRUTH_REFUSE_STRIKES


def test_an_impatient_lane_calls_a_wall_sooner_than_a_patient_one(tmp_path):
    """Same refused step, different genome, different turn at which the map is blamed."""
    calls = {}
    for label, strikes in (("impatient", 4), ("patient", 12)):
        ag = _truth_agent(tmp_path)
        ag._truth_refuse_strikes = strikes
        st = _ow(14, 1, 3)
        for turn in range(40):
            ag._truth_step(st, MT_MOON_1F_MAP)
            ag.turn_count += 1
            if (1, 2) in ag.world.blocked.get(14, {}):
                calls[label] = turn
                break
    assert calls["impatient"] < calls["patient"]


def test_truth_step_degrades_once_when_the_truth_file_is_unavailable(tmp_path, monkeypatch):
    """A missing or sha-mismatched truth file must cost one log line, not a working leg: the first
    call falls back to the march, and the failure is remembered so the load is never retried."""
    import rom_truth
    from test_agent import _make_agent

    loader = MagicMock(side_effect=ValueError("extracted from a different ROM"))
    monkeypatch.setattr(rom_truth, "load_truth", loader)
    ag = _make_agent(tmp_path)
    assert ag._truth_step(_ow(14, 1, 3), MT_MOON_1F_MAP) is None
    assert ag._truth_step(_ow(14, 1, 3), MT_MOON_1F_MAP) is None
    assert loader.call_count == 1


def test_truth_step_declines_a_map_the_truth_does_not_know(tmp_path):
    """No hop chain, no opinion — the caller keeps its previous fallback."""
    ag = _truth_agent(tmp_path)
    assert ag._truth_step(_ow(99, 0, 0), MT_MOON_1F_MAP) is None


def test_truth_step_emits_left_and_down(tmp_path):
    """The step translator's other two arms: right/up are exercised by the crossing tests above."""
    ag = _truth_agent(tmp_path)
    # (2,1) -> the only open north-edge cell (1,0): (2,0) is walled, so the first step is left.
    assert ag._truth_step(_ow(14, 2, 1), MT_MOON_1F_MAP) == "left"
    ag2 = _truth_agent(tmp_path)
    ag2._truth["maps"]["14"]["connections"] = {"south": 15}  # exit flips to the open south edge
    assert ag2._truth_step(_ow(14, 1, 1), MT_MOON_1F_MAP) == "down"
