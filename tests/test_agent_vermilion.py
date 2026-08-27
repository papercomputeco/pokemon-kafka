"""The southbound chain driver and the cutscene observation hook.

Every hop target resolves from the extracted truth at runtime; the coordinates in these tests
mirror the measured Cerulean facts (the Trashed House back door, the officer-guarded front)."""

from unittest.mock import MagicMock

from agent import (
    CERULEAN_CITY_MAP,
    ROUTE_5_MAP,
    ROUTE_6_MAP,
    TRASHED_HOUSE_MAP,
    UNDERGROUND_HOUSE_N_MAP,
    UNDERGROUND_TUNNEL_MAP,
    VERMILION_CHAIN,
    VERMILION_CITY_MAP,
)
from memory_reader import OverworldState
from test_agent import _make_agent


def _ag(tmp_path):
    ag = _make_agent(tmp_path)
    ag._truth_ready = MagicMock(return_value=True)
    ag._truth = {
        "maps": {
            str(CERULEAN_CITY_MAP): {
                "width": 4,
                "height": 3,
                "grid": ["1111", "1111", "1100"],
                "warps": [[3, 1, TRASHED_HOUSE_MAP, 0]],
            },
            str(TRASHED_HOUSE_MAP): {"width": 4, "height": 2, "grid": ["1111", "1111"], "warps": [[3, 0, 255, 7]]},
            str(ROUTE_5_MAP): {
                "width": 4,
                "height": 2,
                "grid": ["1111", "1111"],
                "warps": [[2, 0, UNDERGROUND_HOUSE_N_MAP, 0]],
            },
            str(UNDERGROUND_TUNNEL_MAP): {"width": 2, "height": 4, "grid": ["11"] * 4, "warps": [[0, 3, 74, 0]]},
            str(ROUTE_6_MAP): {"width": 4, "height": 2, "grid": ["1111", "1111"], "warps": []},
        }
    }
    ag._truth_walk = MagicMock(return_value="down")
    return ag


def _st(map_id, x=0, y=0, badges=0x03):
    return OverworldState(map_id=map_id, x=x, y=y, badges=badges)


def test_gates(tmp_path):
    ag = _ag(tmp_path)
    assert ag._vermilion_action(_st(CERULEAN_CITY_MAP, badges=0x01)) is None  # no Cascade Badge
    assert ag._vermilion_action(_st(59)) is None  # not a chain map
    ag._truth_ready = MagicMock(return_value=False)
    assert ag._vermilion_action(_st(CERULEAN_CITY_MAP)) is None


def test_cerulean_tries_the_edge_then_the_trashed_house(tmp_path):
    ag = _ag(tmp_path)
    assert ag._vermilion_action(_st(CERULEAN_CITY_MAP, 1, 1)) == "down"
    assert ag._truth_walk.call_args[0][1] == {(0, 2), (1, 2)}  # open south-row cells only
    # Edge unreachable (main region): the road south is the house's front door.
    ag._truth_walk = MagicMock(side_effect=[None, "up"])
    assert ag._vermilion_action(_st(CERULEAN_CITY_MAP, 1, 1)) == "up"
    assert ag._truth_walk.call_args[0][1] == {(3, 1)}
    # Standing ON the south row: step off — the edge hands over on the step OFF it.
    assert ag._vermilion_action(_st(CERULEAN_CITY_MAP, 0, 2)) == "down"


def test_back_door_walks_to_3_0_and_steps_up(tmp_path):
    ag = _ag(tmp_path)
    assert ag._vermilion_action(_st(TRASHED_HOUSE_MAP, 2, 1)) == "down"
    assert ag._truth_walk.call_args[0][1] == {(3, 0)}
    ag._truth_walk = MagicMock(return_value=None)
    assert ag._vermilion_action(_st(TRASHED_HOUSE_MAP, 3, 0)) == "up"


def test_warp_hops_target_the_extracted_destination(tmp_path):
    ag = _ag(tmp_path)
    assert ag._vermilion_action(_st(ROUTE_5_MAP, 1, 1)) == "down"
    assert ag._truth_walk.call_args[0][1] == {(2, 0)}
    kwargs = ag._truth_walk.call_args
    assert kwargs.kwargs.get("avoid_warps") is True  # never thread an unintended door


