# tests/test_discovery.py
"""Tests for the discovery engine (scripts/discovery.py) — loop 3."""

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import discovery
import pytest

# ---------------------------------------------------------------------------
# Queue
# ---------------------------------------------------------------------------


def _entry(**kw):
    base = {"at": 100.0, "rule": "navigation-thrash", "reason": "rejects-exhausted", "fitness": {}, "handled": False}
    base.update(kw)
    return base


def test_load_queue_missing_or_corrupt(tmp_path):
    assert discovery.load_queue(tmp_path / "nope.json") == []
    bad = tmp_path / "bad.json"
    bad.write_text("{oops")
    assert discovery.load_queue(bad) == []


def test_pick_entry_oldest_unhandled():
    entries = [_entry(at=1.0, handled=True), _entry(at=2.0), _entry(at=3.0)]
    entry, idx = discovery.pick_entry(entries, manual_reason=None)
    assert entry["at"] == 2.0
    assert idx == 1


def test_pick_entry_none_when_all_handled():
    entry, idx = discovery.pick_entry([_entry(handled=True)], manual_reason=None)
    assert entry is None and idx is None


def test_pick_entry_manual_reason_synthesizes():
    entry, idx = discovery.pick_entry([], manual_reason="demo: forest wall")
    assert idx is None
    assert entry["reason"] == "manual"
    assert entry["rule"] == "manual"
    assert entry["detail"] == "demo: forest wall"


def test_mark_handled_persists(tmp_path):
    q = tmp_path / "queue.json"
    q.write_text(json.dumps([_entry(), _entry(at=200.0)]))
    discovery.mark_handled(q, 1)
    entries = json.loads(q.read_text())
    assert entries[0]["handled"] is False
    assert entries[1]["handled"] is True


# ---------------------------------------------------------------------------
# Bundle + prompt + branch
# ---------------------------------------------------------------------------


def test_build_bundle_gathers_context():
    races = [{"rule": "navigation-thrash", "accepted": False}]
    bundle = discovery.build_bundle(_entry(fitness={"stuck_count": 15}), races, "obs tail")
    assert bundle["rule"] == "navigation-thrash"
    assert bundle["fitness"] == {"stuck_count": 15}
    assert bundle["races"] == races
    assert bundle["observations"] == "obs tail"
    assert "scripts/pathfinding.py" in bundle["code_map"]


def test_build_prompt_carries_constraints_and_evidence():
    bundle = discovery.build_bundle(_entry(fitness={"stuck_count": 15}), [], "the agent oscillated at a door")
    prompt = discovery.build_prompt(bundle)
    assert "navigation-thrash" in prompt
    assert "stuck_count" in prompt
    assert "oscillated" in prompt
    assert "minimal" in prompt.lower()
    assert "do not delete or weaken tests" in prompt.lower()
    assert "scripts/pathfinding.py" in prompt


def test_branch_name():
    assert discovery.branch_name("navigation-thrash", "2026-07-19") == "discovery/navigation-thrash-2026-07-19"


# ---------------------------------------------------------------------------
# run_evidence — measurement that outranks the operator's hypothesis
# ---------------------------------------------------------------------------


def _events(tmp_path, rows):
    path = tmp_path / "events.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows))
    return path


def _stuck(turn, x, y):
    return {"event_type": "stuck", "turn": turn, "data": {"position": {"x": x, "y": y}}}


def test_run_evidence_ranks_positions_by_count(tmp_path):
    path = _events(
        tmp_path,
        [_stuck(t, 6, 2) for t in (317, 400, 7996)]
        + [_stuck(t, 25, 17) for t in (186, 204)]
        + [{"event_type": "decision", "turn": 1, "data": {}}],  # non-stuck ignored
    )
    evidence = discovery.run_evidence(path)
    assert evidence["stuck_total"] == 5
    top = evidence["top_positions"][0]
    assert top["position"] == [6, 2]
    assert (top["count"], top["first_turn"], top["last_turn"]) == (3, 317, 7996)


