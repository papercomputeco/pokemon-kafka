"""Tests for evolve.py — 100% coverage."""

import json
import os
import runpy
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import evolve as evolve_mod
from evolve import (
    DEFAULT_PARAMS,
    EvolutionResult,
    score,
    run_agent,
    build_mutation_prompt,
    parse_llm_response,
    evolve,
    _perturb,
    main,
)


# ── EvolutionResult dataclass ──────────────────────────────────────────


class TestEvolutionResult:
    def test_defaults(self):
        r = EvolutionResult()
        assert r.generation == 0
        assert r.params == {}
        assert r.fitness == {}
        assert r.score == 0.0
        assert r.improved is False


# ── DEFAULT_PARAMS ─────────────────────────────────────────────────────


class TestDefaultParams:
    def test_keys(self):
        assert "stuck_threshold" in DEFAULT_PARAMS
        assert "door_cooldown" in DEFAULT_PARAMS
        assert "waypoint_skip_distance" in DEFAULT_PARAMS
        assert "axis_preference_map_0" in DEFAULT_PARAMS
        assert "bt_max_snapshots" in DEFAULT_PARAMS
        assert "bt_restore_threshold" in DEFAULT_PARAMS
        assert "bt_max_attempts" in DEFAULT_PARAMS
        assert "bt_snapshot_interval" in DEFAULT_PARAMS


# ── score() ────────────────────────────────────────────────────────────


class TestScore:
    def test_zero_fitness(self):
        f = {
            "final_map_id": 0,
            "badges": 0,
            "party_size": 0,
            "battles_won": 0,
            "stuck_count": 0,
            "turns": 0,
        }
        assert score(f) == 0.0

    def test_positive_score(self):
        f = {
            "final_map_id": 1,
            "badges": 1,
            "party_size": 1,
            "battles_won": 5,
            "stuck_count": 2,
            "turns": 100,
        }
        # 1*1000 + 1*5000 + 1*500 + 5*10 - 2*5 - 100*0.1
        expected = 1000 + 5000 + 500 + 50 - 10 - 10.0
        assert score(f) == expected

    def test_missing_keys_default_zero(self):
        assert score({}) == 0.0

    def test_high_stuck_penalizes(self):
        base = {"final_map_id": 1, "badges": 0, "party_size": 0,
                "battles_won": 0, "stuck_count": 0, "turns": 0}
        stuck = dict(base, stuck_count=100)
        assert score(stuck) < score(base)

    def test_backtrack_restores_penalizes(self):
        base = {"final_map_id": 1, "badges": 0, "party_size": 0,
                "battles_won": 0, "stuck_count": 0, "turns": 0,
                "backtrack_restores": 0}
        with_bt = dict(base, backtrack_restores=10)
        assert score(with_bt) < score(base)
        # Penalty is -2 per restore
        assert score(base) - score(with_bt) == 20


# ── run_agent() ────────────────────────────────────────────────────────


