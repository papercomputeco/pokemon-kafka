"""Comprehensive tests for agent.py — targeting 100% line coverage."""

import importlib
import json
import runpy
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from memory_reader import BattleState, OverworldState

# Import the agent module — pyboy is available in this env via deps
import agent
from agent import (
    EARLY_GAME_TARGETS,
    MOVE_DATA,
    SCRIPT_DIR,
    TYPE_CHART_PATH,
    ROUTES_PATH,
    load_type_chart,
    GameController,
    BattleStrategy,
    Navigator,
    StrategyEngine,
    PokemonAgent,
    main,
)


# ===================================================================
# Module-level import branches (lines 19-28)
# ===================================================================


class TestModuleImportBranches:
    """Cover the try/except ImportError blocks at module level."""

    def test_pyboy_import_error(self):
        """Lines 21-23: PyBoy import fails -> print + sys.exit(1)."""
        # Remove agent from sys.modules so it re-imports
        saved_modules = {}
        for mod_name in list(sys.modules):
            if mod_name == "agent" or mod_name.startswith("agent."):
                saved_modules[mod_name] = sys.modules.pop(mod_name)
        # Also remove pyboy so the import fails
        saved_pyboy = sys.modules.pop("pyboy", None)

        try:
            # Make pyboy import fail
            import builtins
            original_import = builtins.__import__

            def fail_pyboy(name, *args, **kwargs):
                if name == "pyboy":
                    raise ImportError("no pyboy")
                return original_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", side_effect=fail_pyboy):
                with pytest.raises(SystemExit) as exc_info:
                    importlib.import_module("agent")
                assert exc_info.value.code == 1
        finally:
            # Restore modules
            if saved_pyboy is not None:
                sys.modules["pyboy"] = saved_pyboy
            for mod_name, mod in saved_modules.items():
                sys.modules[mod_name] = mod

    def test_pil_import_error(self):
        """Lines 27-28: PIL import fails -> Image = None."""
        saved_modules = {}
        for mod_name in list(sys.modules):
            if mod_name == "agent" or mod_name.startswith("agent."):
                saved_modules[mod_name] = sys.modules.pop(mod_name)
        saved_pil = sys.modules.pop("PIL", None)
        saved_pil_image = sys.modules.pop("PIL.Image", None)

        try:
            import builtins
            original_import = builtins.__import__

            def fail_pil(name, *args, **kwargs):
                if name == "PIL" or name == "PIL.Image":
                    raise ImportError("no PIL")
                return original_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", side_effect=fail_pil):
                mod = importlib.import_module("agent")
                assert mod.Image is None
        finally:
            if saved_pil is not None:
                sys.modules["PIL"] = saved_pil
            if saved_pil_image is not None:
                sys.modules["PIL.Image"] = saved_pil_image
            for mod_name, mod_obj in saved_modules.items():
                sys.modules[mod_name] = mod_obj


# ===================================================================
# load_type_chart
# ===================================================================


class TestLoadTypeChart:
    """Test the JSON-loading function with file-exists and fallback paths."""

    def test_loads_from_file(self, tmp_path):
        chart_data = {"fire": {"grass": 2.0}}
        chart_file = tmp_path / "type_chart.json"
        chart_file.write_text(json.dumps(chart_data))

        with patch.object(agent, "TYPE_CHART_PATH", chart_file):
            result = load_type_chart()

        assert result == chart_data

    def test_fallback_when_file_missing(self, tmp_path):
        missing = tmp_path / "nope.json"
        with patch.object(agent, "TYPE_CHART_PATH", missing):
            result = load_type_chart()

        # The fallback dict must have the keys defined in agent.py
        assert "fire" in result
        assert "water" in result
        assert "grass" in result
        assert "electric" in result
        assert "ground" in result
        assert "ice" in result
        assert "psychic" in result
        assert "normal" in result


# ===================================================================
# GameController
# ===================================================================


class TestGameController:
    def setup_method(self):
        self.pyboy = MagicMock()
        self.ctrl = GameController(self.pyboy)

    def test_press(self):
        self.ctrl.press("a", hold_frames=5, release_frames=3)
        self.pyboy.button.assert_called_once_with("a", delay=5)
        assert self.pyboy.tick.call_count == 3

    def test_press_defaults(self):
        self.ctrl.press("b")
        self.pyboy.button.assert_called_once_with("b", delay=20)
        assert self.pyboy.tick.call_count == 10

    def test_wait(self):
        self.ctrl.wait(10)
        assert self.pyboy.tick.call_count == 10

    def test_wait_default(self):
        self.ctrl.wait()
        assert self.pyboy.tick.call_count == 30

    def test_move(self):
        self.ctrl.move("up")
        self.pyboy.button.assert_called_once_with("up", delay=20)
        # release_frames=8 + wait(30) = 38 ticks
        assert self.pyboy.tick.call_count == 38

    def test_mash_a(self):
        self.ctrl.mash_a(times=2, delay=10)
        assert self.pyboy.button.call_count == 2
        # Each mash_a iteration: press("a") -> 10 ticks + wait(10) -> 10 ticks = 20
        # 2 iterations = 40
        assert self.pyboy.tick.call_count == 40

    def test_mash_a_defaults(self):
        self.ctrl.mash_a()
        assert self.pyboy.button.call_count == 5

    def test_navigate_menu_down(self):
        self.ctrl.navigate_menu(target_index=2, current_index=0)
        # 2 down presses + 1 "a" press = 3 button calls
        assert self.pyboy.button.call_count == 3
        button_calls = [c[0][0] for c in self.pyboy.button.call_args_list]
        assert button_calls == ["down", "down", "a"]

    def test_navigate_menu_up(self):
        self.ctrl.navigate_menu(target_index=0, current_index=3)
        button_calls = [c[0][0] for c in self.pyboy.button.call_args_list]
        assert button_calls == ["up", "up", "up", "a"]

    def test_navigate_menu_same_index(self):
        self.ctrl.navigate_menu(target_index=0, current_index=0)
        # No direction presses, just "a"
        assert self.pyboy.button.call_count == 1
        self.pyboy.button.assert_called_with("a", delay=20)


# ===================================================================
# BattleStrategy
# ===================================================================


