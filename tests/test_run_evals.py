import json

import run_evals


def _case(tmp_path, name="c1", **over):
    c = {
        "name": name,
        "learning": "docs/learnings/x.md",
        "category": "battle",
        "seed_state": "seed.state",
        "stop_on_map": 51,
        "max_turns": 100,
        "genome": {"door_cooldown": 9},
        "pass": {"final_map_id": 51, "min_lead_hp": 5},
    }
    c.update(over)
    d = tmp_path / "cases"
    d.mkdir(exist_ok=True)
    (d / f"{name}.json").write_text(json.dumps(c))
    return c


def test_load_cases_reads_all_or_one(tmp_path):
    _case(tmp_path, "a")
    _case(tmp_path, "b")
    assert [c["name"] for c in run_evals.load_cases(tmp_path / "cases")] == ["a", "b"]
    assert [c["name"] for c in run_evals.load_cases(tmp_path / "cases", only="b")] == ["b"]


def test_build_cmd_encodes_case(tmp_path):
    c = _case(tmp_path)
    cmd, env = run_evals.build_cmd("rom.gb", c, tmp_path / "out")
    assert cmd[:4] == ["uv", "run", "python", str(run_evals.AGENT)]
    assert "--load-state" in cmd and "seed.state" in cmd
    assert "--stop-on-map" in cmd and "51" in cmd
    assert "--max-turns" in cmd and "100" in cmd
    assert "--no-self-heal" in cmd and "--no-in-run-heal" in cmd
    assert json.loads(env["EVOLVE_PARAMS"]) == {"door_cooldown": 9}


def test_build_cmd_omits_evolve_params_for_empty_genome(tmp_path):
    c = _case(tmp_path, genome={})
    _cmd, env = run_evals.build_cmd("rom.gb", c, tmp_path / "out")
    assert "EVOLVE_PARAMS" not in env


def test_judge_pass_fail_and_expected_fail(tmp_path):
    c = _case(tmp_path)
    assert run_evals.judge(c, {"final_map_id": 51, "lead_hp": 9}) == "PASS"
    assert run_evals.judge(c, {"final_map_id": 51, "lead_hp": 1}) == "FAIL"
    assert run_evals.judge(c, {"final_map_id": 13, "lead_hp": 30}) == "FAIL"
    x = _case(tmp_path, "x", expected_fail=True)
    assert run_evals.judge(x, {"final_map_id": 13, "lead_hp": 0}) == "XFAIL"
    assert run_evals.judge(x, {"final_map_id": 51, "lead_hp": 9}) == "XPASS"
    assert run_evals.judge(c, {}) == "FAIL"


def test_run_case_uses_runner_and_reads_fitness(tmp_path, monkeypatch):
    c = _case(tmp_path)

    def fake_run(cmd, env, cwd, timeout):
        out = [a for a in cmd if a.endswith("fitness.json")][0]
        (tmp_path / "out").mkdir(exist_ok=True)
        open(out, "w").write(json.dumps({"final_map_id": 51, "lead_hp": 12, "turns": 77}))
        return 0

    row = run_evals.run_case("rom.gb", c, tmp_path / "out", runner=fake_run)
    assert row["verdict"] == "PASS" and row["turns"] == 77 and row["lead_hp"] == 12


def test_run_case_missing_fitness_is_fail(tmp_path):
    c = _case(tmp_path)
    row = run_evals.run_case("rom.gb", c, tmp_path / "out", runner=lambda *a, **k: 1)
    assert row["verdict"] == "FAIL" and row["turns"] is None


def test_main_dry_run_and_results_file(tmp_path, monkeypatch, capsys):
    _case(tmp_path, "a")
    rc = run_evals.main(["--cases", str(tmp_path / "cases"), "--dry-run", "--rom", "rom.gb"])
    assert rc == 0
    assert "--stop-on-map" in capsys.readouterr().out
    # real run path with a fake runner writes a dated results file
    monkeypatch.setattr(run_evals, "_default_runner", lambda cmd, env, cwd, timeout: 1)
    rc = run_evals.main(["--cases", str(tmp_path / "cases"), "--rom", "rom.gb", "--results-dir", str(tmp_path / "res")])
    assert rc == 1  # a hard FAIL is non-zero
    files = list((tmp_path / "res").glob("*.md"))
    assert len(files) == 1 and "| a |" in files[0].read_text() and "FAIL" in files[0].read_text()


def test_main_returns_zero_when_only_expected_failures(tmp_path, monkeypatch):
    _case(tmp_path, "x", expected_fail=True)
    monkeypatch.setattr(run_evals, "_default_runner", lambda cmd, env, cwd, timeout: 1)
    assert (
        run_evals.main(["--cases", str(tmp_path / "cases"), "--rom", "rom.gb", "--results-dir", str(tmp_path / "r")])
        == 0
    )


def test_default_runner_invokes_subprocess(monkeypatch):
    calls = {}

    class P:
        returncode = 0

    def fake_run(cmd, **kw):
        calls["cmd"] = cmd
        calls["kw"] = kw
        return P()

    monkeypatch.setattr(run_evals.subprocess, "run", fake_run)
    assert run_evals._default_runner(["echo"], {"A": "1"}, "/tmp", 5) == 0
    assert calls["cmd"] == ["echo"] and calls["kw"]["timeout"] == 5 and calls["kw"]["env"]["A"] == "1"


def test_default_runner_timeout_is_failure(monkeypatch):
    def boom(cmd, **kw):
        raise run_evals.subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(run_evals.subprocess, "run", boom)
    assert run_evals._default_runner(["x"], {}, "/tmp", 1) == 124