class TestRunAgent:
    def test_success(self, tmp_path):
        fitness = {"turns": 50, "battles_won": 3, "maps_visited": 2,
                   "final_map_id": 1, "final_x": 5, "final_y": 10,
                   "badges": 0, "party_size": 1, "stuck_count": 2}

        # Mock subprocess to write fitness JSON
        def mock_run(cmd, env=None, capture_output=False, timeout=None):
            output_path = cmd[cmd.index("--output-json") + 1]
            Path(output_path).write_text(json.dumps(fitness))
            return MagicMock(returncode=0)

        with patch("evolve.subprocess.run", side_effect=mock_run):
            result = run_agent("/fake/rom.gb", 200, DEFAULT_PARAMS)

        assert result["turns"] == 50
        assert result["battles_won"] == 3

    def test_timeout_returns_fallback(self):
        import subprocess as sp

        with patch("evolve.subprocess.run", side_effect=sp.TimeoutExpired("cmd", 600)):
            result = run_agent("/fake/rom.gb", 200, DEFAULT_PARAMS)

        assert result["stuck_count"] == 200
        assert result["battles_won"] == 0

    def test_missing_output_returns_fallback(self):
        with patch("evolve.subprocess.run"):
            # subprocess.run completes but output file doesn't exist
            result = run_agent("/fake/rom.gb", 100, DEFAULT_PARAMS)

        assert result["turns"] == 100

    def test_invalid_json_returns_fallback(self, tmp_path):
        def mock_run(cmd, env=None, capture_output=False, timeout=None):
            output_path = cmd[cmd.index("--output-json") + 1]
            Path(output_path).write_text("not json")
            return MagicMock(returncode=0)

        with patch("evolve.subprocess.run", side_effect=mock_run):
            result = run_agent("/fake/rom.gb", 100, DEFAULT_PARAMS)

        assert result["battles_won"] == 0

    def test_unlink_oserror_ignored(self):
        """Lines 108-109: OSError on cleanup is silently ignored."""
        def mock_run(cmd, env=None, capture_output=False, timeout=None):
            output_path = cmd[cmd.index("--output-json") + 1]
            Path(output_path).write_text(json.dumps({
                "turns": 1, "battles_won": 0, "maps_visited": 0,
                "final_map_id": 0, "final_x": 0, "final_y": 0,
                "badges": 0, "party_size": 0, "stuck_count": 0}))
            return MagicMock(returncode=0)

        with patch("evolve.subprocess.run", side_effect=mock_run), \
             patch("evolve.os.unlink", side_effect=OSError("perm denied")):
            result = run_agent("/fake/rom.gb", 100, DEFAULT_PARAMS)

        assert result["turns"] == 1

    def test_params_passed_as_env(self, tmp_path):
        captured_env = {}

        def mock_run(cmd, env=None, capture_output=False, timeout=None):
            captured_env.update(env or {})
            output_path = cmd[cmd.index("--output-json") + 1]
            Path(output_path).write_text(json.dumps({"turns": 1, "battles_won": 0,
                "maps_visited": 0, "final_map_id": 0, "final_x": 0, "final_y": 0,
                "badges": 0, "party_size": 0, "stuck_count": 0}))
            return MagicMock(returncode=0)

        params = {"stuck_threshold": 10, "door_cooldown": 6,
                  "waypoint_skip_distance": 5, "axis_preference_map_0": "x"}

        with patch("evolve.subprocess.run", side_effect=mock_run):
            run_agent("/fake/rom.gb", 100, params)

        assert "EVOLVE_PARAMS" in captured_env
        assert json.loads(captured_env["EVOLVE_PARAMS"]) == params


# ── build_mutation_prompt() ────────────────────────────────────────────


class TestBuildMutationPrompt:
    def test_includes_params_and_fitness(self):
        prompt = build_mutation_prompt(DEFAULT_PARAMS, {"turns": 100, "badges": 0})
        assert "stuck_threshold" in prompt
        assert '"turns": 100' in prompt

    def test_includes_bt_descriptions(self):
        prompt = build_mutation_prompt(DEFAULT_PARAMS, {})
        assert "bt_max_snapshots" in prompt
        assert "bt_restore_threshold" in prompt
        assert "bt_max_attempts" in prompt
        assert "bt_snapshot_interval" in prompt

    def test_includes_observations(self):
        obs = [{"priority": "important", "content": "Tool error: boom"}]
        prompt = build_mutation_prompt(DEFAULT_PARAMS, {}, obs)
        assert "Tool error: boom" in prompt
        assert "[important]" in prompt

    def test_no_observations(self):
        prompt = build_mutation_prompt(DEFAULT_PARAMS, {})
        assert "observations" not in prompt.lower() or "Recent" not in prompt


# ── parse_llm_response() ──────────────────────────────────────────────


class TestParseLlmResponse:
    def test_valid_json(self):
        resp = json.dumps(DEFAULT_PARAMS)
        assert parse_llm_response(resp) == DEFAULT_PARAMS

    def test_json_with_code_fences(self):
        resp = f"```json\n{json.dumps(DEFAULT_PARAMS)}\n```"
        assert parse_llm_response(resp) == DEFAULT_PARAMS

    def test_invalid_json(self):
        assert parse_llm_response("not json at all") is None

    def test_missing_keys(self):
        assert parse_llm_response('{"stuck_threshold": 5}') is None

    def test_extra_whitespace(self):
        resp = f"  \n{json.dumps(DEFAULT_PARAMS)}\n  "
        assert parse_llm_response(resp) == DEFAULT_PARAMS


