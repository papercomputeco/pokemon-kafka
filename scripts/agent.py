#!/usr/bin/env python3
"""
Pokemon Agent — Autonomous turn-based RPG player via PyBoy.

Runs headless. Reads game state from memory. Makes decisions.
Sends inputs. Logs everything. Designed for stereOS + Tapes.

Usage:
    python3 agent.py path/to/pokemon_red.gb [--strategy low|medium|high]
"""

import argparse
import json
import sys
import time
import os
from pathlib import Path

try:
    from pyboy import PyBoy
except ImportError:
    print("PyBoy not installed. Run: pip install pyboy")
    sys.exit(1)

try:
    from PIL import Image
except ImportError:
    Image = None

from memory_reader import MemoryReader, BattleState, OverworldState, CollisionMap
from memory_file import MemoryFile
from pathfinding import astar_path

# ---------------------------------------------------------------------------
# Type chart (simplified — super effective multipliers)
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent
TYPE_CHART_PATH = SCRIPT_DIR.parent / "references" / "type_chart.json"
ROUTES_PATH = SCRIPT_DIR.parent / "references" / "routes.json"

# Early-game scripted targets to get from Red's room to Oak's lab.
# Coords are taken from pret/pokered map object data.
EARLY_GAME_TARGETS = {
    38: {"name": "Red's bedroom", "target": (7, 1), "axis": "x"},
    37: {"name": "Red's house 1F", "target": (2, 7), "axis": "y"},
    0: {"name": "Pallet Town", "target": (5, 1), "axis": "x"},
}

# Move ID → (name, type, power, accuracy)
# Subset of Gen 1 moves for demonstration
MOVE_DATA = {
    0x01: ("Pound", "normal", 40, 100),
    0x0A: ("Scratch", "normal", 40, 100),
    0x21: ("Tackle", "normal", 35, 95),
    0x2D: ("Ember", "fire", 40, 100),
    0x37: ("Water Gun", "water", 40, 100),
    0x49: ("Vine Whip", "grass", 35, 100),
    0x55: ("Thunderbolt", "electric", 95, 100),
    0x56: ("Thunder Wave", "electric", 0, 100),
    0x59: ("Thunder", "electric", 120, 70),
    0x3A: ("Ice Beam", "ice", 95, 100),
    0x3F: ("Flamethrower", "fire", 95, 100),
    0x39: ("Surf", "water", 95, 100),
    0x16: ("Razor Leaf", "grass", 55, 95),
    0x5D: ("Psychic", "psychic", 90, 100),
    0x1A: ("Body Slam", "normal", 85, 100),
    0x26: ("Earthquake", "ground", 100, 100),
    0x00: ("(No move)", "none", 0, 0),
}


def load_type_chart():
    """Load type effectiveness chart from JSON."""
    if TYPE_CHART_PATH.exists():
        with open(TYPE_CHART_PATH) as f:
            return json.load(f)
    # Fallback: minimal chart
    return {
        "fire": {"grass": 2.0, "water": 0.5, "fire": 0.5, "ice": 2.0},
        "water": {"fire": 2.0, "grass": 0.5, "water": 0.5, "ground": 2.0, "rock": 2.0},
        "grass": {"water": 2.0, "fire": 0.5, "grass": 0.5, "ground": 2.0, "rock": 2.0},
        "electric": {"water": 2.0, "grass": 0.5, "electric": 0.5, "ground": 0.0, "flying": 2.0},
        "ground": {"fire": 2.0, "electric": 2.0, "grass": 0.5, "flying": 0.0, "rock": 2.0},
        "ice": {"grass": 2.0, "ground": 2.0, "flying": 2.0, "dragon": 2.0, "fire": 0.5},
        "psychic": {"fighting": 2.0, "poison": 2.0, "psychic": 0.5},
        "normal": {"rock": 0.5, "ghost": 0.0},
    }


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