def test_mats_out_and_edge_south(tmp_path):
    ag = _ag(tmp_path)
    ag._truth["maps"][str(UNDERGROUND_HOUSE_N_MAP)] = {
        "width": 4,
        "height": 2,
        "grid": ["1111", "1111"],
        "warps": [[1, 1, 255, 3], [2, 1, 255, 3]],
    }
    old = VERMILION_CHAIN[UNDERGROUND_HOUSE_N_MAP]
    try:
        VERMILION_CHAIN[UNDERGROUND_HOUSE_N_MAP] = ("mats-out", ROUTE_6_MAP)
        assert ag._vermilion_action(_st(UNDERGROUND_HOUSE_N_MAP, 0, 0)) == "down"
        assert ag._truth_walk.call_args[0][1] == {(1, 1), (2, 1)}
        ag._truth_walk = MagicMock(return_value=None)
        assert ag._vermilion_action(_st(UNDERGROUND_HOUSE_N_MAP, 1, 1)) == "down"
    finally:
        VERMILION_CHAIN[UNDERGROUND_HOUSE_N_MAP] = old
    ag._truth_walk = MagicMock(return_value="left")
    assert ag._vermilion_action(_st(ROUTE_6_MAP, 1, 0)) == "left"
    ag._truth_walk = MagicMock(return_value=None)
    assert ag._vermilion_action(_st(ROUTE_6_MAP, 0, 1)) == "down"


def test_chain_ends_at_vermilion():
    hops = set(VERMILION_CHAIN)
    dests = {nxt for _, nxt in VERMILION_CHAIN.values()}
    assert VERMILION_CITY_MAP in dests and VERMILION_CITY_MAP not in hops


def test_decision_chain_gives_the_south_the_map(tmp_path):
    ag = _ag(tmp_path)
    ag._vermilion_action = MagicMock(return_value="down")
    ag._pewter_heal_action = MagicMock(return_value=None)
    ag._badge2_action = MagicMock(side_effect=AssertionError("badge2 ran on the southern loop"))
    assert ag.choose_overworld_action(_st(ROUTE_5_MAP, 1, 1)) == "down"


def test_cutscene_freeze_emits_discovery(tmp_path):
    """text_box_active lies under script control (the Route 3 lesson): a frozen position with
    changing screen text is a cutscene, and what it says is the observation."""
    ag = _ag(tmp_path)
    ag._vermilion_action = MagicMock(return_value=None)
    ag._pewter_heal_action = MagicMock(return_value=None)
    ag._badge2_action = MagicMock(return_value=None)
    ag._recruit_action = MagicMock(return_value=None)
    ag._mtmoon_action = MagicMock(return_value=None)
    ag._brock_engage_action = MagicMock(return_value=None)
    st = _st(CERULEAN_CITY_MAP, 2, 2)
    ag.last_overworld_state = st
    ag.memory.read_dialogue = MagicMock(return_value="Cell Separation System!")
    ag.collector.discovery = MagicMock()
    ag.choose_overworld_action(_st(CERULEAN_CITY_MAP, 2, 2))
    args = ag.collector.discovery.call_args
    assert args[0][4] == "Cell Separation System!"
    assert args.kwargs.get("kind") == "cutscene"
    # Dedup: the same line does not spam a second event.
    ag.collector.discovery.reset_mock()
    ag.choose_overworld_action(_st(CERULEAN_CITY_MAP, 2, 2))
    ag.collector.discovery.assert_not_called()


def test_truth_walk_avoid_warps_blocks_unintended_doors(tmp_path):
    """The plan must never thread a door tile as floor (the Center-door 6,000-turn press)."""
    import rom_truth as rt

    ag = _make_agent(tmp_path)
    ag._truth_mod = rt
    ag._truth = {
        "maps": {
            "9": {
                "width": 3,
                "height": 1,
                "grid": ["111"],
                "tiles": ["2c2c2c"],
                "tileset": 1,
                "warps": [[1, 0, 64, 0]],
                "sprites": [],
            }
        }
    }
    ag._truth_pairs = set()
    ag._truth_ready = MagicMock(return_value=True)
    st = _st(9, 0, 0)
    # The only route to (2,0) runs over the door at (1,0): with avoid_warps it is refused...
    assert ag._truth_walk(st, {(2, 0)}, "t", avoid_warps=True) is None
    # ...and allowed when the door IS the target.
    assert ag._truth_walk(st, {(1, 0)}, "t2", avoid_warps=True) == "right"