# ── _perturb() ─────────────────────────────────────────────────────────


class TestPerturb:
    def test_returns_dict_with_same_keys(self):
        result = _perturb(DEFAULT_PARAMS)
        assert set(result.keys()) == set(DEFAULT_PARAMS.keys())

    def test_at_least_one_value_differs(self):
        """Over many runs, perturbation should change something."""
        import random
        random.seed(42)
        diffs = 0
        for _ in range(20):
            result = _perturb(DEFAULT_PARAMS)
            if result != DEFAULT_PARAMS:
                diffs += 1
        assert diffs > 0

    def test_minimum_value_clamp(self):
        """Numeric params should never go below 1."""
        import random
        random.seed(0)
        params = dict(DEFAULT_PARAMS, stuck_threshold=1, door_cooldown=1,
                      waypoint_skip_distance=1, bt_max_snapshots=1,
                      bt_restore_threshold=1, bt_max_attempts=1,
                      bt_snapshot_interval=1)
        for _ in range(50):
            result = _perturb(params)
            for key in ("stuck_threshold", "door_cooldown", "waypoint_skip_distance",
                        "bt_max_snapshots", "bt_restore_threshold",
                        "bt_max_attempts", "bt_snapshot_interval"):
                assert result[key] >= 1

    def test_can_perturb_bt_keys(self):
        """bt_* keys should be reachable by perturbation."""
        import random
        random.seed(123)
        bt_changed = set()
        for _ in range(200):
            result = _perturb(DEFAULT_PARAMS)
            for key in ("bt_max_snapshots", "bt_restore_threshold",
                        "bt_max_attempts", "bt_snapshot_interval"):
                if result[key] != DEFAULT_PARAMS[key]:
                    bt_changed.add(key)
        assert len(bt_changed) > 0


# ── evolve() ───────────────────────────────────────────────────────────