class GameController:
    """Send inputs to PyBoy with proper frame timing."""

    def __init__(self, pyboy: PyBoy):
        self.pyboy = pyboy

    def press(self, button: str, hold_frames: int = 20, release_frames: int = 10):
        """Press and release a button with frame advance.

        Uses pyboy.button() which handles press+hold+release internally.
        button_press()/button_release() do not work reliably in headless mode.
        """
        self.pyboy.button(button, delay=hold_frames)
        for _ in range(release_frames):
            self.pyboy.tick()

    def wait(self, frames: int = 30):
        """Advance N frames without input."""
        for _ in range(frames):
            self.pyboy.tick()

    def move(self, direction: str):
        """Move a single tile in the overworld."""
        self.press(direction, hold_frames=20, release_frames=8)
        self.wait(30)

    def mash_a(self, times: int = 5, delay: int = 20):
        """Mash A to advance text boxes."""
        for _ in range(times):
            self.press("a")
            self.wait(delay)

    def navigate_menu(self, target_index: int, current_index: int = 0):
        """Move cursor to a menu item (assumes vertical menu)."""
        diff = target_index - current_index
        direction = "down" if diff > 0 else "up"
        for _ in range(abs(diff)):
            self.press(direction)
            self.wait(8)
        self.press("a")
        self.wait(20)


# ---------------------------------------------------------------------------
# Battle strategy
# ---------------------------------------------------------------------------

class BattleStrategy:
    """Heuristic-based battle decision engine."""

    def __init__(self, type_chart: dict):
        self.type_chart = type_chart

    def score_move(self, move_id: int, move_pp: int, enemy_type: str = "normal") -> float:
        """Score a move based on power, PP, and type effectiveness."""
        if move_pp <= 0:
            return -1.0
        if move_id not in MOVE_DATA:
            return 10.0  # Unknown move, give it a baseline

        name, move_type, power, accuracy = MOVE_DATA[move_id]
        if power == 0:
            return 1.0  # Status move — low priority for grinding

        effectiveness = 1.0
        if move_type in self.type_chart:
            effectiveness = self.type_chart[move_type].get(enemy_type, 1.0)

        return power * (accuracy / 100.0) * effectiveness

    def choose_action(self, battle: BattleState) -> dict:
        """
        Decide what to do in battle.

        Returns:
            {"action": "fight", "move_index": 0-3}
            {"action": "item", "item": "potion"}
            {"action": "switch", "slot": 1-5}
            {"action": "run"}
        """
        # Low HP — heal if wild battle
        hp_ratio = battle.player_hp / max(battle.player_max_hp, 1)
        if hp_ratio < 0.2 and battle.battle_type == 1:  # Wild
            return {"action": "run"}  # Safe option when low

        if hp_ratio < 0.25:
            return {"action": "item", "item": "potion"}

        # Score all moves and pick the best
        moves = [
            (i, self.score_move(battle.moves[i], battle.move_pp[i]))
            for i in range(4)
            if battle.moves[i] != 0x00
        ]

        if not moves or all(score < 0 for _, score in moves):
            # No PP left — Struggle will auto-trigger, just press FIGHT
            return {"action": "fight", "move_index": 0}

        best_index, best_score = max(moves, key=lambda x: x[1])
        return {"action": "fight", "move_index": best_index}


# ---------------------------------------------------------------------------
# Overworld navigation
# ---------------------------------------------------------------------------

