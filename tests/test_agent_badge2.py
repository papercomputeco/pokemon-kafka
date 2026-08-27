"""The badge-2 drivers: gym approach, the Nugget Bridge grind, and the learn-flow recovery.

Every coordinate here was measured live (screenshots + RAM probes, 2026-08-26): Misty is talked
to from (5,2), her east side; (4,3) is usually parked on by the defeated swimmer's body; below
BADGE2_GRIND_LEVEL the driver ping-pongs the bridge gauntlet instead of challenging."""

from unittest.mock import MagicMock

from agent import (
    BADGE2_GRIND_LEVEL,
    CERULEAN_CITY_MAP,
    CERULEAN_GYM_MAP,
    ROUTE_24_MAP,
    ROUTE_25_MAP,
)
from memory_reader import OverworldState
from test_agent import _make_agent


def _ag(tmp_path, level=BADGE2_GRIND_LEVEL):
    ag = _make_agent(tmp_path)
    ag._truth_ready = MagicMock(return_value=True)
    ag._truth = {
        "maps": {
            str(CERULEAN_CITY_MAP): {"width": 4, "height": 2, "grid": ["1010", "1111"]},
            str(ROUTE_24_MAP): {"width": 3, "height": 2, "grid": ["111", "101"]},
            str(ROUTE_25_MAP): {"width": 3, "height": 2, "grid": ["111", "110"]},
        }
    }
    ag._truth_walk = MagicMock(return_value="up")
    # PARTY_BASE + 33 is the lead's level; everything else reads 0.
    ag.memory._read = MagicMock(side_effect=lambda a: level if a == ag.memory.PARTY_BASE + 33 else 0)
    return ag


def _st(map_id, x=0, y=0, badges=0x01):
    return OverworldState(map_id=map_id, x=x, y=y, badges=badges)


# ---- gates -------------------------------------------------------------------------------------


def test_badge2_inert_without_badge1_or_with_badge2(tmp_path):
    ag = _ag(tmp_path)
    assert ag._badge2_action(_st(CERULEAN_CITY_MAP, badges=0)) is None
    assert ag._badge2_action(_st(CERULEAN_CITY_MAP, badges=0x03)) is None
    assert ag._badge2_action(_st(15)) is None  # not gym ground
    ag._truth_ready = MagicMock(return_value=False)
    assert ag._badge2_action(_st(CERULEAN_CITY_MAP)) is None


# ---- the gym drive -----------------------------------------------------------------------------


def test_city_walks_to_the_gym_door(tmp_path):
    ag = _ag(tmp_path)
    assert ag._badge2_action(_st(CERULEAN_CITY_MAP, 19, 18)) == "up"
    args = ag._truth_walk.call_args[0]
    assert args[1] == {(30, 19)}


def test_misty_is_talked_to_from_her_east_side(tmp_path):
    ag = _ag(tmp_path)
    ag.turn_count = 0
    assert ag._badge2_action(_st(CERULEAN_GYM_MAP, 5, 2)) == "left"  # face her
    ag.turn_count = 1
    assert ag._badge2_action(_st(CERULEAN_GYM_MAP, 5, 2)) == "a"  # talk
    assert ag._badge2_action(_st(CERULEAN_GYM_MAP, 5, 3)) == "up"  # step to the talk tile
    ag.turn_count = 0
    assert ag._badge2_action(_st(CERULEAN_GYM_MAP, 4, 3)) == "up"  # the swimmer-body fallback
    ag.turn_count = 1
    assert ag._badge2_action(_st(CERULEAN_GYM_MAP, 4, 3)) == "a"


def test_gym_default_walks_toward_the_corridor(tmp_path):
    ag = _ag(tmp_path)
    ag._truth_walk = MagicMock(return_value="right")
    assert ag._badge2_action(_st(CERULEAN_GYM_MAP, 4, 13)) == "right"
    assert ag._truth_walk.call_args[0][1] == {(5, 3)}


# ---- the grind ---------------------------------------------------------------------------------


def test_under_leveled_lane_grinds_instead_of_challenging(tmp_path):
    ag = _ag(tmp_path, level=BADGE2_GRIND_LEVEL - 1)
    assert ag._badge2_action(_st(CERULEAN_CITY_MAP, 19, 18)) == "up"
    assert ag._truth_walk.call_args[0][2] == "to nugget bridge"
    # City north-edge targets are the OPEN row-0 cells only.
    assert ag._truth_walk.call_args[0][1] == {(0, 0), (2, 0)}