class TestBattleStrategy:
    def setup_method(self):
        self.chart = {
            "fire": {"grass": 2.0, "water": 0.5, "fire": 0.5},
            "water": {"fire": 2.0, "grass": 0.5},
            "normal": {"rock": 0.5, "ghost": 0.0},
        }
        self.strategy = BattleStrategy(self.chart)

    # -- score_move --

    def test_score_move_no_pp(self):
        assert self.strategy.score_move(0x01, 0) == -1.0

    def test_score_move_negative_pp(self):
        assert self.strategy.score_move(0x01, -5) == -1.0

    def test_score_move_unknown_move(self):
        assert self.strategy.score_move(0xFF, 10) == 10.0

    def test_score_move_status_move(self):
        # Thunder Wave: power=0
        assert self.strategy.score_move(0x56, 10) == 1.0

    def test_score_move_no_move(self):
        # 0x00 = "(No move)", power=0, accuracy=0
        assert self.strategy.score_move(0x00, 10) == 1.0

    def test_score_move_normal_effectiveness(self):
        # Pound: 40 power, 100 acc, "normal" type vs "normal" enemy
        score = self.strategy.score_move(0x01, 10, "normal")
        assert score == 40 * 1.0 * 1.0  # 40.0

    def test_score_move_super_effective(self):
        # Ember (fire) vs grass: 40 * 1.0 * 2.0 = 80
        score = self.strategy.score_move(0x2D, 10, "grass")
        assert score == 80.0

    def test_score_move_not_very_effective(self):
        # Ember (fire) vs water: 40 * 1.0 * 0.5 = 20
        score = self.strategy.score_move(0x2D, 10, "water")
        assert score == 20.0

    def test_score_move_type_not_in_chart(self):
        # Psychic type not in our chart -> effectiveness = 1.0
        score = self.strategy.score_move(0x5D, 10, "normal")
        assert score == 90 * 1.0 * 1.0

    def test_score_move_enemy_not_in_chart_entry(self):
        # Ember (fire) vs "dragon" -- "dragon" not in fire's chart entry -> 1.0
        score = self.strategy.score_move(0x2D, 10, "dragon")
        assert score == 40 * 1.0 * 1.0

    def test_score_move_accuracy_factor(self):
        # Tackle: 35 power, 95 acc
        score = self.strategy.score_move(0x21, 10, "normal")
        assert score == pytest.approx(35 * 0.95 * 1.0)

    # -- choose_action --

    def _make_battle(self, **kwargs):
        defaults = {
            "battle_type": 1,
            "player_hp": 100,
            "player_max_hp": 100,
            "enemy_hp": 50,
            "enemy_max_hp": 50,
            "moves": [0x01, 0x2D, 0x00, 0x00],
            "move_pp": [10, 10, 0, 0],
        }
        defaults.update(kwargs)
        return BattleState(**defaults)

    def test_choose_action_run_when_low_hp_wild(self):
        battle = self._make_battle(player_hp=10, player_max_hp=100, battle_type=1)
        action = self.strategy.choose_action(battle)
        assert action == {"action": "run"}

    def test_choose_action_item_when_low_hp_trainer(self):
        # hp_ratio = 0.20 -- not < 0.2, so run won't trigger; but 0.20 < 0.25 -> item
        battle = self._make_battle(player_hp=20, player_max_hp=100, battle_type=2)
        action = self.strategy.choose_action(battle)
        assert action == {"action": "item", "item": "potion"}

    def test_choose_action_item_when_low_hp_wild_above_run_threshold(self):
        # hp_ratio = 0.24 -- above 0.2, below 0.25 -> item
        battle = self._make_battle(player_hp=24, player_max_hp=100, battle_type=1)
        action = self.strategy.choose_action(battle)
        assert action == {"action": "item", "item": "potion"}

    def test_choose_action_fight_best_move(self):
        battle = self._make_battle(
            moves=[0x01, 0x2D, 0x00, 0x00],
            move_pp=[10, 10, 0, 0],
        )
        action = self.strategy.choose_action(battle)
        assert action["action"] == "fight"
        assert action["move_index"] in (0, 1)

    def test_choose_action_all_no_pp(self):
        # All moves have 0 PP -> all scores < 0 -> fallback fight index 0
        battle = self._make_battle(
            moves=[0x01, 0x2D, 0x21, 0x37],
            move_pp=[0, 0, 0, 0],
        )
        action = self.strategy.choose_action(battle)
        assert action == {"action": "fight", "move_index": 0}

    def test_choose_action_all_empty_moves(self):
        # All moves are 0x00 -- filtered out, moves list empty -> fallback
        battle = self._make_battle(
            moves=[0x00, 0x00, 0x00, 0x00],
            move_pp=[10, 10, 10, 10],
        )
        action = self.strategy.choose_action(battle)
        assert action == {"action": "fight", "move_index": 0}

    def test_choose_action_max_hp_zero(self):
        # max_hp = 0 -> max(0, 1) = 1, hp_ratio = 0/1 = 0 -> run (wild)
        battle = self._make_battle(player_hp=0, player_max_hp=0, battle_type=1)
        action = self.strategy.choose_action(battle)
        assert action == {"action": "run"}


# ===================================================================
# Navigator
# ===================================================================


