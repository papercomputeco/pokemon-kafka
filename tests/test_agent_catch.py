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
    ag.memory._read = MagicMock(return_value=0)
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
    pressed = [c.args[0] for c in ag.controller.press.call_args_list]
    assert pressed[-1] == "a"  # the verified bag walk ends on the throw


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


def _downed_lead_battle():
    return BattleState(
        battle_type=1,
        enemy_species=SPEAROW,
        enemy_hp=29,
        enemy_max_hp=29,
        player_hp=0,
        player_max_hp=28,
        moves=[0x34, 0x00, 0x00, 0x00],
        move_pp=[10, 0, 0, 0],
    )


def _forced_switch_agent(tmp_path, party):
    """A battle agent parked on the 'Bring out which POKeMON?' menu: lead down, enemy alive,
    no battle menu for B to reach — with a live cursor register so the menu walk is real."""
    ag = _battle_agent(tmp_path, _downed_lead_battle())
    ag._await_battle_menu = MagicMock(return_value=False)
    ag.memory.read_party = MagicMock(return_value=party)
    cursor = {"v": 0}
    ag.memory._read = MagicMock(side_effect=lambda addr: cursor["v"] if addr == 0xCC26 else 0)

    def on_press(button, **kw):
        cursor["v"] += {"down": 1, "up": -1}.get(button, 0)

    ag.controller = MagicMock()
    ag.controller.press = MagicMock(side_effect=on_press)
    return ag


def test_forced_switch_sends_the_best_healthy_mon(tmp_path):
    """Lead down, battle live: the game holds the party menu B cannot leave (measured on the
    Route 6 grind: 150 fight/run decisions bounced off it). The turn answers it with the
    highest-level healthy mon instead of consulting the strategy."""
    ag = _forced_switch_agent(
        tmp_path,
        [
            {"species": "Mankey", "level": 10, "hp": 0, "max_hp": 28},
            {"species": "Drowzee", "level": 13, "hp": 0, "max_hp": 38},
            {"species": "Charmeleon", "level": 38, "hp": 106, "max_hp": 106},
            {"species": "Diglett", "level": 17, "hp": 33, "max_hp": 33},
        ],
    )
    ag.battle_strategy.choose_action = MagicMock(side_effect=AssertionError("strategy consulted at the forced switch"))
    ag.run_battle_turn()
    presses = [c.args[0] for c in ag.controller.press.call_args_list]
    assert presses.count("down") == 2  # cursor walked to Charmeleon's row
    assert presses[-2:] == ["a", "a"]  # select, then confirm through "Go! ..."
    assert any("SWITCH" in e and "Charmeleon" in e for e in ag.events)


def test_forced_switch_guard_ignores_stale_battle_hp(tmp_path):
    """wBattleMon HP lies until the lead is sent out: a 0 with a fully healthy party is a
    battle-intro artifact, and the turn falls through to the strategy."""
    ag = _forced_switch_agent(tmp_path, [{"species": "Charmeleon", "level": 38, "hp": 106, "max_hp": 106}])
    ag.battle_strategy.choose_action = MagicMock(return_value={"action": "run"})
    ag.run_battle_turn()
    ag.battle_strategy.choose_action.assert_called_once()


def test_forced_switch_yields_the_party_wipe_to_the_whiteout(tmp_path):
    ag = _forced_switch_agent(tmp_path, [{"species": "Mankey", "level": 10, "hp": 0, "max_hp": 28}])
    ag.battle_strategy.choose_action = MagicMock(return_value={"action": "run"})
    ag.run_battle_turn()
    ag.battle_strategy.choose_action.assert_called_once()
    assert not any("SWITCH" in e for e in ag.events)