def test_grind_walks_off_the_edge_when_standing_on_it(tmp_path):
    ag = _ag(tmp_path, level=BADGE2_GRIND_LEVEL - 1)
    ag._truth_walk = MagicMock(return_value=None)  # standing on the edge target
    assert ag._badge2_action(_st(CERULEAN_CITY_MAP, 0, 0)) == "up"


def test_grind_route24_heads_east_then_flips_at_the_bridge_head(tmp_path):
    ag = _ag(tmp_path, level=BADGE2_GRIND_LEVEL - 1)
    assert ag._badge2_action(_st(ROUTE_24_MAP, 11, 30)) == "up"
    assert ag._truth_walk.call_args[0][2] == "to route 25"
    ag._grind_flip = True
    ag._truth_walk = MagicMock(return_value=None)  # standing at the bridge head
    assert ag._badge2_action(_st(ROUTE_24_MAP, 10, 16)) == "up"
    assert ag._grind_flip is False


def test_grind_route25_sweeps_then_turns_back(tmp_path):
    ag = _ag(tmp_path, level=BADGE2_GRIND_LEVEL - 1)
    ag._truth_walk = MagicMock(return_value=None)  # reached the sweep end
    assert ag._badge2_action(_st(ROUTE_25_MAP, 40, 4)) == "left"
    assert ag._grind_flip is True
    ag._truth_walk = MagicMock(return_value="left")
    assert ag._badge2_action(_st(ROUTE_25_MAP, 30, 4)) == "left"
    assert ag._truth_walk.call_args[0][2] == "back to route 24"
    ag._truth_walk = MagicMock(return_value=None)
    assert ag._badge2_action(_st(ROUTE_25_MAP, 0, 0)) == "left"


def test_grind_route24_flip_walk_in_progress_and_route25_forward(tmp_path):
    ag = _ag(tmp_path, level=BADGE2_GRIND_LEVEL - 1)
    ag._grind_flip = True
    ag._truth_walk = MagicMock(return_value="down")
    assert ag._badge2_action(_st(ROUTE_24_MAP, 11, 10)) == "down"
    ag._grind_flip = False
    ag._truth_walk = MagicMock(return_value="right")
    assert ag._badge2_action(_st(ROUTE_25_MAP, 10, 4)) == "right"
    assert ag._truth_walk.call_args[0][1] == {(40, 4), (40, 3)}


def test_grind_route24_walks_off_east_edge_when_standing_on_it(tmp_path):
    ag = _ag(tmp_path, level=BADGE2_GRIND_LEVEL - 1)
    ag._truth_walk = MagicMock(return_value=None)
    assert ag._badge2_action(_st(ROUTE_24_MAP, 2, 0)) == "right"


def test_grind_inert_off_its_maps(tmp_path):
    ag = _ag(tmp_path, level=BADGE2_GRIND_LEVEL - 1)
    assert ag._badge2_grind_action(_st(CERULEAN_GYM_MAP, 4, 13)) is None


# ---- learn-flow recovery -----------------------------------------------------------------------


def _wedged_agent(tmp_path, cc28_values, moves=(10, 45, 52, 43)):
    ag = _make_agent(tmp_path)
    ag.controller = MagicMock()
    ag.memory.battle_menu_visible = MagicMock(return_value=False)
    seq = list(cc28_values)

    def read(addr):
        if addr == 0xCC28:
            return seq.pop(0) if seq else 0
        base = ag.memory.PARTY_BASE
        if base + 8 <= addr < base + 12:
            return moves[addr - base - 8]
        return 0

    ag.memory._read = MagicMock(side_effect=read)
    ag._battle_wedge_attempts = 1
    return ag


def test_learn_flow_gives_up_the_lowest_power_move(tmp_path):
    ag = _wedged_agent(tmp_path, cc28_values=[1, 1, 3])  # picker appears on the third read
    ag._recover_battle_wedge()
    pressed = [c.args[0] for c in ag.controller.press.call_args_list]
    # After the B volley: two probing A's, then the picker path — one DOWN (Growl, slot 2), A.
    assert pressed[:8] == ["b"] * 8
    assert pressed[8:][:2] == ["a", "a"]
    assert "down" in pressed[10:] and pressed[-1] == "a" or ag.controller.mash_a.called