def _decision(turn, x, y, buttons):
    return {
        "event_type": "decision",
        "turn": turn,
        "data": {"reason": f"map 51 ({x},{y}) stuck=0 | WP: 0→(1,43)", "buttons": buttons},
    }


def test_run_evidence_extracts_the_decision_loop_signature(tmp_path):
    """The trace, not the stuck counts, is what shows a two-tile limit cycle."""
    rows = []
    for turn in range(20):
        rows.append(_decision(turn, 6, 2, ["up"]) if turn % 2 == 0 else _decision(turn, 6, 1, ["down"]))
    evidence = discovery.run_evidence(_events(tmp_path, rows), trace_len=4)

    assert evidence["loop_signature"][0] == {"where": "map 51 (6,2)", "buttons": "up", "count": 10}
    assert evidence["loop_signature"][1] == {"where": "map 51 (6,1)", "buttons": "down", "count": 10}
    # Tail is capped and keeps the *last* decisions — the terminal behaviour.
    assert [d["turn"] for d in evidence["final_decisions"]] == [16, 17, 18, 19]
    assert evidence["final_decisions"][-1] == {"turn": 19, "where": "map 51 (6,1)", "buttons": "down"}


def test_format_evidence_renders_signature_and_trace(tmp_path):
    path = _events(tmp_path, [_decision(7999, 6, 1, ["down"]), _stuck(317, 6, 2)])
    text = discovery.format_evidence(discovery.run_evidence(path))
    assert "map 51 (6,1) → down: 1×" in text
    assert "T7999 map 51 (6,1) → down" in text


def test_prompt_names_the_existing_machinery():
    prompt = discovery.build_prompt(discovery.build_bundle(_entry(), [], "", {}))
    assert "AlphaEvolve" in prompt
    assert "Factorio Learning Environment" in prompt
    assert "DEFAULT_PARAMS" in prompt  # new thresholds must become evolvable


def test_run_evidence_tolerates_a_partial_last_line(tmp_path):
    """A live run's log can end mid-write; that must not lose the whole file."""
    path = tmp_path / "events.jsonl"
    path.write_text(json.dumps(_stuck(10, 1, 1)) + "\n{partial")
    assert discovery.run_evidence(path)["stuck_total"] == 1


def test_run_evidence_empty_when_absent_or_eventless(tmp_path):
    assert discovery.run_evidence(tmp_path / "nope.jsonl") == {}
    assert discovery.run_evidence(_events(tmp_path, [{"event_type": "milestone", "turn": 1}])) == {}
    # A decision-only log still yields trace evidence — loops can exist
    # without ever tripping the stuck detector.
    assert discovery.run_evidence(_events(tmp_path, [{"event_type": "decision", "turn": 1}]))["loop_signature"]


def test_format_evidence_states_the_counts_and_the_log(tmp_path):
    text = discovery.format_evidence(discovery.run_evidence(_events(tmp_path, [_stuck(317, 6, 2)])))
    assert "(6,2) — 1 events, turns 317–317" in text
    assert "events.jsonl" in text


def test_format_evidence_admits_when_nothing_was_measured():
    """Empty evidence must not claim authority — "no log exists" was itself
    an unmeasured claim, and telling proposers to trust it over a correct
    operator note recreated the misdirection this section exists to prevent."""
    for empty in ({}, None):
        text = discovery.format_evidence(empty)
        assert "not measured" in text
        assert "trust the measurement" not in text.lower()


def test_prompt_marks_the_note_as_hypothesis_when_measured(tmp_path):
    """A wrong operator note must not read as a conclusion — this bit a real run."""
    evidence = discovery.run_evidence(_events(tmp_path, [_stuck(317, 6, 2)]))
    prompt = discovery.build_prompt(discovery.build_bundle(_entry(), [], "", evidence))
    assert "hypothesis" in prompt.lower()
    assert "trust the measurement" in prompt.lower()


