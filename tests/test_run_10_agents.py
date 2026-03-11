"""Tests for run_10_agents.py — 100% coverage."""

import json
import runpy
import subprocess as sp
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import run_10_agents as mod
from run_10_agents import (
    PARAM_VARIANTS,
    main,
    run_one_agent,
    score,  # re-exported from evolve
)

# ── PARAM_VARIANTS validation ────────────────────────────────────────


class TestParamVariants:
    def test_has_16_variants(self):
        assert len(PARAM_VARIANTS) == 16

    def test_all_variants_have_required_keys(self):
        required = {
            "stuck_threshold",
            "door_cooldown",
            "waypoint_skip_distance",
            "axis_preference_map_0",
            "label",
            "bt_max_snapshots",
            "bt_restore_threshold",
            "bt_max_attempts",
            "bt_snapshot_interval",
        }
        for i, variant in enumerate(PARAM_VARIANTS):
            missing = required - set(variant.keys())
            assert not missing, f"Variant {i} ({variant.get('label', '?')}) missing: {missing}"

    def test_labels_unique(self):
        labels = [v["label"] for v in PARAM_VARIANTS]
        assert len(labels) == len(set(labels)), "Duplicate labels found"


# ── score() ───────────────────────────────────────────────────────────


class TestScore:
    def test_zero_fitness(self):
        assert score({}) == 0.0

    def test_positive_score(self):
        f = {
            "final_map_id": 1,
            "badges": 1,
            "party_size": 1,
            "battles_won": 5,
            "stuck_count": 2,
            "turns": 100,
        }
        expected = 1000 + 5000 + 500 + 500 - 10 - 10.0
        assert score(f) == expected

    def test_stuck_penalizes(self):
        base = {"final_map_id": 1}
        stuck = {"final_map_id": 1, "stuck_count": 100}
        assert score(stuck) < score(base)


# ── run_one_agent() ───────────────────────────────────────────────────


class TestRunOneAgent:
    def _make_fitness(self, **overrides):
        f = {"final_map_id": 1, "badges": 0, "party_size": 1, "battles_won": 3, "stuck_count": 2, "turns": 50}
        f.update(overrides)
        return f

    def test_success(self):
        fitness = self._make_fitness()

        def mock_run(cmd, env=None, capture_output=False, text=False, timeout=None):
            output_path = cmd[cmd.index("--output-json") + 1]
            Path(output_path).write_text(json.dumps(fitness))
            return MagicMock(returncode=0)

        params = {
            "stuck_threshold": 8,
            "door_cooldown": 4,
            "waypoint_skip_distance": 3,
            "axis_preference_map_0": "y",
            "label": "test_label",
        }

        with patch("run_10_agents.subprocess.run", side_effect=mock_run):
            result = run_one_agent("/fake/rom.gb", params, 0)

        assert result["agent_id"] == 0
        assert result["label"] == "test_label"
        assert result["fitness"] == fitness
        assert result["score"] == score(fitness)
        assert result["returncode"] == 0
        assert "error" not in result
        # label should be stripped from params passed to agent
        assert "label" not in result["params"]

    def test_label_defaults_to_agent_id(self):
        fitness = self._make_fitness()

        def mock_run(cmd, env=None, capture_output=False, text=False, timeout=None):
            output_path = cmd[cmd.index("--output-json") + 1]
            Path(output_path).write_text(json.dumps(fitness))
            return MagicMock(returncode=0)

        params = {"stuck_threshold": 8, "door_cooldown": 4, "waypoint_skip_distance": 3, "axis_preference_map_0": "y"}

        with patch("run_10_agents.subprocess.run", side_effect=mock_run):
            result = run_one_agent("/fake/rom.gb", params, 7)

        assert result["label"] == "agent_7"

    def test_timeout_returns_error(self):
        params = {"stuck_threshold": 8, "label": "timeout_test"}

        with patch("run_10_agents.subprocess.run", side_effect=sp.TimeoutExpired("cmd", 300)):
            result = run_one_agent("/fake/rom.gb", params, 1)

        assert result["score"] == -999
        assert result["fitness"] == {}
        assert "error" in result

    def test_file_not_found_returns_error(self):
        params = {"stuck_threshold": 8, "label": "fnf_test"}

        with patch("run_10_agents.subprocess.run", side_effect=FileNotFoundError("no python")):
            result = run_one_agent("/fake/rom.gb", params, 2)

        assert result["score"] == -999
        assert "error" in result

    def test_invalid_json_returns_error(self):
        params = {"stuck_threshold": 8, "label": "bad_json"}

        def mock_run(cmd, env=None, capture_output=False, text=False, timeout=None):
            output_path = cmd[cmd.index("--output-json") + 1]
            Path(output_path).write_text("not json")
            return MagicMock(returncode=0)

        with patch("run_10_agents.subprocess.run", side_effect=mock_run):
            result = run_one_agent("/fake/rom.gb", params, 3)

        assert result["score"] == -999
        assert "error" in result

    def test_params_passed_as_env(self):
        fitness = self._make_fitness()
        captured_env = {}

        def mock_run(cmd, env=None, capture_output=False, text=False, timeout=None):
            captured_env.update(env or {})
            output_path = cmd[cmd.index("--output-json") + 1]
            Path(output_path).write_text(json.dumps(fitness))
            return MagicMock(returncode=0)

        params = {"stuck_threshold": 10, "door_cooldown": 6, "label": "env_test"}

        with patch("run_10_agents.subprocess.run", side_effect=mock_run):
            run_one_agent("/fake/rom.gb", params, 0)

        assert "EVOLVE_PARAMS" in captured_env
        parsed = json.loads(captured_env["EVOLVE_PARAMS"])
        assert parsed == {"stuck_threshold": 10, "door_cooldown": 6}
        assert "label" not in parsed

    def test_cleanup_unlink_oserror_ignored(self):
        fitness = self._make_fitness()

        def mock_run(cmd, env=None, capture_output=False, text=False, timeout=None):
            output_path = cmd[cmd.index("--output-json") + 1]
            Path(output_path).write_text(json.dumps(fitness))
            return MagicMock(returncode=0)

        params = {"stuck_threshold": 8, "label": "cleanup_test"}

        with (
            patch("run_10_agents.subprocess.run", side_effect=mock_run),
            patch("run_10_agents.os.unlink", side_effect=OSError("perm")),
        ):
            result = run_one_agent("/fake/rom.gb", params, 0)

        assert result["fitness"] == fitness