class Navigator:
    """Simple overworld movement."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.current_waypoint = 0
        self.current_map = None

    def _add_direction(self, directions: list[str], direction: str | None):
        """Append a direction once while preserving order."""
        if direction and direction not in directions:
            directions.append(direction)

    def _direction_toward_target(
        self,
        state: OverworldState,
        target_x: int,
        target_y: int,
        axis_preference: str = "x",
        stuck_turns: int = 0,
    ) -> str | None:
        """Choose a movement direction and rotate alternatives when blocked."""
        horizontal = None
        vertical = None

        if state.x < target_x:
            horizontal = "right"
        elif state.x > target_x:
            horizontal = "left"

        if state.y < target_y:
            vertical = "down"
        elif state.y > target_y:
            vertical = "up"

        ordered: list[str] = []
        primary = [horizontal, vertical] if axis_preference == "x" else [vertical, horizontal]
        secondary = [vertical, horizontal] if axis_preference == "x" else [horizontal, vertical]

        for direction in primary:
            self._add_direction(ordered, direction)
        for direction in secondary:
            self._add_direction(ordered, direction)
        for direction in ("up", "right", "down", "left"):
            self._add_direction(ordered, direction)

        if not ordered:
            return None
        return ordered[stuck_turns % len(ordered)]

    def _try_astar(self, state: OverworldState, target_x: int, target_y: int, collision_grid: list) -> str | None:
        """Try A* pathfinding to target. Returns first direction or None."""
        screen_target_row = 4 + (target_y - state.y)
        screen_target_col = 4 + (target_x - state.x)
        if 0 <= screen_target_row < 9 and 0 <= screen_target_col < 10:
            result = astar_path(collision_grid, (4, 4), (screen_target_row, screen_target_col))
            if result["status"] in ("success", "partial") and result["directions"]:
                return result["directions"][0]
        return None

    def next_direction(self, state: OverworldState, turn: int = 0, stuck_turns: int = 0, collision_grid: list | None = None) -> str | None:
        """Get the next direction to move based on current position and route plan."""
        map_key = str(state.map_id)

        # Reset waypoint index on map change
        if map_key != self.current_map:
            self.current_map = map_key
            self.current_waypoint = 0

        special_target = EARLY_GAME_TARGETS.get(state.map_id)
        if special_target:
            target_x, target_y = special_target["target"]
            if collision_grid is not None:
                astar_dir = self._try_astar(state, target_x, target_y, collision_grid)
                if astar_dir is not None:
                    return astar_dir
            return self._direction_toward_target(
                state,
                target_x,
                target_y,
                axis_preference=special_target.get("axis", "x"),
                stuck_turns=stuck_turns,
            )

        if map_key not in self.routes:
            # No route data — cycle directions to explore and find exits
            directions = ["down", "right", "down", "left", "up", "down"]
            return directions[turn % len(directions)]

        route = self.routes[map_key]
        waypoints = route["waypoints"] if isinstance(route, dict) and "waypoints" in route else route
        if self.current_waypoint >= len(waypoints):
            return None  # Route complete

        target = waypoints[self.current_waypoint]
        tx, ty = target["x"], target["y"]

        if state.x == tx and state.y == ty:
            self.current_waypoint += 1
            return self.next_direction(state, turn=turn, stuck_turns=stuck_turns, collision_grid=collision_grid)

        if collision_grid is not None:
            astar_dir = self._try_astar(state, tx, ty, collision_grid)
            if astar_dir is not None:
                return astar_dir

        return self._direction_toward_target(state, tx, ty, stuck_turns=stuck_turns)


# ---------------------------------------------------------------------------
# Strategy engine
# ---------------------------------------------------------------------------


class StrategyEngine:
    """Controls intelligence level based on strategy tier."""

    STUCK_THRESHOLD = 10

    def __init__(self, tier: str, notes_path: str | None = None):
        self.tier = tier
        self.notes: MemoryFile | None = None
        if tier in ("medium", "high") and notes_path:
            self.notes = MemoryFile(notes_path)

    def should_call_llm(self, stuck_turns: int = 0, map_changed: bool = False) -> bool:
        """Determine if an LLM call should be made this turn."""
        if self.tier == "low":
            return False
        if self.tier == "high":
            return True
        # medium: call on triggers only
        return stuck_turns >= self.STUCK_THRESHOLD or map_changed


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

class PokemonAgent:
    """Autonomous Pokemon player."""

    def __init__(self, rom_path: str, strategy: str = "low", screenshots: bool = False):
        self.rom_path = rom_path
        self.pyboy = PyBoy(rom_path, window="null")
        self.controller = GameController(self.pyboy)
        self.memory = MemoryReader(self.pyboy)
        self.type_chart = load_type_chart()
        self.battle_strategy = BattleStrategy(self.type_chart)
        self.strategy_engine = StrategyEngine(
            strategy,
            notes_path=str(SCRIPT_DIR.parent / "notes.md") if strategy != "low" else None,
        )
        self.turn_count = 0
        self.battles_won = 0
        self.screenshots = screenshots
        self.last_overworld_state: OverworldState | None = None
        self.last_overworld_action: str | None = None
        self.stuck_turns = 0
        self.recent_positions: list[tuple[int, int, int]] = []
        self.maps_visited: set[int] = set()
        self.events: list[str] = []
        self.collision_map = CollisionMap()

        # Screenshot output directory
        self.frames_dir = SCRIPT_DIR.parent / "frames"
        if self.screenshots:
            self.frames_dir.mkdir(parents=True, exist_ok=True)

        # Pokedex log directory
        self.pokedex_dir = SCRIPT_DIR.parent / "pokedex"
        self.pokedex_dir.mkdir(parents=True, exist_ok=True)

        # Load routes
        routes = {}
        if ROUTES_PATH.exists():
            with open(ROUTES_PATH) as f:
                routes = json.load(f)
        self.navigator = Navigator(routes)

        print(f"[agent] Loaded ROM: {rom_path}")
        print(f"[agent] Strategy: {strategy}")
        print(f"[agent] Running headless — no display")

    def update_overworld_progress(self, state: OverworldState):
        """Track whether the last overworld action moved the player."""
        pos = (state.map_id, state.x, state.y)

        self.maps_visited.add(state.map_id)

        if self.last_overworld_state is None:
            self.recent_positions.append(pos)
            return

        if state.map_id != self.last_overworld_state.map_id:
            self.stuck_turns = 0
            self.recent_positions.clear()
            self.recent_positions.append(pos)
            self.log(
                f"MAP CHANGE | {self.last_overworld_state.map_id} -> {state.map_id} | "
                f"Pos: ({state.x}, {state.y})"
            )
            return

        # Detect oscillation: if current position was visited recently,
        # increment stuck counter so the navigator tries alternate directions.
        if pos in self.recent_positions:
            self.stuck_turns += 1
        else:
            self.stuck_turns = 0

        self.recent_positions.append(pos)
        if len(self.recent_positions) > 8:
            self.recent_positions.pop(0)

        if self.stuck_turns in {2, 5, 10}:
            self.log(
                f"STUCK | Map: {state.map_id} | Pos: ({state.x}, {state.y}) | "
                f"Last move: {self.last_overworld_action} | Streak: {self.stuck_turns}"
            )

    def choose_overworld_action(self, state: OverworldState) -> str:
        """Pick the next overworld action."""
        if state.text_box_active:
            return "a"

        # After Oak escorts the player into the lab, stay in interaction mode
        # until the scripted intro there finishes.
        if state.map_id == 40 and state.party_count == 0:
            return "a"

        direction = self.navigator.next_direction(
            state,
            turn=self.turn_count,
            stuck_turns=self.stuck_turns,
            collision_grid=self.collision_map.grid,
        )
        return direction or "a"

    def log(self, msg: str):
        """Structured log line for Tapes to capture."""
        timestamp = time.strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        print(line, flush=True)
        self.events.append(line)

    def write_pokedex_entry(self):
        """Write a session summary to the pokedex directory."""
        final_state = self.memory.read_overworld_state()
        timestamp = time.strftime("%Y-%m-%d_%H%M%S")

        # Find next log number
        existing = list(self.pokedex_dir.glob("log*.md"))
        next_num = len(existing) + 1
        path = self.pokedex_dir / f"log{next_num}.md"

        # Count notable events
        map_changes = [e for e in self.events if "MAP CHANGE" in e]
        battles = [e for e in self.events if "BATTLE" in e]
        stuck_events = [e for e in self.events if "STUCK" in e]

        lines = [
            f"# Log {next_num}: Session {timestamp}",
            "",
            "## Summary",
            "",
            f"- **Turns:** {self.turn_count}",
            f"- **Battles won:** {self.battles_won}",
            f"- **Maps visited:** {len(self.maps_visited)} ({', '.join(str(m) for m in sorted(self.maps_visited))})",
            f"- **Final position:** Map {final_state.map_id} ({final_state.x}, {final_state.y})",
            f"- **Badges:** {final_state.badges}",
            f"- **Party size:** {final_state.party_count}",
            f"- **Strategy:** {self.battle_strategy.__class__.__name__}",
            "",
            "## Stats",
            "",
            f"- Map changes: {len(map_changes)}",
            f"- Battle turns: {len(battles)}",
            f"- Stuck events: {len(stuck_events)}",
            "",
            "## Event Log",
            "",
        ]

        for event in self.events:
            lines.append(f"    {event}")

        lines.append("")
        path.write_text("\n".join(lines))
        self.log(f"POKEDEX | Wrote {path}")

    def take_screenshot(self):
        """Save current frame as turn{N}.png."""
        if not self.screenshots or Image is None:
            return
        path = self.frames_dir / f"turn{self.turn_count}.png"
        img = Image.fromarray(self.pyboy.screen.ndarray)
        img.save(path)
        self.log(f"SCREENSHOT | {path}")

    def run_battle_turn(self):
        """Execute one battle turn."""
        battle = self.memory.read_battle_state()
        action = self.battle_strategy.choose_action(battle)

        self.log(
            f"BATTLE | Player HP: {battle.player_hp}/{battle.player_max_hp} | "
            f"Enemy HP: {battle.enemy_hp}/{battle.enemy_max_hp} | "
            f"Action: {action}"
        )

        if action["action"] == "fight":
            # Navigate to FIGHT menu
            self.controller.press("a")  # Select FIGHT
            self.controller.wait(20)
            # Select move
            self.controller.navigate_menu(action["move_index"])
            self.controller.wait(60)  # Wait for attack animation
            self.controller.mash_a(3)  # Clear text boxes

        elif action["action"] == "run":
            # Navigate to RUN (index 3 in battle menu)
            self.controller.navigate_menu(3)
            self.controller.wait(40)
            self.controller.mash_a(3)

        elif action["action"] == "item":
            # Navigate to BAG (index 1 in battle menu)
            self.controller.navigate_menu(1)
            self.controller.wait(20)
            # Select first healing item (simplified)
            self.controller.press("a")
            self.controller.wait(40)
            self.controller.mash_a(3)

        elif action["action"] == "switch":
            # Navigate to POKEMON (index 2 in battle menu)
            self.controller.navigate_menu(2)
            self.controller.wait(20)
            self.controller.navigate_menu(action.get("slot", 1))
            self.controller.wait(40)
            self.controller.mash_a(3)

        self.turn_count += 1

    def run_overworld(self):
        """Move in the overworld."""
        state = self.memory.read_overworld_state()
        self.update_overworld_progress(state)
        try:
            self.collision_map.update(self.pyboy)
        except Exception:
            pass  # game_wrapper may not be available in all contexts
        action = self.choose_overworld_action(state)

        if action in {"up", "down", "left", "right"}:
            self.controller.move(action)
        else:
            self.controller.press("a", hold_frames=20, release_frames=12)
            self.controller.wait(24)

        # Log position every 100 steps
        if self.turn_count % 100 == 0:
            self.log(
                f"OVERWORLD | Map: {state.map_id} | "
                f"Pos: ({state.x}, {state.y}) | "
                f"Badges: {state.badges} | "
                f"Party: {state.party_count} | "
                f"Action: {action} | "
                f"Stuck: {self.stuck_turns}"
            )

        self.last_overworld_state = state
        self.last_overworld_action = action

    def run(self, max_turns: int = 100_000):
        """Main agent loop."""
        self.log("Agent starting. Advancing through intro...")

        # Advance through title screen (needs ~1500 frames to reach "Press Start")
        self.controller.wait(1500)
        self.controller.press("start")
        self.controller.wait(60)

        # Mash through Oak's entire intro, name selection, rival naming.
        # Need long frame waits — the game has slow text scroll and animations.
        # This takes ~600 A presses with proper wait times.
        for i in range(600):
            self.controller.press("a")
            self.controller.wait(30)  # Longer waits for text to scroll

        self.log("Intro complete. Entering game loop.")

        for _ in range(max_turns):
            battle = self.memory.read_battle_state()

            if battle.battle_type > 0:
                self.run_battle_turn()

                # Check if battle ended
                self.controller.wait(10)
                new_battle = self.memory.read_battle_state()
                if new_battle.battle_type == 0:
                    self.battles_won += 1
                    self.log(f"Battle ended. Total wins: {self.battles_won}")
            else:
                self.run_overworld()
                self.turn_count += 1

            if self.turn_count % 10 == 0:
                self.take_screenshot()

        self.log(f"Session complete. Turns: {self.turn_count} | Wins: {self.battles_won}")
        self.write_pokedex_entry()
        try:
            self.pyboy.stop()
        except PermissionError:
            pass  # ROM save file write fails on read-only mounts


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pokemon Agent — autonomous RPG player")
    parser.add_argument("rom", help="Path to ROM file (.gb or .gbc)")
    parser.add_argument(
        "--strategy",
        choices=["low", "medium", "high"],
        default="low",
        help="Decision strategy (default: low)",
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=100_000,
        help="Maximum turns before stopping (default: 100000)",
    )
    parser.add_argument(
        "--save-screenshots",
        action="store_true",
        help="Save periodic screenshots to ./frames/",
    )
    args = parser.parse_args()

    if not Path(args.rom).exists():
        print(f"ROM not found: {args.rom}")
        sys.exit(1)

    agent = PokemonAgent(args.rom, strategy=args.strategy, screenshots=args.save_screenshots)
    agent.run(max_turns=args.max_turns)


if __name__ == "__main__":
    main()