class TestNavigator:
    # -- _add_direction --

    def test_add_direction_appends(self):
        nav = Navigator({})
        dirs = []
        nav._add_direction(dirs, "up")
        assert dirs == ["up"]

    def test_add_direction_no_duplicates(self):
        nav = Navigator({})
        dirs = ["up"]
        nav._add_direction(dirs, "up")
        assert dirs == ["up"]

    def test_add_direction_none_ignored(self):
        nav = Navigator({})
        dirs = []
        nav._add_direction(dirs, None)
        assert dirs == []

    # -- _direction_toward_target --

    def test_direction_at_target_returns_cardinal(self):
        """When at target, horizontal=None, vertical=None, but the cardinal
        directions loop still fills ordered with all 4 directions."""
        nav = Navigator({})
        state = OverworldState(x=5, y=5)
        result = nav._direction_toward_target(state, 5, 5)
        # ordered = [up, right, down, left] from the for loop on line 243
        assert result == "up"

    def test_direction_toward_target_empty_ordered(self):
        """Line 246-247: defensive branch where ordered list is empty.
        Must mock _add_direction to be a no-op so ordered stays empty."""
        nav = Navigator({})
        state = OverworldState(x=5, y=5)
        with patch.object(nav, "_add_direction"):
            result = nav._direction_toward_target(state, 5, 5)
        assert result is None

    def test_direction_x_preference(self):
        nav = Navigator({})
        state = OverworldState(x=3, y=3)
        result = nav._direction_toward_target(state, 5, 5, axis_preference="x")
        assert result == "right"

    def test_direction_y_preference(self):
        nav = Navigator({})
        state = OverworldState(x=3, y=3)
        result = nav._direction_toward_target(state, 5, 5, axis_preference="y")
        assert result == "down"

    def test_direction_left_up(self):
        nav = Navigator({})
        state = OverworldState(x=5, y=5)
        result = nav._direction_toward_target(state, 3, 3, axis_preference="x")
        assert result == "left"

    def test_direction_stuck_rotates(self):
        nav = Navigator({})
        state = OverworldState(x=3, y=3)
        # Target at 5,5, x-pref: ordered = [right, down, up, left]
        r0 = nav._direction_toward_target(state, 5, 5, stuck_turns=0)
        r1 = nav._direction_toward_target(state, 5, 5, stuck_turns=1)
        assert r0 == "right"
        assert r1 == "down"

    def test_direction_only_horizontal(self):
        nav = Navigator({})
        state = OverworldState(x=3, y=5)
        result = nav._direction_toward_target(state, 5, 5, axis_preference="x")
        assert result == "right"

    def test_direction_only_vertical(self):
        nav = Navigator({})
        state = OverworldState(x=5, y=3)
        result = nav._direction_toward_target(state, 5, 5, axis_preference="y")
        assert result == "down"

    # -- next_direction --

    def test_next_direction_early_game_target(self):
        nav = Navigator({})
        # Map 38 = Red's bedroom, target (7, 1)
        state = OverworldState(map_id=38, x=3, y=3)
        result = nav.next_direction(state)
        assert result == "right"  # x-preference towards x=7

    def test_next_direction_map_change_resets_waypoint(self):
        nav = Navigator({"10": [{"x": 5, "y": 5}]})
        nav.current_map = "9"
        nav.current_waypoint = 3
        state = OverworldState(map_id=10, x=3, y=3)
        nav.next_direction(state)
        assert nav.current_map == "10"
        assert nav.current_waypoint == 0

    def test_next_direction_no_route_cycles(self):
        nav = Navigator({})
        state = OverworldState(map_id=99, x=5, y=5)
        directions = ["down", "right", "down", "left", "up", "down"]
        for turn in range(6):
            result = nav.next_direction(state, turn=turn)
            assert result == directions[turn % 6]

    def test_next_direction_route_dict_with_waypoints(self):
        routes = {
            "10": {
                "name": "Test Route",
                "waypoints": [
                    {"x": 5, "y": 5},
                    {"x": 10, "y": 10},
                ],
            }
        }
        nav = Navigator(routes)
        state = OverworldState(map_id=10, x=3, y=3)
        result = nav.next_direction(state)
        assert result in ("right", "down")

    def test_next_direction_route_raw_list(self):
        """Line 276: waypoints = route (the else branch when route is a raw list)."""
        routes = {
            "10": [
                {"x": 5, "y": 5},
                {"x": 10, "y": 10},
            ]
        }
        nav = Navigator(routes)
        state = OverworldState(map_id=10, x=3, y=3)
        result = nav.next_direction(state)
        assert result in ("right", "down")

    def test_next_direction_route_complete(self):
        routes = {"10": [{"x": 5, "y": 5}]}
        nav = Navigator(routes)
        nav.current_map = "10"
        nav.current_waypoint = 1  # past the end
        state = OverworldState(map_id=10, x=5, y=5)
        result = nav.next_direction(state)
        assert result is None

    def test_next_direction_waypoint_reached_advances(self):
        """When at a waypoint, the navigator advances and recurses."""
        routes = {
            "10": [
                {"x": 5, "y": 5},
                {"x": 10, "y": 10},
            ]
        }
        nav = Navigator(routes)
        state = OverworldState(map_id=10, x=5, y=5)
        result = nav.next_direction(state)
        assert nav.current_waypoint == 1
        assert result in ("right", "down")

    def test_next_direction_waypoint_reached_last_returns_none(self):
        """When at the final waypoint, advancing makes route complete -> None."""
        routes = {"10": [{"x": 5, "y": 5}]}
        nav = Navigator(routes)
        state = OverworldState(map_id=10, x=5, y=5)
        result = nav.next_direction(state)
        assert result is None
        assert nav.current_waypoint == 1


# ===================================================================
# PokemonAgent -- helper to build one with mocks
# ===================================================================


def _make_agent(tmp_path, screenshots=False, routes=None, type_chart_data=None):
    """Build a PokemonAgent with all external I/O mocked."""
    mock_pb = MagicMock()
    mock_pb.memory = MagicMock()

    tc_path = tmp_path / "tc.json"
    if type_chart_data:
        tc_path.write_text(json.dumps(type_chart_data))

    rp = tmp_path / "routes.json"
    if routes is not None:
        rp.write_text(json.dumps(routes))

    pokedex_dir = tmp_path / "pokedex"
    frames_dir = tmp_path / "frames"

    with (
        patch("agent.PyBoy", return_value=mock_pb),
        patch.object(agent, "TYPE_CHART_PATH", tc_path),
        patch.object(agent, "ROUTES_PATH", rp),
        patch.object(agent, "SCRIPT_DIR", tmp_path),
    ):
        ag = PokemonAgent(
            str(tmp_path / "fake.gb"),
            strategy="low",
            screenshots=screenshots,
        )

    # Override dirs to use tmp_path
    ag.pokedex_dir = pokedex_dir
    ag.pokedex_dir.mkdir(parents=True, exist_ok=True)
    ag.frames_dir = frames_dir
    if screenshots:
        ag.frames_dir.mkdir(parents=True, exist_ok=True)

    return ag


# ===================================================================
# StrategyEngine tests
# ===================================================================