def test_events_for_fitness_resolves_recorded_runs(tmp_path):
    run_dir = tmp_path / "runs" / "20260810-185357-7f79"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text("")
    found = discovery.events_for_fitness({"run_id": "20260810-185357-7f79"}, runs_dir=tmp_path / "runs")
    assert found == run_dir / "events.jsonl"
    # No run_id (unrecorded run) or no log on disk → None, never a guess.
    assert discovery.events_for_fitness({}, runs_dir=tmp_path / "runs") is None
    assert discovery.events_for_fitness({"run_id": "nope"}, runs_dir=tmp_path / "runs") is None
    assert discovery.events_for_fitness(None) is None


def test_every_healer_rule_has_a_code_map():
    """A rule the healer can escalate must not fall back to the "manual" map."""
    from healer import RULES

    for rule in RULES:
        assert rule["name"] in discovery.RULE_CODE_MAP, rule["name"]


def test_nav_rules_point_at_the_editable_route_file():
    for name in ("navigation-thrash", "terminal-wedge"):
        assert "references/routes.json" in discovery.RULE_CODE_MAP[name]


# ---------------------------------------------------------------------------
# pending_escalation — "the healer already escalated this run"
# ---------------------------------------------------------------------------

_FITNESS = {
    "turns": 8000,
    "stuck_count": 682,
    "max_stuck_streak": 95,
    "final_x": 6,
    "final_y": 2,
    "final_map_id": 51,
}


def test_pending_escalation_matches_on_run_identity(tmp_path):
    queue = tmp_path / "q.json"
    queue.write_text(
        json.dumps(
            [
                _entry(rule="terminal-wedge", handled=True, fitness=_FITNESS),  # handled: skipped
                _entry(fitness={**_FITNESS, "stuck_count": 3}),  # different run
                _entry(fitness=_FITNESS),
            ]
        )
    )
    found = discovery.pending_escalation(queue, _FITNESS)
    assert found == {"rule": "navigation-thrash", "reason": "rejects-exhausted", "position": 2, "pending": 2}


def test_pending_escalation_none_when_run_never_escalated(tmp_path):
    queue = tmp_path / "q.json"
    queue.write_text(json.dumps([_entry(fitness=_FITNESS)]))
    assert discovery.pending_escalation(queue, {**_FITNESS, "turns": 10}) is None
    assert discovery.pending_escalation(tmp_path / "missing.json", _FITNESS) is None


def test_pending_escalation_ignores_entries_missing_identity_keys(tmp_path):
    """An empty-fitness entry must not match every run by vacuous truth."""
    queue = tmp_path / "q.json"
    queue.write_text(json.dumps([_entry(fitness={})]))
    assert discovery.pending_escalation(queue, _FITNESS) is None


# ---------------------------------------------------------------------------
# prompt subcommand — the hand-driven half of loop 3
# ---------------------------------------------------------------------------


def _prompt_args(tmp_path, **kw):
    fitness = tmp_path / "fitness.json"
    fitness.write_text(json.dumps(_FITNESS))
    args = {
        "fitness": str(fitness),
        "rule": "navigation-thrash",
        "detail": "ping-pongs between two tiles",
        "reason": "operator",
        "json": False,
        "events": None,
        "queue": str(tmp_path / "queue.json"),
        "healer_state": str(tmp_path / "healer.json"),
    }
    args.update(kw)
    return SimpleNamespace(**args)


def test_prompt_counts_evidence_from_the_log_beside_the_fitness_file(tmp_path, capsys):
    _events(tmp_path, [_stuck(317, 6, 2), _stuck(400, 6, 2), _stuck(186, 25, 17)])
    discovery._prompt(_prompt_args(tmp_path))
    out = capsys.readouterr().out
    assert "(6,2) — 2 events" in out  # dominant wedge, not the one a human clicked
    assert "(25,17) — 1 events" in out


def test_prompt_prints_the_proposer_prompt(tmp_path, capsys):
    assert discovery._prompt(_prompt_args(tmp_path)) == 0
    out = capsys.readouterr().out
    assert "navigation-thrash" in out
    assert "ping-pongs between two tiles" in out
    assert "682" in out  # the run's own evidence
    assert "references/routes.json" in out
    assert "do not delete or weaken tests" in out.lower()