class TestEvolve:
    def _mock_run_agent(self, fitness_seq):
        """Return a patched run_agent that yields fitness dicts from a sequence."""
        call_count = {"n": 0}

        def mock_fn(rom, turns, params):
            idx = min(call_count["n"], len(fitness_seq) - 1)
            call_count["n"] += 1
            return fitness_seq[idx]

        return mock_fn

    def test_basic_evolution_no_llm(self):
        baseline = {"final_map_id": 0, "badges": 0, "party_size": 1,
                    "battles_won": 0, "stuck_count": 5, "turns": 100}
        improved = {"final_map_id": 1, "badges": 0, "party_size": 1,
                    "battles_won": 2, "stuck_count": 1, "turns": 80}

        # baseline run, then gen1 variant (improved)
        mock_run = self._mock_run_agent([baseline, improved])

        with patch("evolve.run_agent", side_effect=mock_run):
            results = evolve("/fake.gb", max_generations=1, max_turns=100)

        assert len(results) == 1
        assert results[0].improved is True

    def test_no_improvement(self):
        good = {"final_map_id": 1, "badges": 0, "party_size": 1,
                "battles_won": 5, "stuck_count": 0, "turns": 50}
        worse = {"final_map_id": 0, "badges": 0, "party_size": 0,
                 "battles_won": 0, "stuck_count": 10, "turns": 200}

        mock_run = self._mock_run_agent([good, worse])

        with patch("evolve.run_agent", side_effect=mock_run):
            results = evolve("/fake.gb", max_generations=1, max_turns=100)

        assert len(results) == 1
        assert results[0].improved is False

    def test_with_llm_fn(self):
        baseline = {"final_map_id": 0, "badges": 0, "party_size": 1,
                    "battles_won": 0, "stuck_count": 5, "turns": 100}
        improved = {"final_map_id": 1, "badges": 0, "party_size": 1,
                    "battles_won": 2, "stuck_count": 1, "turns": 80}

        variant_params = dict(DEFAULT_PARAMS, stuck_threshold=5)
        llm_fn = MagicMock(return_value=json.dumps(variant_params))
        mock_run = self._mock_run_agent([baseline, improved])

        with patch("evolve.run_agent", side_effect=mock_run):
            results = evolve("/fake.gb", max_generations=1, max_turns=100,
                             llm_fn=llm_fn)

        assert llm_fn.called
        assert results[0].improved is True

    def test_llm_invalid_response_skips(self):
        baseline = {"final_map_id": 0, "badges": 0, "party_size": 1,
                    "battles_won": 0, "stuck_count": 5, "turns": 100}

        llm_fn = MagicMock(return_value="garbage response")
        mock_run = self._mock_run_agent([baseline])

        with patch("evolve.run_agent", side_effect=mock_run):
            results = evolve("/fake.gb", max_generations=1, max_turns=100,
                             llm_fn=llm_fn)

        assert len(results) == 1
        assert results[0].improved is False

    def test_with_observer_fn(self):
        baseline = {"final_map_id": 0, "badges": 0, "party_size": 1,
                    "battles_won": 0, "stuck_count": 5, "turns": 100}
        variant = {"final_map_id": 0, "badges": 0, "party_size": 1,
                   "battles_won": 0, "stuck_count": 3, "turns": 100}

        obs = [{"priority": "important", "content": "Stuck at map 0"}]
        observer_fn = MagicMock(return_value=obs)

        variant_params = dict(DEFAULT_PARAMS, stuck_threshold=5)
        llm_fn = MagicMock(return_value=json.dumps(variant_params))
        mock_run = self._mock_run_agent([baseline, variant])

        with patch("evolve.run_agent", side_effect=mock_run):
            evolve("/fake.gb", max_generations=1, max_turns=100,
                   llm_fn=llm_fn, observer_fn=observer_fn)

        # Observer was called
        assert observer_fn.called
        # LLM prompt should include observations
        prompt_arg = llm_fn.call_args[0][0]
        assert "Stuck at map 0" in prompt_arg

    def test_multiple_generations(self):
        fitness_seq = [
            {"final_map_id": 0, "badges": 0, "party_size": 1,
             "battles_won": 0, "stuck_count": 5, "turns": 100},  # baseline
            {"final_map_id": 1, "badges": 0, "party_size": 1,
             "battles_won": 2, "stuck_count": 1, "turns": 80},   # gen1 (better)
            {"final_map_id": 0, "badges": 0, "party_size": 1,
             "battles_won": 0, "stuck_count": 8, "turns": 150},  # gen2 (worse)
        ]

        mock_run = self._mock_run_agent(fitness_seq)

        with patch("evolve.run_agent", side_effect=mock_run):
            results = evolve("/fake.gb", max_generations=2, max_turns=100)

        assert len(results) == 2
        assert results[0].improved is True
        assert results[1].improved is False


# ── main() CLI ─────────────────────────────────────────────────────────


class TestMain:
    def test_rom_not_found(self):
        with patch("sys.argv", ["evolve.py", "/nonexistent/rom.gb"]):
            with pytest.raises(SystemExit) as exc:
                main()
            assert exc.value.code == 1

    def test_runs_evolution(self, tmp_path):
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 100)

        baseline = {"final_map_id": 0, "badges": 0, "party_size": 0,
                    "battles_won": 0, "stuck_count": 0, "turns": 10}

        with patch("sys.argv", ["evolve.py", str(rom), "--generations", "1",
                                "--max-turns", "10"]):
            with patch("evolve.evolve", return_value=[
                EvolutionResult(generation=1, improved=False)
            ]) as mock_evolve:
                main()

        mock_evolve.assert_called_once_with(
            str(rom), max_generations=1, max_turns=10
        )


# ── __main__ guard ─────────────────────────────────────────────────────


class TestMainGuard:
    def test_dunder_main_calls_main(self, tmp_path):
        """Line 316: if __name__ == '__main__': main()"""
        rom = tmp_path / "test.gb"
        rom.write_bytes(b"\x00" * 100)

        with patch("sys.argv", ["evolve.py", str(rom), "--generations", "1",
                                "--max-turns", "1"]), \
             patch("evolve.evolve", return_value=[
                 EvolutionResult(generation=1, improved=False)
             ]):
            runpy.run_path(
                str(Path(evolve_mod.__file__).resolve()),
                run_name="__main__",
            )