def test_learn_flow_gives_up_without_picker_after_probing(tmp_path):
    ag = _wedged_agent(tmp_path, cc28_values=[1] * 8)
    ag._recover_battle_wedge()
    pressed = [c.args[0] for c in ag.controller.press.call_args_list]
    assert pressed.count("a") == 8  # probed the cap, never found the picker


def test_recovery_stays_b_only_when_the_menu_is_up(tmp_path):
    ag = _make_agent(tmp_path)
    ag.controller = MagicMock()
    ag.memory.battle_menu_visible = MagicMock(return_value=True)
    ag._battle_wedge_attempts = 1
    ag._recover_battle_wedge()
    pressed = [c.args[0] for c in ag.controller.press.call_args_list]
    assert pressed == ["b"] * 8  # FIGHT is drawn: an A would re-enter the remembered cursor


def test_decision_chain_routes_badge2_and_disables_gym_restores(tmp_path):
    ag = _ag(tmp_path)
    ag._badge2_action = MagicMock(return_value="up")
    ag._pewter_heal_action = MagicMock(return_value=None)
    assert ag.choose_overworld_action(_st(CERULEAN_GYM_MAP, 4, 13)) == "up"
    assert ag._quest_nav_active is True


def test_gym_falls_back_to_a_press_when_no_path_remains(tmp_path):
    ag = _ag(tmp_path)
    ag._truth_walk = MagicMock(return_value=None)
    assert ag._badge2_action(_st(CERULEAN_GYM_MAP, 7, 8)) is None  # driver defers; navigator owns it


def test_battle_turn_advances_ko_text_when_enemy_is_down(tmp_path):
    from memory_reader import BattleState

    ag = _make_agent(tmp_path)
    ag.controller = MagicMock()
    ag._await_battle_menu = MagicMock(return_value=False)
    ag.memory.read_battle_state = MagicMock(
        return_value=BattleState(battle_type=2, enemy_hp=0, enemy_max_hp=41, player_hp=34, player_max_hp=68)
    )
    ag.battle_strategy.choose_action = MagicMock(side_effect=AssertionError("strategy ran on a downed enemy"))
    before = ag.turn_count
    ag.run_battle_turn()
    assert ag.turn_count == before + 1
    assert [c.args[0] for c in ag.controller.press.call_args_list] == ["b", "a"]


def test_leveled_lane_on_the_routes_defers_to_other_drivers(tmp_path):
    ag = _ag(tmp_path)  # at grind level: no grind, and the routes are not gym ground
    assert ag._badge2_action(_st(ROUTE_24_MAP, 11, 20)) is None


def test_item_action_walks_the_bag_by_absolute_row(tmp_path):
    """The battle bag remembers its cursor between opens: the blind walk drifted onto CANCEL
    and parked 88,000 turns over a wild NidoranF. The walk now reads scroll+cursor live."""
    from memory_reader import BattleState

    ag = _make_agent(tmp_path)
    ag.controller = MagicMock()
    ag._await_battle_menu = MagicMock(return_value=True)
    ag._select_battle_menu = MagicMock(return_value=True)
    ag.memory.read_battle_state = MagicMock(
        return_value=BattleState(battle_type=1, enemy_hp=20, enemy_max_hp=27, player_hp=14, player_max_hp=68)
    )
    ag.memory.find_healing_item = MagicMock(return_value=(3, 0x14))
    ag.battle_strategy.choose_action = MagicMock(return_value={"action": "item", "item": "Potion", "bag_index": 3})
    # cursor parked at absolute row 4 (CANCEL): reads walk it 4 -> up -> 3
    reads = {0xCC36: [2, 2, 2], 0xCC26: [2, 1, 1]}

    def read(addr):
        if addr in reads and reads[addr]:
            return reads[addr].pop(0)
        return 0

    ag.memory._read = MagicMock(side_effect=read)
    ag.run_battle_turn()
    pressed = [c.args[0] for c in ag.controller.press.call_args_list]
    assert pressed.count("up") == 1 and pressed[-1] == "a"  # one verified step up, then use