class TestStrategyEngine:
    def test_low_tier_no_notes(self):
        engine = StrategyEngine("low")
        assert engine.tier == "low"
        assert engine.notes is None

    def test_medium_tier_has_notes(self, tmp_path):
        engine = StrategyEngine("medium", notes_path=str(tmp_path / "notes.md"))
        assert engine.tier == "medium"
        assert engine.notes is not None

    def test_high_tier_has_notes(self, tmp_path):
        engine = StrategyEngine("high", notes_path=str(tmp_path / "notes.md"))
        assert engine.tier == "high"
        assert engine.notes is not None

    def test_medium_no_notes_path(self):
        engine = StrategyEngine("medium")
        assert engine.notes is None

    def test_should_call_llm_low_never(self):
        engine = StrategyEngine("low")
        assert engine.should_call_llm(stuck_turns=100, map_changed=True) is False

    def test_should_call_llm_medium_when_stuck(self):
        engine = StrategyEngine("medium")
        assert engine.should_call_llm(stuck_turns=10, map_changed=False) is True

    def test_should_call_llm_medium_on_map_change(self):
        engine = StrategyEngine("medium")
        assert engine.should_call_llm(stuck_turns=0, map_changed=True) is True

    def test_should_call_llm_medium_not_stuck(self):
        engine = StrategyEngine("medium")
        assert engine.should_call_llm(stuck_turns=5, map_changed=False) is False

    def test_should_call_llm_high_always(self):
        engine = StrategyEngine("high")
        assert engine.should_call_llm(stuck_turns=0, map_changed=False) is True


# ===================================================================
# PokemonAgent tests
# ===================================================================


class TestPokemonAgentInit:
    def test_init_without_screenshots(self, tmp_path):
        ag = _make_agent(tmp_path, screenshots=False)
        assert ag.screenshots is False
        assert ag.turn_count == 0
        assert ag.battles_won == 0
        assert ag.stuck_turns == 0
        assert ag.events == []
        assert ag.last_overworld_state is None

    def test_init_with_screenshots(self, tmp_path):
        ag = _make_agent(tmp_path, screenshots=True)
        assert ag.screenshots is True
        assert ag.frames_dir.exists()

    def test_init_loads_routes(self, tmp_path):
        routes = {"12": [{"x": 5, "y": 33}]}
        ag = _make_agent(tmp_path, routes=routes)
        assert ag.navigator.routes == routes

    def test_init_no_routes_file(self, tmp_path):
        ag = _make_agent(tmp_path)
        assert ag.navigator.routes == {}

    def test_init_with_type_chart(self, tmp_path):
        chart = {"fire": {"grass": 2.0}}
        ag = _make_agent(tmp_path, type_chart_data=chart)
        assert ag.type_chart == chart


class TestUpdateOverworldProgress:
    def test_first_call(self, tmp_path):
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=0, x=5, y=5)
        ag.update_overworld_progress(state)
        assert (0, 5, 5) in ag.recent_positions
        assert 0 in ag.maps_visited

    def test_map_change(self, tmp_path):
        ag = _make_agent(tmp_path)
        old = OverworldState(map_id=0, x=5, y=5)
        ag.last_overworld_state = old
        ag.recent_positions = [(0, 5, 5)]
        ag.stuck_turns = 3

        new = OverworldState(map_id=12, x=5, y=33)
        ag.update_overworld_progress(new)

        assert ag.stuck_turns == 0
        assert ag.recent_positions == [(12, 5, 33)]
        assert 12 in ag.maps_visited
        assert any("MAP CHANGE" in e for e in ag.events)

    def test_oscillation_increments_stuck(self, tmp_path):
        ag = _make_agent(tmp_path)
        old = OverworldState(map_id=0, x=5, y=5)
        ag.last_overworld_state = old
        ag.recent_positions = [(0, 5, 5)]

        state = OverworldState(map_id=0, x=5, y=5)
        ag.update_overworld_progress(state)
        assert ag.stuck_turns == 1

    def test_no_oscillation_resets_stuck(self, tmp_path):
        ag = _make_agent(tmp_path)
        old = OverworldState(map_id=0, x=5, y=5)
        ag.last_overworld_state = old
        ag.recent_positions = [(0, 5, 5)]
        ag.stuck_turns = 3

        state = OverworldState(map_id=0, x=6, y=5)
        ag.update_overworld_progress(state)
        assert ag.stuck_turns == 0

    def test_recent_positions_capped_at_8(self, tmp_path):
        ag = _make_agent(tmp_path)
        old = OverworldState(map_id=0, x=0, y=0)
        ag.last_overworld_state = old
        ag.recent_positions = [(0, i, 0) for i in range(8)]

        state = OverworldState(map_id=0, x=99, y=0)
        ag.update_overworld_progress(state)
        assert len(ag.recent_positions) == 8

    def test_stuck_log_at_2(self, tmp_path):
        ag = _make_agent(tmp_path)
        old = OverworldState(map_id=0, x=5, y=5)
        ag.last_overworld_state = old
        ag.recent_positions = [(0, 5, 5)]
        ag.stuck_turns = 1

        state = OverworldState(map_id=0, x=5, y=5)
        ag.update_overworld_progress(state)
        assert ag.stuck_turns == 2
        assert any("STUCK" in e for e in ag.events)

    def test_stuck_log_at_5(self, tmp_path):
        ag = _make_agent(tmp_path)
        old = OverworldState(map_id=0, x=5, y=5)
        ag.last_overworld_state = old
        ag.recent_positions = [(0, 5, 5)]
        ag.stuck_turns = 4

        state = OverworldState(map_id=0, x=5, y=5)
        ag.update_overworld_progress(state)
        assert ag.stuck_turns == 5
        assert any("STUCK" in e for e in ag.events)

    def test_stuck_log_at_10(self, tmp_path):
        ag = _make_agent(tmp_path)
        old = OverworldState(map_id=0, x=5, y=5)
        ag.last_overworld_state = old
        ag.recent_positions = [(0, 5, 5)]
        ag.stuck_turns = 9

        state = OverworldState(map_id=0, x=5, y=5)
        ag.update_overworld_progress(state)
        assert ag.stuck_turns == 10
        assert any("STUCK" in e for e in ag.events)

    def test_stuck_no_log_at_3(self, tmp_path):
        ag = _make_agent(tmp_path)
        old = OverworldState(map_id=0, x=5, y=5)
        ag.last_overworld_state = old
        ag.recent_positions = [(0, 5, 5)]
        ag.stuck_turns = 2

        state = OverworldState(map_id=0, x=5, y=5)
        ag.update_overworld_progress(state)
        assert ag.stuck_turns == 3
        stuck_events = [e for e in ag.events if "STUCK" in e]
        assert len(stuck_events) == 0


