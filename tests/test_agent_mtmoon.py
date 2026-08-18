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

    assert ag._route_march(mk(3, 8), 70, 18) == "right"   # open field: press east
    assert ag._route_march(mk(13, 8), 70, 18) == "down"   # near the first wall: approach its row
    assert ag._route_march(mk(13, 12), 70, 18) == "right"  # on the row: press east
    # a solid wall ahead: free press, then the row scan steps up and re-probes east
    assert ag._route_march(mk(5, 12), 70, 18) == "right"
    assert ag._route_march(mk(5, 12), 70, 18) == "up"     # east blocked at this row
    assert ag._route_march(mk(5, 11), 70, 18) == "right"  # re-probe at the next row
    assert ag._route_march(mk(5, 11), 70, 18) == "up"     # still blocked: keep scanning

def test_route3_march_sweeps_an_edge_then_works_the_next(tmp_path):
    """On an edge: press off, bump along the edge; a full sweep with no warp advances to the
    next stage, and after all three edges the march hands over."""
    ag = _ag(tmp_path)
    ag._mtmoon_start_stage = 0
    ag.memory.read_warps = MagicMock(return_value=[])
    ag.memory.read_map_bounds = MagicMock(return_value=(70, 18))
    st = OverworldState(map_id=14, x=69, y=8, badges=1)  # east edge (bw-1 = 69)
    assert ag._route_march(st, 70, 18) == "right"         # enter edge mode, probe the row
    m = ag._mtmoon_march
    m["x"], m["y"] = 68, 8                                # a free turn again (lane shifted)
    m["t"] = 18 * 2 + 6                                   # a full sweep of the east edge...
    assert ag._route_march(st, 70, 18) == "down"          # ...on to the south edge
    st2 = OverworldState(map_id=14, x=30, y=0, badges=1)  # north edge (stage two)
    m["stage"] = 2
    m["x"], m["y"] = 30, 1
    m["t"] = 70 * 2 + 6
    assert ag._route_march(st2, 70, 18) is None           # all three edges swept: hand over


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
