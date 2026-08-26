"""The quartermaster's catch hook in the battle turn: a wanted wild outranks the fight."""

from unittest.mock import MagicMock

from memory_reader import BattleState
from test_agent import _make_agent

SPEAROW, CHARMELEON = 0x05, 0xB2


def _wild_battle(species=SPEAROW):
    return BattleState(
        battle_type=1,
        enemy_species=species,
        enemy_hp=29,
        enemy_max_hp=29,
        enemy_level=10,
        player_hp=63,
        player_max_hp=63,
        moves=[0x34, 0x00, 0x00, 0x00],
        move_pp=[10, 0, 0, 0],
    )


def _battle_agent(tmp_path, battle):
    ag = _make_agent(tmp_path)
    ag._await_battle_menu = MagicMock(return_value=True)
    ag._select_battle_menu = MagicMock(return_value=True)
    ag.controller = MagicMock()
    ag.memory.read_battle_state = MagicMock(return_value=battle)
    ag.memory.find_healing_item = MagicMock(return_value=None)
    ag.memory.read_party_species = MagicMock(return_value=[CHARMELEON])
    ag.memory.read_bag_items = MagicMock(return_value=[(0xEA, 1), (0x04, 5)])
    return ag


def test_catch_hook_outranks_the_fight(tmp_path):
    ag = _battle_agent(tmp_path, _wild_battle())
    ag.catch_wanted = {SPEAROW}
    ag.battle_strategy.choose_action = MagicMock(side_effect=AssertionError("strategy consulted despite catch"))
    ag.run_battle_turn()
    assert any("CATCH" in e for e in ag.events)
    ag._select_battle_menu.assert_called_once_with("item")
    ag.controller.navigate_menu.assert_called_once_with(1)  # the ball's bag slot


def test_catch_hook_defers_to_the_strategy_when_not_wanted(tmp_path):
    ag = _battle_agent(tmp_path, _wild_battle(species=0x6B))  # Zubat: not on the list
    ag.catch_wanted = {SPEAROW}
    ag.battle_strategy.choose_action = MagicMock(return_value={"action": "fight", "move_index": 0})
    ag.run_battle_turn()
    ag.battle_strategy.choose_action.assert_called_once()
    assert not any("CATCH" in e for e in ag.events)


def test_catch_hook_inert_without_a_wanted_list(tmp_path):
    ag = _battle_agent(tmp_path, _wild_battle())
    ag.battle_strategy.choose_action = MagicMock(return_value={"action": "fight", "move_index": 0})
    ag.run_battle_turn()
    ag.memory.read_party_species.assert_not_called()
    ag.battle_strategy.choose_action.assert_called_once()


def test_read_party_species_reads_the_slot_list(tmp_path):
    ag = _make_agent(tmp_path)
    mem = {ag.memory.ADDR_PARTY_COUNT: 2, 0xD164: CHARMELEON, 0xD165: SPEAROW}
    ag.memory._read = MagicMock(side_effect=lambda addr: mem.get(addr, 0))
    assert ag.memory.read_party_species() == [CHARMELEON, SPEAROW]
