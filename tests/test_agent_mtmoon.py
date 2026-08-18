"""The badge_to_mtmoon leg: Badge 1 in hand, out the door of the Gym, off the east edge of
Pewter, across Route 3 to the Mt. Moon warps.

Each map's exit is the game's own warp table filtered by the destination map — no baked tiles —
so these tests pin the *hop selection* and its gates (badge, map, empty warp table), which is
the part a wrong guess used to cost thousands of turns (pre-badge runs walked the map-2
waypoints to the Gym door from the wrong side of the leg).
"""

from unittest.mock import MagicMock

from agent import MT_MOON_1F_MAP, PEWTER_CITY_MAP, PEWTER_GYM_MAP, ROUTE_3_MAP
from memory_reader import OverworldState
from test_agent import _make_agent

# Pewter City's whole warp table, from the map's own wWarpEntries (the routes.json "2" comment),
# plus the east-edge exit to Route 3.
PEWTER_WARPS = [
    (16, 17, PEWTER_GYM_MAP),  # Gym
    (13, 25, 58),  # Pokemon Center
    (23, 17, 56),  # Mart
    (14, 7, 52),  # Museum
    (19, 5, 52),  # Museum
    (18, 22, ROUTE_3_MAP),  # east edge -> Route 3
]


def _ag(tmp_path):
    ag = _make_agent(tmp_path)
    ag._pilot_to = MagicMock(return_value="up")  # one step toward the target; None = standing on it
    return ag


# ---- gates -------------------------------------------------------------------------------------


def test_mtmoon_is_inert_before_the_badge(tmp_path):
    """The whole Pewter machinery (heal trip, Brock engage) belongs to the pre-badge leg."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=PEWTER_WARPS)
    st = OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1, badges=0)
    assert ag._mtmoon_action(st) is None


def test_mtmoon_is_inert_off_the_road(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=PEWTER_WARPS)
    assert ag._mtmoon_action(OverworldState(map_id=51, x=1, y=1, badges=1)) is None, "not on the transit road"
    assert ag._mtmoon_action(OverworldState(map_id=MT_MOON_1F_MAP, x=1, y=1, badges=1)) is None, "destination: done"
    assert ag._mtmoon_action(OverworldState(map_id=58, x=1, y=1, badges=1)) is None, "inside a Center"


def test_mtmoon_defers_when_the_warp_table_is_unreadable(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[])
    assert ag._mtmoon_action(OverworldState(map_id=PEWTER_CITY_MAP, x=12, y=20, badges=1)) is None


def test_mtmoon_defers_when_the_map_has_no_door_to_the_next_hop(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(0, 13, PEWTER_CITY_MAP)])  # only the door back, no exit
    st = OverworldState(map_id=PEWTER_CITY_MAP, x=12, y=20, badges=1)
    assert ag._mtmoon_action(st) is None


# ---- hop selection: the exit is the warp whose DESTINATION is the next map ----------------------


def test_gym_exits_through_its_only_door(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(0, 13, PEWTER_CITY_MAP)])  # the Gym's door -> Pewter
    st = OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1, badges=1)
    assert ag._mtmoon_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 0, 13)


def test_city_takes_the_route3_warp_not_the_gym_or_center(tmp_path):
    """The old waypoints aimed the city walk at the Gym door (16,17) — for this leg that is the way back."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=PEWTER_WARPS)
    st = OverworldState(map_id=PEWTER_CITY_MAP, x=12, y=20, badges=1)
    assert ag._mtmoon_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 18, 22)  # the east edge, not (16,17)/(13,25)


def test_city_picks_the_nearest_exit_when_several_leave_to_route3(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(18, 22, ROUTE_3_MAP), (19, 25, ROUTE_3_MAP)])
    st = OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=21, badges=1)
    ag._mtmoon_action(st)
    ag._pilot_to.assert_called_with(st, 18, 22)


def test_route3_takes_the_cave_warp_not_the_exit_back_to_pewter(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(
        return_value=[
            (0, 23, PEWTER_CITY_MAP),  # back to Pewter (where we came from)
            (2, 21, MT_MOON_1F_MAP),  # the cave
            (63, 30, 12),  # far east to Route 1 — the other way around
        ]
    )
    st = OverworldState(map_id=ROUTE_3_MAP, x=10, y=25, badges=1)
    assert ag._mtmoon_action(st) == "up"
    ag._pilot_to.assert_called_with(st, 2, 21)


def test_on_the_warp_tile_it_nudges_without_replanning(tmp_path):
    """Warps fire on the step into the tile; a read on the tile is mid-transition, so don't plan."""
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(18, 22, ROUTE_3_MAP)])
    st = OverworldState(map_id=PEWTER_CITY_MAP, x=18, y=22, badges=1)
    assert ag._mtmoon_action(st) == "down"
    ag._pilot_to.assert_not_called()


def test_pilot_none_fallback_still_yields_an_action(tmp_path):
    ag = _ag(tmp_path)
    ag.memory.read_warps = MagicMock(return_value=[(0, 13, PEWTER_CITY_MAP)])
    ag._pilot_to = MagicMock(return_value=None)
    assert ag._mtmoon_action(OverworldState(map_id=PEWTER_GYM_MAP, x=5, y=1, badges=1)) == "down"