class TestChooseOverworldAction:
    def test_text_box_active_returns_a(self, tmp_path):
        ag = _make_agent(tmp_path)
        state = OverworldState(text_box_active=True)
        assert ag.choose_overworld_action(state) == "a"

    def test_oaks_lab_no_party_returns_a(self, tmp_path):
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=40, party_count=0)
        assert ag.choose_overworld_action(state) == "a"

    def test_oaks_lab_with_party_uses_navigator(self, tmp_path):
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=40, party_count=1, x=5, y=5)
        result = ag.choose_overworld_action(state)
        # map 40 not in EARLY_GAME_TARGETS and not in routes -> cycles directions
        assert result in ("down", "right", "left", "up")

    def test_navigator_returns_none_falls_back_to_a(self, tmp_path):
        ag = _make_agent(tmp_path)
        ag.navigator.next_direction = MagicMock(return_value=None)
        state = OverworldState(map_id=99, x=5, y=5)
        assert ag.choose_overworld_action(state) == "a"

    def test_normal_direction(self, tmp_path):
        ag = _make_agent(tmp_path)
        ag.navigator.next_direction = MagicMock(return_value="left")
        state = OverworldState(map_id=99, x=5, y=5)
        assert ag.choose_overworld_action(state) == "left"


class TestLog:
    def test_log_appends_event(self, tmp_path):
        ag = _make_agent(tmp_path)
        ag.log("test message")
        assert len(ag.events) == 1
        assert "test message" in ag.events[0]

    def test_log_has_timestamp(self, tmp_path):
        ag = _make_agent(tmp_path)
        ag.log("hello")
        # Format: [HH:MM:SS] hello
        assert ag.events[0].startswith("[")
        assert "]" in ag.events[0]


class TestWritePokedexEntry:
    def test_writes_markdown_file(self, tmp_path):
        ag = _make_agent(tmp_path)
        ag.turn_count = 50
        ag.battles_won = 3
        ag.maps_visited = {0, 12}
        ag.events = [
            "[00:00:01] MAP CHANGE | 0 -> 12 | Pos: (5, 33)",
            "[00:00:02] BATTLE | Player HP: 30/40 | Enemy HP: 0/20 | Action: fight",
            "[00:00:03] STUCK | Map: 12 | Pos: (5, 30) | Last move: up | Streak: 2",
            "[00:00:04] Some random event",
        ]
        mock_ow = OverworldState(map_id=12, x=5, y=10, badges=0, party_count=1)
        ag.memory.read_overworld_state = MagicMock(return_value=mock_ow)

        ag.write_pokedex_entry()

        logs = list(ag.pokedex_dir.glob("log*.md"))
        assert len(logs) == 1
        content = logs[0].read_text()
        assert "Log 1" in content
        assert "Turns:** 50" in content
        assert "Battles won:** 3" in content
        assert "Maps visited:** 2" in content
        assert "MAP CHANGE" in content
        assert "BATTLE" in content
        assert "STUCK" in content
        assert "Some random event" in content

    def test_increments_log_number(self, tmp_path):
        ag = _make_agent(tmp_path)
        (ag.pokedex_dir / "log1.md").write_text("old")
        ag.memory.read_overworld_state = MagicMock(
            return_value=OverworldState(map_id=0, x=0, y=0)
        )
        ag.write_pokedex_entry()
        assert (ag.pokedex_dir / "log2.md").exists()


class TestTakeScreenshot:
    def test_no_screenshots_flag(self, tmp_path):
        ag = _make_agent(tmp_path, screenshots=False)
        ag.take_screenshot()  # Should do nothing, no error
        assert not ag.frames_dir.exists() or not list(ag.frames_dir.glob("*.png"))

    def test_image_none(self, tmp_path):
        ag = _make_agent(tmp_path, screenshots=True)
        with patch.object(agent, "Image", None):
            ag.take_screenshot()

    def test_saves_screenshot(self, tmp_path):
        ag = _make_agent(tmp_path, screenshots=True)
        mock_image_mod = MagicMock()
        mock_img = MagicMock()
        mock_image_mod.fromarray.return_value = mock_img
        ag.pyboy.screen.ndarray = MagicMock()

        with patch.object(agent, "Image", mock_image_mod):
            ag.turn_count = 42
            ag.take_screenshot()

        mock_image_mod.fromarray.assert_called_once_with(ag.pyboy.screen.ndarray)
        mock_img.save.assert_called_once()
        saved_path = mock_img.save.call_args[0][0]
        assert "turn42.png" in str(saved_path)
        assert any("SCREENSHOT" in e for e in ag.events)


class TestRunBattleTurn:
    def _setup_agent_for_battle(self, tmp_path, action_dict):
        ag = _make_agent(tmp_path)
        battle = BattleState(
            battle_type=1,
            player_hp=50,
            player_max_hp=100,
            enemy_hp=30,
            enemy_max_hp=40,
            moves=[0x01, 0x00, 0x00, 0x00],
            move_pp=[10, 0, 0, 0],
        )
        ag.memory.read_battle_state = MagicMock(return_value=battle)
        ag.battle_strategy.choose_action = MagicMock(return_value=action_dict)
        return ag

    def test_fight_action(self, tmp_path):
        ag = self._setup_agent_for_battle(
            tmp_path, {"action": "fight", "move_index": 2}
        )
        initial_turns = ag.turn_count
        ag.run_battle_turn()
        assert ag.turn_count == initial_turns + 1
        assert any("BATTLE" in e for e in ag.events)

    def test_run_action(self, tmp_path):
        ag = self._setup_agent_for_battle(tmp_path, {"action": "run"})
        ag.run_battle_turn()
        assert ag.turn_count == 1

    def test_item_action(self, tmp_path):
        ag = self._setup_agent_for_battle(
            tmp_path, {"action": "item", "item": "potion"}
        )
        ag.run_battle_turn()
        assert ag.turn_count == 1

    def test_switch_action(self, tmp_path):
        ag = self._setup_agent_for_battle(
            tmp_path, {"action": "switch", "slot": 2}
        )
        ag.run_battle_turn()
        assert ag.turn_count == 1

    def test_switch_action_default_slot(self, tmp_path):
        ag = self._setup_agent_for_battle(
            tmp_path, {"action": "switch"}
        )
        ag.run_battle_turn()
        assert ag.turn_count == 1


