"""role_metrics reads both harness transcripts and counts executions, not mentions."""

import json

import role_metrics as rm


def _claude_log(tmp_path, tool_uses, result=None):
    p = tmp_path / "x.claude.jsonl"
    lines = []
    for name, inp in tool_uses:
        lines.append(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {"model": "m", "content": [{"type": "tool_use", "name": name, "input": inp}]},
                }
            )
        )
    if result:
        lines.append(json.dumps({"type": "result", **result}))
    p.write_text("\n".join(lines) + "\n")
    return p


def test_grep_of_a_script_is_a_read_not_a_probe_or_relay(tmp_path):
    """The first version counted `grep -n foo scripts/agent.py` as a probe and inflated laguna-xs
    to 47 probes on a run that made one relay call. Only an execution counts."""
    p = _claude_log(
        tmp_path,
        [
            ("Bash", {"command": "grep -n waypoint scripts/agent.py | head"}),
            ("Bash", {"command": "grep -n stop_on scripts/relay.py"}),
            ("Bash", {"command": "uv run python scripts/agent.py rom.gb --load-state s.state --max-turns 200"}),
            ("Bash", {"command": "uv run python scripts/relay.py rom.gb --segments badge_to_mtmoon"}),
        ],
        result={"subtype": "success", "duration_ms": 60_000},
    )
    s = rm.parse_claude(p)
    assert (s.relay_calls, s.probe_calls, s.code_reads) == (1, 1, 2)
    assert s.calls_before_first_relay == 3


def test_edit_order_and_learnings_are_tracked(tmp_path):
    p = _claude_log(
        tmp_path,
        [
            ("Read", {"file_path": "/wt/scripts/parcel_quest.py"}),
            ("Read", {"file_path": "/wt/scripts/relay.py"}),
            ("Edit", {"file_path": "/wt/scripts/parcel_quest.py"}),
            ("Read", {"file_path": "/wt/scripts/agent.py"}),
            ("Write", {"file_path": "/wt/docs/learnings/route3-to-mtmoon.md"}),
            ("Edit", {"file_path": "/wt/tests/test_parcel_quest.py"}),
        ],
        result={"subtype": "success", "duration_ms": 30 * 60_000},
    )
    s = rm.parse_claude(p)
    assert s.code_reads_before_first_edit == 2 and s.calls_before_first_edit == 2
    assert s.code_files_edited == {"scripts/parcel_quest.py"}
    assert s.learnings_written == {"route3-to-mtmoon.md"} and len(s.tests_touched) == 1


def test_pi_session_parses_tool_calls_and_dead_stream(tmp_path):
    p = tmp_path / "s.jsonl"
    rows = [
        {"type": "model_change", "modelId": "qwen38-27b-128k", "timestamp": "2026-08-18T14:00:00.000Z"},
        {
            "type": "message",
            "timestamp": "2026-08-18T14:00:01.000Z",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "toolCall",
                        "name": "bash",
                        "arguments": {"command": "uv run python scripts/agent.py rom.gb --max-turns 50"},
                    }
                ],
            },
        },
        {"type": "message", "timestamp": "2026-08-18T14:10:00.000Z", "message": {"role": "assistant", "content": []}},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    s = rm.parse_pi(p)
    assert s.model == "qwen38-27b-128k" and s.probe_calls == 1
    assert round(s.wall_min) == 10
    assert s.ended_by_choice is False, "an empty final assistant turn is the dead-stream signature"


def test_main_prints_a_markdown_table(tmp_path, capsys):
    p = _claude_log(
        tmp_path,
        [("Bash", {"command": "uv run python scripts/relay.py rom.gb"})],
        result={"subtype": "success", "duration_ms": 1000},
    )
    assert rm.main([str(p), "--repo", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("| run |") and "| x |" in out


def test_malformed_lines_bad_timestamps_and_string_arguments_are_tolerated(tmp_path):
    p = tmp_path / "s.jsonl"
    rows = [
        "not json at all",
        json.dumps({"type": "message", "timestamp": "garbage", "message": {"role": "user", "content": "hi"}}),
        json.dumps(
            {
                "type": "message",
                "timestamp": "2026-08-18T14:00:00.000Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "toolCall",
                            "name": "bash",
                            "arguments": '{"command": "uv run python scripts/relay.py rom.gb"}',
                        },
                        {"type": "toolCall", "name": "bash", "arguments": "plain string not json"},
                        {"type": "text", "text": "done"},
                    ],
                },
            }
        ),
    ]
    p.write_text("\n".join(rows) + "\n")
    s = rm.parse_pi(p)
    assert s.relay_calls == 1 and s.calls == 2
    assert s.ended_by_choice is True
    assert s.wall_min == 0.0  # a single timestamp has no span


def test_claude_log_without_result_and_malformed_lines(tmp_path):
    p = tmp_path / "k.claude.jsonl"
    p.write_text(
        "{bad\n" + json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "x"}]}}) + "\n"
    )
    s = rm.parse_claude(p)
    assert s.calls == 0 and s.ended_by_choice is None and s.wall_min == 0.0


def test_worktree_commits_counts_the_run_branch_and_tolerates_git_errors(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    wt = tmp_path / "pokemon-kafka-speedrun-demo"
    repo.mkdir()
    wt.mkdir()
    monkeypatch.setattr(rm.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": "abc one\ndef two\n"})())
    assert rm.worktree_commits("demo", repo) == 2
    assert rm.worktree_commits("nope", repo) is None

    def boom(*a, **k):
        raise OSError("no git")

    monkeypatch.setattr(rm.subprocess, "run", boom)
    assert rm.worktree_commits("demo", repo) is None


def test_main_handles_missing_files_and_json_output(tmp_path, capsys):
    p = _claude_log(tmp_path, [("Bash", {"command": "echo hi"})], result={"subtype": "success", "duration_ms": 1000})
    assert rm.main([str(tmp_path / "missing.claude.jsonl"), str(p), "--repo", str(tmp_path), "--json"]) == 0
    out, err = capsys.readouterr()
    assert "missing" in err
    assert json.loads(out)[0]["label"] == "x"


def test_dunder_main_guard(tmp_path):
    """if __name__ == '__main__': sys.exit(main())"""
    import runpy
    from pathlib import Path
    from unittest.mock import patch

    import pytest

    p = _claude_log(tmp_path, [("Bash", {"command": "echo hi"})], result={"subtype": "success", "duration_ms": 1000})
    with patch("sys.argv", ["role_metrics.py", str(p), "--repo", str(tmp_path)]), pytest.raises(SystemExit) as e:
        runpy.run_path(str(Path(rm.__file__).resolve()), run_name="__main__")
    assert e.value.code == 0