def test_prompt_writes_no_state(tmp_path):
    """Drafting is read-only — it must not consume a queue entry or set a cooldown."""
    discovery._prompt(_prompt_args(tmp_path))
    assert not (tmp_path / "queue.json").exists()
    assert not (tmp_path / "healer.json").exists()


def test_prompt_json_mode_carries_escalation(tmp_path):
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps([_entry(fitness=_FITNESS)]))
    args = _prompt_args(tmp_path, json=True, queue=str(queue))
    with patch("builtins.print") as printer:
        assert discovery._prompt(args) == 0
    payload = json.loads(printer.call_args[0][0])
    assert payload["escalation"]["reason"] == "rejects-exhausted"
    assert "navigation-thrash" in payload["prompt"]


def test_prompt_json_mode_escalation_none_for_clean_run(tmp_path):
    with patch("builtins.print") as printer:
        discovery._prompt(_prompt_args(tmp_path, json=True))
    assert json.loads(printer.call_args[0][0])["escalation"] is None


def test_prompt_unreadable_fitness_exits_nonzero(tmp_path, capsys):
    """Unlike `run`, something is waiting on this — failures must surface."""
    assert discovery._prompt(_prompt_args(tmp_path, fitness=str(tmp_path / "nope.json"))) == 1
    assert "unreadable fitness file" in capsys.readouterr().err


def test_prompt_subcommand_dispatches_through_main(tmp_path, capsys):
    fitness = tmp_path / "fitness.json"
    fitness.write_text(json.dumps(_FITNESS))
    argv = ["discovery.py", "prompt", "--fitness", str(fitness), "--queue", str(tmp_path / "q.json")]
    with patch("sys.argv", argv):
        assert discovery.main() == 0
    assert "You are the discovery engine" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# sh wrapper (real subprocess, trivial command)
# ---------------------------------------------------------------------------