# ── main() ────────────────────────────────────────────────────────────


class TestMain:
    def test_no_args_exits(self, capsys):
        with patch("sys.argv", ["run_10_agents.py"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
        assert "Usage" in capsys.readouterr().out

    def test_rom_not_found_exits(self, capsys):
        with patch("sys.argv", ["run_10_agents.py", "/nonexistent/rom.gb"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1
        assert "ROM not found" in capsys.readouterr().out

    def test_full_run(self, tmp_path, capsys):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 100)

        fake_result = {
            "agent_id": 0,
            "label": "test",
            "params": {},
            "fitness": {
                "final_map_id": 1,
                "badges": 0,
                "party_size": 1,
                "battles_won": 3,
                "stuck_count": 2,
                "turns": 50,
            },
            "score": 1530.0,
            "elapsed": 1.0,
            "returncode": 0,
        }

        def mock_run_one_agent(rom_path, params, agent_id):
            return dict(fake_result, agent_id=agent_id, label=params.get("label", f"agent_{agent_id}"))

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        with (
            patch("sys.argv", ["run_10_agents.py", str(rom)]),
            patch("run_10_agents.run_one_agent", side_effect=mock_run_one_agent),
            patch("run_10_agents.ProcessPoolExecutor", ThreadPoolExecutor),
            patch.object(mod, "SCRIPT_DIR", scripts_dir),
        ):
            main()

        output = capsys.readouterr().out
        assert "Winner:" in output
        assert "score=" in output

        saved = tmp_path / "pokedex" / "evolve_results.json"
        assert saved.exists()
        data = json.loads(saved.read_text())
        assert len(data) == len(PARAM_VARIANTS)

    def test_error_result_shows_fail(self, tmp_path, capsys):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 100)

        def mock_run_one_agent(rom_path, params, agent_id):
            return {
                "agent_id": agent_id,
                "label": params.get("label", f"agent_{agent_id}"),
                "params": {},
                "fitness": {},
                "score": -999,
                "elapsed": 0.5,
                "error": "timeout",
            }

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        with (
            patch("sys.argv", ["run_10_agents.py", str(rom)]),
            patch("run_10_agents.run_one_agent", side_effect=mock_run_one_agent),
            patch("run_10_agents.ProcessPoolExecutor", ThreadPoolExecutor),
            patch.object(mod, "SCRIPT_DIR", scripts_dir),
        ):
            main()

        output = capsys.readouterr().out
        assert "[FAIL]" in output


# ── __main__ guard ────────────────────────────────────────────────────


class TestMainGuard:
    def test_dunder_main_calls_main(self, tmp_path):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 100)

        fake_result = {
            "agent_id": 0,
            "label": "test",
            "params": {},
            "fitness": {"final_map_id": 0},
            "score": 0.0,
            "elapsed": 0.1,
            "returncode": 0,
        }

        def mock_run_one_agent(rom_path, params, agent_id):
            return dict(fake_result, agent_id=agent_id, label=params.get("label", f"agent_{agent_id}"))

        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()

        with (
            patch("sys.argv", ["run_10_agents.py", str(rom)]),
            patch("run_10_agents.run_one_agent", side_effect=mock_run_one_agent),
            patch("run_10_agents.ProcessPoolExecutor", ThreadPoolExecutor),
            patch.object(mod, "SCRIPT_DIR", scripts_dir),
        ):
            runpy.run_path(
                str(Path(mod.__file__).resolve()),
                run_name="__main__",
            )