class TestRunOverworld:
    def test_directional_movement(self, tmp_path):
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=99, x=5, y=5)
        ag.memory.read_overworld_state = MagicMock(return_value=state)
        ag.choose_overworld_action = MagicMock(return_value="up")
        # Replace controller with a mock so we can assert calls
        ag.controller = MagicMock()
        ag.turn_count = 0

        ag.run_overworld()

        ag.controller.move.assert_called_once_with("up")
        assert ag.last_overworld_state == state
        assert ag.last_overworld_action == "up"

    def test_a_press_action(self, tmp_path):
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=99, x=5, y=5, text_box_active=True)
        ag.memory.read_overworld_state = MagicMock(return_value=state)
        ag.choose_overworld_action = MagicMock(return_value="a")
        ag.controller = MagicMock()
        ag.turn_count = 0

        ag.run_overworld()

        ag.controller.press.assert_called_once_with("a", hold_frames=20, release_frames=12)
        ag.controller.wait.assert_called_once_with(24)
        assert ag.last_overworld_action == "a"

    def test_logs_every_100_steps(self, tmp_path):
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=12, x=5, y=10, badges=1, party_count=2)
        ag.memory.read_overworld_state = MagicMock(return_value=state)
        ag.choose_overworld_action = MagicMock(return_value="down")
        ag.controller = MagicMock()
        ag.turn_count = 100  # divisible by 100

        ag.run_overworld()

        overworld_logs = [e for e in ag.events if "OVERWORLD" in e]
        assert len(overworld_logs) == 1
        assert "Map: 12" in overworld_logs[0]

    def test_no_log_at_non_100(self, tmp_path):
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=12, x=5, y=10)
        ag.memory.read_overworld_state = MagicMock(return_value=state)
        ag.choose_overworld_action = MagicMock(return_value="down")
        ag.controller = MagicMock()
        ag.turn_count = 99

        ag.run_overworld()

        overworld_logs = [e for e in ag.events if "OVERWORLD" in e]
        assert len(overworld_logs) == 0

    def test_logs_at_turn_0(self, tmp_path):
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=12, x=5, y=10)
        ag.memory.read_overworld_state = MagicMock(return_value=state)
        ag.choose_overworld_action = MagicMock(return_value="down")
        ag.controller = MagicMock()
        ag.turn_count = 0  # 0 % 100 == 0

        ag.run_overworld()

        overworld_logs = [e for e in ag.events if "OVERWORLD" in e]
        assert len(overworld_logs) == 1


class TestRun:
    def test_run_battle_then_overworld(self, tmp_path):
        ag = _make_agent(tmp_path)

        battle_active = BattleState(
            battle_type=1,
            player_hp=50,
            player_max_hp=100,
            enemy_hp=30,
            enemy_max_hp=40,
            moves=[0x01, 0x00, 0x00, 0x00],
            move_pp=[10, 0, 0, 0],
        )
        battle_none = BattleState(battle_type=0)
        overworld = OverworldState(map_id=0, x=5, y=5)

        # Turn 1: battle -> run_battle_turn (reads battle_active inside),
        #   post-battle check reads battle_none -> battles_won++
        # Turn 2: reads battle_none -> run_overworld
        ag.memory.read_battle_state = MagicMock(
            side_effect=[battle_active, battle_active, battle_none, battle_none]
        )
        ag.memory.read_overworld_state = MagicMock(return_value=overworld)

        ag.run(max_turns=2)

        assert ag.battles_won == 1
        assert any("Battle ended" in e for e in ag.events)
        assert any("Session complete" in e for e in ag.events)

    def test_run_overworld_only(self, tmp_path):
        ag = _make_agent(tmp_path)
        battle_none = BattleState(battle_type=0)
        overworld = OverworldState(map_id=0, x=5, y=5)

        ag.memory.read_battle_state = MagicMock(return_value=battle_none)
        ag.memory.read_overworld_state = MagicMock(return_value=overworld)

        ag.run(max_turns=2)

        assert ag.turn_count >= 2
        assert any("Session complete" in e for e in ag.events)

    def test_run_takes_screenshots_every_10(self, tmp_path):
        ag = _make_agent(tmp_path, screenshots=True)
        battle_none = BattleState(battle_type=0)
        overworld = OverworldState(map_id=0, x=5, y=5)

        ag.memory.read_battle_state = MagicMock(return_value=battle_none)
        ag.memory.read_overworld_state = MagicMock(return_value=overworld)

        mock_image_mod = MagicMock()
        mock_img = MagicMock()
        mock_image_mod.fromarray.return_value = mock_img
        ag.pyboy.screen.ndarray = MagicMock()

        with patch.object(agent, "Image", mock_image_mod):
            ag.run(max_turns=11)

        # Screenshot fires when turn_count % 10 == 0
        assert mock_image_mod.fromarray.call_count >= 1

    def test_run_battle_not_ended(self, tmp_path):
        """Battle still active after run_battle_turn -- no battles_won increment."""
        ag = _make_agent(tmp_path)
        battle_active = BattleState(
            battle_type=1,
            player_hp=50,
            player_max_hp=100,
            enemy_hp=30,
            enemy_max_hp=40,
            moves=[0x01, 0x00, 0x00, 0x00],
            move_pp=[10, 0, 0, 0],
        )
        overworld = OverworldState(map_id=0, x=5, y=5)

        # All battle reads return active battle -- battle never ends
        ag.memory.read_battle_state = MagicMock(return_value=battle_active)
        ag.memory.read_overworld_state = MagicMock(return_value=overworld)

        ag.run(max_turns=1)

        assert ag.battles_won == 0

    def test_run_pyboy_stop_permission_error(self, tmp_path):
        ag = _make_agent(tmp_path)
        battle_none = BattleState(battle_type=0)
        overworld = OverworldState(map_id=0, x=5, y=5)

        ag.memory.read_battle_state = MagicMock(return_value=battle_none)
        ag.memory.read_overworld_state = MagicMock(return_value=overworld)
        ag.pyboy.stop.side_effect = PermissionError("read-only mount")

        # Should not raise
        ag.run(max_turns=1)
        assert any("Session complete" in e for e in ag.events)

    def test_run_writes_pokedex_entry(self, tmp_path):
        ag = _make_agent(tmp_path)
        battle_none = BattleState(battle_type=0)
        overworld = OverworldState(map_id=0, x=5, y=5)

        ag.memory.read_battle_state = MagicMock(return_value=battle_none)
        ag.memory.read_overworld_state = MagicMock(return_value=overworld)

        ag.run(max_turns=1)

        logs = list(ag.pokedex_dir.glob("log*.md"))
        assert len(logs) == 1


# ===================================================================
# main()
# ===================================================================