def test_sh_runs_and_captures(tmp_path):
    result = discovery.sh(["python3", "-c", "print('hi')"], cwd=tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == "hi"


# ---------------------------------------------------------------------------
# Gates
# ---------------------------------------------------------------------------


def _completed(rc=0, stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")


def test_run_gates_all_pass_with_eval(tmp_path):
    def fake_sh(cmd, cwd=None, timeout=None):
        if "pytest" in cmd:
            return _completed(0, "900 passed")
        if "ruff" in cmd:
            return _completed(0, "All checks passed!")
        raise AssertionError(f"unexpected sh: {cmd}")

    candidate = {"turns": 100, "stuck_count": 0, "final_map_id": 0}
    baseline = {"turns": 100, "stuck_count": 40, "final_map_id": 0}
    with patch.object(discovery, "sh", side_effect=fake_sh):
        with patch.object(discovery, "eval_candidate", return_value=[discovery.score(candidate)]):
            with patch.object(discovery, "run_agent", return_value=baseline):
                passed, report = discovery.run_gates(tmp_path, "rom.gb", eval_runs=1, race_turns=100)
    assert passed is True
    assert "pytest" in report and "eval" in report


def test_run_gates_fail_on_tests(tmp_path):
    def fake_sh(cmd, cwd=None, timeout=None):
        if "pytest" in cmd:
            return _completed(1, "1 failed")
        return _completed(0)

    with patch.object(discovery, "sh", side_effect=fake_sh):
        passed, report = discovery.run_gates(tmp_path, "rom.gb", eval_runs=0, race_turns=100)
    assert passed is False
    assert "1 failed" in report


def test_run_gates_fail_on_eval_margin(tmp_path):
    good = {"final_map_id": 0, "stuck_count": 1}
    with patch.object(discovery, "sh", return_value=_completed(0, "ok")):
        with patch.object(discovery, "eval_candidate", return_value=[discovery.score(good)]):
            with patch.object(discovery, "run_agent", return_value=good):  # same score -> no margin
                passed, report = discovery.run_gates(tmp_path, "rom.gb", eval_runs=1, race_turns=100)
    assert passed is False


def test_run_gates_eval_skipped_when_zero(tmp_path):
    with patch.object(discovery, "sh", return_value=_completed(0, "ok")):
        with patch.object(discovery, "run_agent") as ra:
            passed, report = discovery.run_gates(tmp_path, "rom.gb", eval_runs=0, race_turns=100)
    ra.assert_not_called()
    assert passed is True
    assert "eval skipped" in report


def test_eval_candidate_runs_worktree_agent(tmp_path):
    fitness = {"final_map_id": 12}
    out = tmp_path / "out.json"
    rom_args = []

    def fake_sh(cmd, cwd=None, timeout=None):
        rom_args.append(cmd[2])  # [python, agent.py, ROM, ...]
        Path(cmd[cmd.index("--output-json") + 1]).write_text(json.dumps(fitness))
        return _completed(0)

    with patch.object(discovery, "sh", side_effect=fake_sh):
        scores = discovery.eval_candidate(tmp_path, "rom.gb", runs=2, turns=100)
    assert scores == [discovery.score(fitness)] * 2
    assert not out.exists()  # temp files cleaned by eval_candidate itself
    # The candidate runs with cwd=worktree, which has no ROM (gitignored):
    # a relative rom path would be unresolvable there. Must be absolutized.
    assert all(Path(r).is_absolute() for r in rom_args)


# ---------------------------------------------------------------------------
# run flow (everything patched)
# ---------------------------------------------------------------------------


@pytest.fixture()
def run_env(tmp_path):
    queue = tmp_path / "queue.json"
    queue.write_text(json.dumps([_entry(fitness={"stuck_count": 15})]))
    state = tmp_path / "state.json"
    argv = [
        "discovery.py",
        "run",
        "--rom",
        "rom.gb",
        "--queue",
        str(queue),
        "--state",
        str(state),
        "--eval-runs",
        "0",
    ]
    return tmp_path, queue, state, argv


def _patch_flow(has_changes=True, gates=(True, "all green"), pr_url="https://pr/1"):
    return {
        "worktree": patch.object(discovery, "worktree_add", return_value=(Path("/wt"), "abc123")),
        "propose": patch.object(discovery, "propose", return_value="proposed"),
        "changes": patch.object(discovery, "has_changes", return_value=has_changes),
        "gates": patch.object(discovery, "run_gates", return_value=gates),
        "commit": patch.object(discovery, "commit_if_needed"),
        "pr": patch.object(discovery, "push_and_pr", return_value=pr_url),
        "cleanup": patch.object(discovery, "cleanup"),
        "races": patch.object(discovery, "recent_races", return_value=[]),
        "obs": patch.object(discovery, "read_observations_tail", return_value=""),
    }


def _run_main(argv, patches):
    from contextlib import ExitStack

    mocks = {}
    with ExitStack() as stack:
        for name, p in patches.items():
            mocks[name] = stack.enter_context(p)
        stack.enter_context(patch("sys.argv", argv))
        rc = discovery.main()
    return rc, mocks


def test_run_happy_path_opens_pr_and_marks_handled(run_env, capsys):
    tmp_path, queue, state, argv = run_env
    rc, mocks = _run_main(argv, _patch_flow())
    assert rc == 0
    mocks["pr"].assert_called_once()
    title = mocks["pr"].call_args.args[2]
    assert "[eval pending]" in title  # eval-runs 0
    assert "navigation-thrash" in title
    assert json.loads(queue.read_text())[0]["handled"] is True
    saved = json.loads(state.read_text())
    assert saved["attempts"][0]["outcome"] == "pr-opened"
    assert "https://pr/1" in capsys.readouterr().out


def test_run_no_changes_cleans_up_no_pr(run_env, capsys):
    tmp_path, queue, state, argv = run_env
    rc, mocks = _run_main(argv, _patch_flow(has_changes=False))
    assert rc == 0
    mocks["pr"].assert_not_called()
    mocks["gates"].assert_not_called()
    mocks["cleanup"].assert_called_once()
    assert json.loads(state.read_text())["attempts"][0]["outcome"] == "no-proposal"


def test_run_gate_failure_cleans_up_no_pr(run_env):
    tmp_path, queue, state, argv = run_env
    rc, mocks = _run_main(argv, _patch_flow(gates=(False, "1 failed")))
    assert rc == 0
    mocks["pr"].assert_not_called()
    mocks["cleanup"].assert_called_once()
    assert json.loads(state.read_text())["attempts"][0]["outcome"] == "gates-failed"
    assert json.loads(queue.read_text())[0]["handled"] is True  # one attempt per entry


def test_run_empty_queue_does_nothing(run_env, capsys):
    tmp_path, queue, state, argv = run_env
    queue.write_text("[]")
    rc, mocks = _run_main(argv, _patch_flow())
    assert rc == 0
    mocks["worktree"].assert_not_called()
    assert "nothing to discover" in capsys.readouterr().out


def test_run_cooldown_blocks(run_env, capsys):
    tmp_path, queue, state, argv = run_env
    import time

    state.write_text(json.dumps({"last_attempt_at": time.time(), "attempts": []}))
    rc, mocks = _run_main(argv, _patch_flow())
    assert rc == 0
    mocks["worktree"].assert_not_called()
    assert "cooldown" in capsys.readouterr().out


def test_run_dry_run_stops_before_worktree(run_env, capsys):
    tmp_path, queue, state, argv = run_env
    rc, mocks = _run_main(argv + ["--dry-run"], _patch_flow())
    assert rc == 0
    mocks["worktree"].assert_not_called()
    out = capsys.readouterr().out
    assert "dry-run" in out and "navigation-thrash" in out


def test_run_manual_reason_without_queue(run_env, capsys):
    tmp_path, queue, state, argv = run_env
    queue.write_text("[]")
    rc, mocks = _run_main(argv + ["--reason", "forest wall glitch"], _patch_flow())
    assert rc == 0
    mocks["pr"].assert_called_once()
    assert "manual" in mocks["pr"].call_args.args[2]


def test_run_engine_error_exits_zero(run_env, capsys):
    tmp_path, queue, state, argv = run_env
    with patch.object(discovery, "worktree_add", side_effect=RuntimeError("git exploded")):
        with (
            patch.object(discovery, "recent_races", return_value=[]),
            patch.object(discovery, "read_observations_tail", return_value=""),
        ):
            with patch("sys.argv", argv):
                assert discovery.main() == 0
    assert "discovery error" in capsys.readouterr().out


def test_module_entrypoint_exits_zero(run_env):
    import runpy

    tmp_path, queue, state, argv = run_env
    queue.write_text("[]")
    with patch("sys.argv", argv):
        with pytest.raises(SystemExit) as exc:
            runpy.run_path(str(discovery.__file__), run_name="__main__")
    assert exc.value.code == 0


# ---------------------------------------------------------------------------
# Impure edges, sh patched
# ---------------------------------------------------------------------------


def test_worktree_add_success_and_failure(tmp_path):
    calls = []

    def fake_sh(cmd, cwd=None, timeout=None):
        calls.append(cmd)
        if cmd[:2] == ["git", "worktree"]:
            return _completed(0)
        return _completed(0, "abc123\n")

    with patch.object(discovery, "sh", side_effect=fake_sh):
        wt, sha = discovery.worktree_add(tmp_path, "discovery/x-1")
    assert wt == tmp_path / ".discovery" / "discovery-x-1"
    assert sha == "abc123"

    with patch.object(discovery, "sh", return_value=subprocess.CompletedProcess([], 128, "", "fatal: exists")):
        with pytest.raises(RuntimeError, match="worktree add failed"):
            discovery.worktree_add(tmp_path, "discovery/x-1")


def test_cleanup_removes_worktree_and_branch(tmp_path):
    calls = []

    def record(cmd, cwd=None, timeout=None):
        calls.append(cmd)
        return _completed(0)

    with patch.object(discovery, "sh", side_effect=record):
        discovery.cleanup(tmp_path, tmp_path / "wt", "discovery/x-1")
    assert ["git", "worktree", "remove", "--force", str(tmp_path / "wt")] == calls[0]
    assert ["git", "branch", "-D", "discovery/x-1"] == calls[1]


def test_propose_invokes_claude_headless(tmp_path):
    captured = {}

    def fake_sh(cmd, cwd=None, timeout=None):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        return _completed(0, "did the thing")

    with patch.object(discovery, "sh", side_effect=fake_sh):
        out = discovery.propose(tmp_path, "fix it", max_turns=7)
    assert out == "did the thing"
    assert captured["cmd"][:3] == ["claude", "-p", "fix it"]
    assert "acceptEdits" in captured["cmd"]
    assert "7" in captured["cmd"]
    assert captured["cwd"] == tmp_path


def test_has_changes_detects_dirty_and_new_commits(tmp_path):
    with patch.object(discovery, "sh", side_effect=[_completed(0, " M x.py\n"), _completed(0, "abc\n")]):
        assert discovery.has_changes(tmp_path, "abc") is True
    with patch.object(discovery, "sh", side_effect=[_completed(0, ""), _completed(0, "def\n")]):
        assert discovery.has_changes(tmp_path, "abc") is True
    with patch.object(discovery, "sh", side_effect=[_completed(0, ""), _completed(0, "abc\n")]):
        assert discovery.has_changes(tmp_path, "abc") is False


def test_commit_if_needed_only_when_dirty(tmp_path):
    calls = []

    def fake_sh(cmd, cwd=None, timeout=None):
        calls.append(cmd)
        return _completed(0, " M x.py\n" if cmd[:2] == ["git", "status"] else "")

    with patch.object(discovery, "sh", side_effect=fake_sh):
        discovery.commit_if_needed(tmp_path, "msg")
    assert ["git", "add", "-A"] in calls
    calls.clear()

    def record_clean(cmd, cwd=None, timeout=None):
        calls.append(cmd)
        return _completed(0, "")

    with patch.object(discovery, "sh", side_effect=record_clean):
        discovery.commit_if_needed(tmp_path, "msg")
    assert len(calls) == 1  # status only, no add/commit


def test_push_and_pr_success_and_failures(tmp_path):
    with patch.object(discovery, "sh", side_effect=[_completed(0), _completed(0, "https://pr/9\n")]):
        assert discovery.push_and_pr(tmp_path, "b", "t", "body") == "https://pr/9"
    with patch.object(discovery, "sh", return_value=subprocess.CompletedProcess([], 1, "", "denied")):
        with pytest.raises(RuntimeError, match="push failed"):
            discovery.push_and_pr(tmp_path, "b", "t", "body")
    with patch.object(discovery, "sh", side_effect=[_completed(0), subprocess.CompletedProcess([], 1, "", "no auth")]):
        with pytest.raises(RuntimeError, match="gh pr create failed"):
            discovery.push_and_pr(tmp_path, "b", "t", "body")


def test_recent_races_and_observations_tail(tmp_path):
    hs = tmp_path / "healer_state.json"
    hs.write_text(json.dumps({"races": [{"rule": f"r{i}"} for i in range(8)]}))
    races = discovery.recent_races(hs, n=5)
    assert [r["rule"] for r in races] == ["r3", "r4", "r5", "r6", "r7"]

    obs = tmp_path / "observations.md"
    obs.write_text("x" * 5000 + "TAIL")
    assert discovery.read_observations_tail(obs, chars=10).endswith("TAIL")
    assert discovery.read_observations_tail(tmp_path / "missing.md") == ""


def test_eval_candidate_bad_output_scores_minus_inf(tmp_path):
    with patch.object(discovery, "sh", return_value=_completed(0)):  # never writes the output json
        scores = discovery.eval_candidate(tmp_path, "rom.gb", runs=1, turns=10)
    assert scores == [float("-inf")]


def test_run_gates_fail_on_ruff(tmp_path):
    def fake_sh(cmd, cwd=None, timeout=None):
        if "pytest" in cmd:
            return _completed(0, "ok")
        if "ruff" in cmd:
            return _completed(1, "E501 line too long")
        raise AssertionError(f"unexpected sh: {cmd}")

    with patch.object(discovery, "sh", side_effect=fake_sh):
        passed, report = discovery.run_gates(tmp_path, "rom.gb", eval_runs=0, race_turns=100)
    assert passed is False
    assert "E501" in report