def _end_to_end_battle_agent(tmp_path, party_after, whited_out=False):
    from unittest.mock import patch

    import agent as agent_mod
    from memory_reader import OverworldState

    ag = _make_agent(tmp_path)
    battle_active = BattleState(
        battle_type=1,
        player_hp=50,
        player_max_hp=100,
        enemy_hp=29,
        enemy_max_hp=29,
        enemy_species=SPEAROW,
        enemy_type1=0x00,
        enemy_type2=0x02,
        moves=[0x01, 0x00, 0x00, 0x00],
        move_pp=[10, 0, 0, 0],
        player_level=22,
    )
    battle_none = BattleState(battle_type=0)
    ag.memory.read_battle_state = MagicMock(side_effect=[battle_active, battle_active, battle_none, battle_none])
    ag.memory.read_overworld_state = MagicMock(return_value=OverworldState(map_id=15, x=70, y=10))
    ag.memory.find_healing_item = MagicMock(return_value=None)
    ag.memory.read_party_species = MagicMock(return_value=[CHARMELEON])
    ag.memory.player_whited_out = MagicMock(return_value=whited_out)
    ag.memory.read_party = MagicMock(return_value=party_after)
    ag.collector.encounter = MagicMock()
    return ag, patch.object(agent_mod, "Image", None)


def test_battle_end_emits_a_caught_encounter(tmp_path):
    """Party growth across the battle is the one disposition the win flag cannot express."""
    two = [
        {"species": "Charmeleon", "level": 22, "hp": 60, "max_hp": 63},
        {"species": "Spearow", "level": 10, "hp": 29, "max_hp": 29},
    ]
    ag, img = _end_to_end_battle_agent(tmp_path, two)
    with img:
        ag.run(max_turns=2)
    kwargs = ag.collector.encounter.call_args[0]
    assert kwargs[1] == "Spearow" and kwargs[8] == "caught" and kwargs[9] == 2


def test_battle_end_emits_escaped_or_lost_on_a_whiteout(tmp_path):
    one = [{"species": "Charmeleon", "level": 22, "hp": 0, "max_hp": 63}]
    ag, img = _end_to_end_battle_agent(tmp_path, one, whited_out=True)
    with img:
        ag.run(max_turns=2)
    assert ag.collector.encounter.call_args[0][8] == "escaped_or_lost"


def test_stop_condition_met_on_party_size(tmp_path):
    from agent import PokemonAgent
    from memory_reader import OverworldState

    ok = PokemonAgent._stop_condition_met(OverworldState(party_count=3), stop_on_party=3)
    assert ok
    assert not PokemonAgent._stop_condition_met(OverworldState(party_count=2), stop_on_party=3)


def test_catch_hook_caps_throws_and_returns_the_turn_to_the_strategy(tmp_path):
    """The hook bypasses choose_action's stall guard, so an uncapped throw loop at a wedged
    battle menu never unsticks (the roster bench's x=64 lane: 2,900 turns at one Rattata)."""
    ag = _battle_agent(tmp_path, _wild_battle())
    ag.catch_wanted = {SPEAROW}
    ag.battle_strategy.choose_action = MagicMock(return_value={"action": "fight", "move_index": 0})
    for _ in range(5):
        ag.run_battle_turn()
    assert ag._catch_throws == 3
    assert ag.battle_strategy.choose_action.call_count == 2  # turns 4 and 5 went back to the fight


def test_catch_throw_cap_resets_when_a_new_battle_starts(tmp_path):
    """The cap tracks its enemy by SPECIES, so without a battle-start reset one failed catch
    silences every later encounter of that species (measured in Diglett's Cave: 120 roam legs
    of Digletts, zero balls thrown after the first three)."""
    ag, img = _end_to_end_battle_agent(tmp_path, [{"species": "Charmeleon", "level": 22, "hp": 60, "max_hp": 63}])
    ag._catch_enemy = SPEAROW  # stale: a previous Spearow ate its three throws
    ag._catch_throws = 3
    with img:
        ag.run(max_turns=2)
    assert ag._catch_enemy is None and ag._catch_throws == 0


def test_catch_throw_cap_resets_on_a_new_enemy(tmp_path):
    ag = _battle_agent(tmp_path, _wild_battle())
    ag.catch_wanted = {SPEAROW, 0xA5}
    ag.battle_strategy.choose_action = MagicMock(return_value={"action": "fight", "move_index": 0})
    for _ in range(3):
        ag.run_battle_turn()
    ag.memory.read_battle_state = MagicMock(return_value=_wild_battle(species=0xA5))  # Rattata now
    ag.run_battle_turn()
    assert ag._catch_throws == 1  # fresh enemy, fresh cap