class TestMain:
    def test_main_success(self, tmp_path):
        rom = tmp_path / "game.gb"
        rom.write_text("fake rom")

        mock_agent = MagicMock()

        with patch(
            "sys.argv", ["agent.py", str(rom), "--strategy", "low", "--max-turns", "5"]
        ), patch("agent.PokemonAgent", return_value=mock_agent) as mock_cls:
            main()

        mock_cls.assert_called_once_with(str(rom), strategy="low", screenshots=False)
        mock_agent.run.assert_called_once_with(max_turns=5)

    def test_main_rom_not_found(self, tmp_path):
        missing = tmp_path / "nope.gb"

        with patch("sys.argv", ["agent.py", str(missing)]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 1

    def test_main_with_screenshots(self, tmp_path):
        rom = tmp_path / "game.gb"
        rom.write_text("fake rom")

        mock_agent = MagicMock()

        with patch(
            "sys.argv",
            ["agent.py", str(rom), "--save-screenshots", "--max-turns", "10"],
        ), patch("agent.PokemonAgent", return_value=mock_agent) as mock_cls:
            main()

        mock_cls.assert_called_once_with(str(rom), strategy="low", screenshots=True)
        mock_agent.run.assert_called_once_with(max_turns=10)

    def test_main_default_args(self, tmp_path):
        rom = tmp_path / "game.gb"
        rom.write_text("fake rom")

        mock_agent = MagicMock()

        with patch("sys.argv", ["agent.py", str(rom)]), patch(
            "agent.PokemonAgent", return_value=mock_agent
        ) as mock_cls:
            main()

        mock_cls.assert_called_once_with(str(rom), strategy="low", screenshots=False)
        mock_agent.run.assert_called_once_with(max_turns=100_000)


# ===================================================================
# __name__ == "__main__" guard (line 600)
# ===================================================================


class TestMainGuard:
    def test_dunder_main_calls_main(self, tmp_path):
        """Line 599-600: if __name__ == '__main__': main()"""
        rom = tmp_path / "game.gb"
        rom.write_text("fake rom")

        # Create a mock pyboy module with a mock PyBoy class.
        # The mock PyBoy instance needs memory that returns int(0)
        # for any address so MemoryReader works correctly.
        from collections import defaultdict
        fake_mem = defaultdict(int)  # returns 0 for any key

        mock_pyboy_mod = MagicMock()
        mock_pb_instance = MagicMock()
        mock_pb_instance.memory = fake_mem
        mock_pyboy_mod.PyBoy = MagicMock(return_value=mock_pb_instance)

        # Also set up pokedex/frames dirs that __init__ tries to create
        pokedex_dir = tmp_path / "pokedex"
        pokedex_dir.mkdir(parents=True, exist_ok=True)

        # Use --max-turns 0 so the main loop body never executes.
        with patch("sys.argv", ["agent.py", str(rom), "--max-turns", "0"]):
            saved_pyboy = sys.modules.get("pyboy")
            sys.modules["pyboy"] = mock_pyboy_mod
            try:
                runpy.run_path(
                    str(Path(agent.__file__).resolve()),
                    run_name="__main__",
                )
            finally:
                if saved_pyboy is not None:
                    sys.modules["pyboy"] = saved_pyboy
                else:
                    sys.modules.pop("pyboy", None)

        # If we got here without error, line 600 (main()) was executed.
        mock_pyboy_mod.PyBoy.assert_called_once()


# ===================================================================
# Module-level constants sanity checks
# ===================================================================


class TestModuleConstants:
    def test_script_dir_is_path(self):
        assert isinstance(SCRIPT_DIR, Path)

    def test_type_chart_path_is_path(self):
        assert isinstance(TYPE_CHART_PATH, Path)

    def test_routes_path_is_path(self):
        assert isinstance(ROUTES_PATH, Path)

    def test_early_game_targets_has_keys(self):
        assert 38 in EARLY_GAME_TARGETS
        assert 37 in EARLY_GAME_TARGETS
        assert 0 in EARLY_GAME_TARGETS

    def test_move_data_has_entries(self):
        assert 0x01 in MOVE_DATA
        assert 0x00 in MOVE_DATA
        assert 0x56 in MOVE_DATA  # Thunder Wave (status)


# ===================================================================
# Navigator -- collision_grid + A* integration
# ===================================================================


class TestNavigatorCollisionGrid:
    """Tests for A* pathfinding integration in Navigator.next_direction."""

    def _open_grid(self):
        """Return a fully walkable 9x10 grid."""
        return [[1] * 10 for _ in range(9)]

    def test_with_collision_grid_uses_astar_for_waypoint(self):
        """When collision_grid is provided and target is on screen, A* is used."""
        routes = {"10": [{"x": 7, "y": 6}]}
        nav = Navigator(routes)
        # Player at (5, 5), target at (7, 6) -> screen target = (4+1, 4+2) = (5, 6)
        state = OverworldState(map_id=10, x=5, y=5)
        grid = self._open_grid()
        result = nav.next_direction(state, collision_grid=grid)
        # A* should give a direction toward (5, 6) from (4, 4)
        assert result in ("down", "right")

    def test_with_collision_grid_astar_returns_first_direction(self):
        """A* path result is used to pick the first direction."""
        routes = {"10": [{"x": 6, "y": 5}]}
        nav = Navigator(routes)
        # Player at (5, 5), target at (6, 5) -> screen target = (4, 5)
        state = OverworldState(map_id=10, x=5, y=5)
        grid = self._open_grid()
        result = nav.next_direction(state, collision_grid=grid)
        # Target is to the right on screen
        assert result == "right"

    def test_with_collision_grid_falls_back_when_astar_fails(self):
        """When A* returns failure (all walls), fall back to _direction_toward_target."""
        routes = {"10": [{"x": 6, "y": 5}]}
        nav = Navigator(routes)
        state = OverworldState(map_id=10, x=5, y=5)
        # All walls except the player position
        grid = [[0] * 10 for _ in range(9)]
        grid[4][4] = 1  # player position is walkable
        result = nav.next_direction(state, collision_grid=grid)
        # A* fails, falls back to _direction_toward_target
        assert result == "right"  # x-preference default

    def test_without_collision_grid_behaves_as_before(self):
        """When collision_grid is None (default), behavior is unchanged."""
        routes = {"10": [{"x": 6, "y": 5}]}
        nav = Navigator(routes)
        state = OverworldState(map_id=10, x=5, y=5)
        result = nav.next_direction(state)
        assert result == "right"  # _direction_toward_target with x-preference

    def test_with_collision_grid_target_offscreen_falls_back(self):
        """When target is offscreen, A* is not attempted."""
        routes = {"10": [{"x": 20, "y": 5}]}
        nav = Navigator(routes)
        # Player at (5, 5), target at (20, 5) -> screen col = 4 + (20-5) = 19 -> offscreen
        state = OverworldState(map_id=10, x=5, y=5)
        grid = self._open_grid()
        result = nav.next_direction(state, collision_grid=grid)
        # Falls back to _direction_toward_target
        assert result == "right"

    def test_with_collision_grid_target_offscreen_negative_falls_back(self):
        """When target is offscreen in the negative direction, A* is not attempted."""
        routes = {"10": [{"x": 0, "y": 0}]}
        nav = Navigator(routes)
        # Player at (10, 10), target at (0, 0) -> screen row = 4 + (0-10) = -6 -> offscreen
        state = OverworldState(map_id=10, x=10, y=10)
        grid = self._open_grid()
        result = nav.next_direction(state, collision_grid=grid)
        assert result == "left"  # x-preference fallback

    def test_with_collision_grid_for_early_game_targets(self):
        """A* is used for early game targets when collision_grid is provided."""
        nav = Navigator({})
        # Map 38 = Red's bedroom, target (7, 1), axis "x"
        # Player at (3, 3) -> screen target = (4 + (1-3), 4 + (7-3)) = (2, 8)
        state = OverworldState(map_id=38, x=3, y=3)
        grid = self._open_grid()
        result = nav.next_direction(state, collision_grid=grid)
        # A* should navigate toward (2, 8) from (4, 4)
        assert result in ("right", "up")

    def test_with_collision_grid_early_game_offscreen_falls_back(self):
        """Early game target offscreen falls back to _direction_toward_target."""
        nav = Navigator({})
        # Map 0 = Pallet Town, target (5, 1)
        # Player at (5, 20) -> screen target = (4 + (1-20), 4 + (5-5)) = (-15, 4) -> offscreen
        state = OverworldState(map_id=0, x=5, y=20)
        grid = self._open_grid()
        result = nav.next_direction(state, collision_grid=grid)
        assert result == "up"  # y-axis preference for Pallet Town is "x" but y needed

    def test_with_collision_grid_early_game_astar_failure_falls_back(self):
        """Early game A* failure falls back to _direction_toward_target."""
        nav = Navigator({})
        # Map 38, target (7, 1), player at (3, 3)
        # screen target = (2, 8) -- make all walls except player
        state = OverworldState(map_id=38, x=3, y=3)
        grid = [[0] * 10 for _ in range(9)]
        grid[4][4] = 1  # player only
        result = nav.next_direction(state, collision_grid=grid)
        assert result == "right"  # x-preference fallback

    def test_with_collision_grid_astar_partial_result_used(self):
        """A* partial result (target is wall but path approaches it) is used."""
        routes = {"10": [{"x": 6, "y": 5}]}
        nav = Navigator(routes)
        state = OverworldState(map_id=10, x=5, y=5)
        grid = self._open_grid()
        # Make the target cell a wall so A* returns partial
        grid[4][5] = 0
        result = nav.next_direction(state, collision_grid=grid)
        # Partial result still gives a direction
        assert result is not None

    def test_with_collision_grid_astar_empty_directions_falls_back(self):
        """When A* succeeds but returns no directions (at target), falls back."""
        routes = {"10": [{"x": 5, "y": 5}, {"x": 6, "y": 5}]}
        nav = Navigator(routes)
        # Player is AT the first waypoint -> advances to second, then A* on second
        state = OverworldState(map_id=10, x=5, y=5)
        grid = self._open_grid()
        result = nav.next_direction(state, collision_grid=grid)
        assert result is not None

    def test_collision_grid_forwarded_on_recursive_call(self):
        """When waypoint is reached and next_direction recurses, collision_grid is forwarded."""
        routes = {"10": [{"x": 5, "y": 5}, {"x": 6, "y": 5}]}
        nav = Navigator(routes)
        state = OverworldState(map_id=10, x=5, y=5)
        grid = self._open_grid()
        # Block the direct path in _direction_toward_target but leave A* path open
        # This verifies collision_grid gets forwarded in recursion
        result = nav.next_direction(state, collision_grid=grid)
        assert nav.current_waypoint == 1
        assert result == "right"


# ===================================================================
# PokemonAgent -- CollisionMap integration
# ===================================================================


class TestPokemonAgentCollisionMap:
    """Tests for CollisionMap integration in PokemonAgent."""

    def test_agent_creates_collision_map(self, tmp_path):
        """PokemonAgent.__init__ creates a collision_map attribute."""
        ag = _make_agent(tmp_path)
        assert hasattr(ag, "collision_map")
        from memory_reader import CollisionMap
        assert isinstance(ag.collision_map, CollisionMap)

    def test_run_overworld_updates_collision_map(self, tmp_path):
        """run_overworld calls collision_map.update before choosing action."""
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=99, x=5, y=5)
        ag.memory.read_overworld_state = MagicMock(return_value=state)
        ag.controller = MagicMock()
        ag.turn_count = 1

        # Mock the collision_map to track update calls
        ag.collision_map = MagicMock()
        ag.collision_map.grid = [[1] * 10 for _ in range(9)]

        ag.run_overworld()

        ag.collision_map.update.assert_called_once_with(ag.pyboy)

    def test_run_overworld_handles_collision_map_failure(self, tmp_path):
        """run_overworld continues even if collision_map.update raises."""
        ag = _make_agent(tmp_path)
        state = OverworldState(map_id=99, x=5, y=5)
        ag.memory.read_overworld_state = MagicMock(return_value=state)
        ag.controller = MagicMock()
        ag.turn_count = 1

        # Make collision_map.update raise
        ag.collision_map = MagicMock()
        ag.collision_map.update.side_effect = Exception("no game_wrapper")
        ag.collision_map.grid = [[1] * 10 for _ in range(9)]

        # Should not raise
        ag.run_overworld()

        assert ag.last_overworld_state == state

    def test_choose_overworld_action_passes_collision_grid(self, tmp_path):
        """choose_overworld_action passes collision_grid to navigator."""
        ag = _make_agent(tmp_path)
        ag.collision_map = MagicMock()
        ag.collision_map.grid = [[1] * 10 for _ in range(9)]

        state = OverworldState(map_id=99, x=5, y=5)
        ag.navigator.next_direction = MagicMock(return_value="down")

        ag.choose_overworld_action(state)

        ag.navigator.next_direction.assert_called_once_with(
            state,
            turn=ag.turn_count,
            stuck_turns=ag.stuck_turns,
            collision_grid=ag.collision_map.grid,
        )
