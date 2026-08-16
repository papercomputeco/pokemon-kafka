import json
from datetime import timedelta

import bench_report


def _msg(ts, role, content, usage=None, stop=None):
    m = {"role": role, "content": content}
    if usage is not None:
        m["usage"] = usage
    if stop:
        m["stopReason"] = stop
    return {"type": "message", "timestamp": ts, "message": m}


def _session(tmp_path, name="s.jsonl"):
    rows = [
        {"type": "session", "timestamp": "2026-08-15T10:00:00.000Z"},
        _msg("2026-08-15T10:00:00.000Z", "user", [{"type": "text", "text": "go"}]),
        # 10 s model latency, one tool call, 100 output tokens
        _msg(
            "2026-08-15T10:00:10.000Z",
            "assistant",
            [{"type": "toolCall", "name": "bash", "arguments": {"command": "ls"}}],
            {"input": 1000, "output": 100, "cacheRead": 5000, "cost": {"total": 0.5}},
        ),
        # 20 s tool time
        _msg("2026-08-15T10:00:30.000Z", "toolResult", [{"type": "text", "text": "ok"}]),
        # 5 s model latency, final text, 50 output tokens
        _msg(
            "2026-08-15T10:00:35.000Z",
            "assistant",
            [{"type": "text", "text": "done"}],
            {"input": 2000, "output": 50, "cacheRead": 0, "cost": {"total": 0.25}},
            stop="stop",
        ),
        {"type": "compaction", "timestamp": "2026-08-15T10:00:36.000Z", "summary": "x"},
    ]
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def test_summarize_computes_time_token_and_speed_columns(tmp_path):
    row = bench_report.summarize([_session(tmp_path)])
    assert row["turns"] == 2
    assert row["tools"] == 1
    assert row["model_s"] == 15.0
    assert row["tool_s"] == 20.0
    assert row["wall_s"] == 35.0
    assert row["input"] == 3000 and row["output"] == 150 and row["cache_read"] == 5000
    assert row["cost"] == 0.75
    assert row["out_tok_s"] == 10.0  # 150 tokens / 15 s
    assert row["s_per_turn"] == 7.5
    assert row["errors"] == 0 and row["compactions"] == 1
    assert row["max_ctx"] == 6000  # input + cache read of the largest turn


def test_summarize_handles_empty_and_error_sessions(tmp_path):
    p = tmp_path / "e.jsonl"
    p.write_text(
        json.dumps(_msg("2026-08-15T10:00:00.000Z", "assistant", [], {"input": 0, "output": 0}, stop="error"))
        + "\nnot json\n"
    )
    row = bench_report.summarize([p])
    assert row["turns"] == 1 and row["errors"] == 1
    assert row["out_tok_s"] == 0.0 and row["s_per_turn"] == 0.0


def test_main_prints_markdown_rows(tmp_path, capsys):
    p = _session(tmp_path)
    assert bench_report.main(["--label", "demo", str(p)], runner=_clean) == 0
    out = capsys.readouterr().out
    assert "| model |" in out and "| demo |" in out and "10.0" in out


def test_main_requires_paths(capsys):
    assert bench_report.main([]) == 2


def test_cloud_cost_uses_published_rates():
    row = {"input": 1_000_000, "cache_read": 10_000_000, "cache_write": 1_000_000, "output": 100_000}
    rates = {"in": 2.0, "out": 10.0, "cache_read": 0.20, "cache_write": 2.50}
    # 2 + 2 + 2.5 + 1 = 7.5
    assert bench_report.cloud_cost(row, rates) == 7.5


def test_summarize_tracks_cache_write(tmp_path):
    p = tmp_path / "c.jsonl"
    p.write_text(
        json.dumps(_msg("2026-08-15T10:00:00.000Z", "user", []))
        + "\n"
        + json.dumps(_msg("2026-08-15T10:00:01.000Z", "assistant", [], {"input": 1, "output": 1, "cacheWrite": 77}))
    )
    assert bench_report.summarize([p])["cache_write"] == 77


def test_energy_from_power_log_integrates_watts(tmp_path):
    log = tmp_path / "power.csv"
    # ts, gpu_w, other_w — 60 s at 300 W GPU + 20 W other = 320 W * 1/60 h = 5.333 Wh
    log.write_text("ts,gpu_w,other_w\n0,300,20\n30,300,20\n60,300,20\n")
    e = bench_report.energy_wh(log)
    assert round(e, 2) == 5.33


def test_energy_from_power_log_handles_bad_lines(tmp_path):
    log = tmp_path / "power.csv"
    log.write_text("ts,gpu_w,other_w\nbad,line\n0,100,\n10,100,\n")
    assert round(bench_report.energy_wh(log), 3) == round(100 * 10 / 3600, 3)
    assert bench_report.energy_wh(tmp_path / "missing.csv") == 0.0


def test_main_prints_cost_and_energy_columns(tmp_path, capsys):
    p = _session(tmp_path)
    log = tmp_path / "power.csv"
    log.write_text("ts,gpu_w,other_w\n0,360,0\n10,360,0\n")
    rc = bench_report.main(
        [
            "--label",
            "x",
            "--rate-in",
            "1",
            "--rate-out",
            "5",
            "--rate-cache-read",
            "0.1",
            "--power-log",
            str(log),
            "--kwh-price",
            "0.30",
            str(p),
        ],
        runner=_clean,
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "cloud $" in out and "Wh" in out
    # input 3000*1 + cache 5000*0.1 + output 150*5 = 0.003+0.0005+0.00075 -> $0.0043
    assert "$0.0043" in out


# --- harness-death guard ---------------------------------------------------------------------


def _clean(cmd):
    """Journal runner that finds nothing — the default for row tests."""
    return ""


def _dead_session(tmp_path, name="dead.jsonl"):
    """The real r4 signature: thinking cut mid-sentence, usage 0/0, stopReason 'stop'."""
    rows = [
        _msg("2026-08-16T17:11:33.000Z", "user", [{"type": "text", "text": "go"}]),
        _msg(
            "2026-08-16T17:14:16.758Z",
            "assistant",
            [{"type": "thinking", "thinking": "In other words, the grid"}],
            {"input": 0, "output": 0},
            stop="stop",
        ),
    ]
    p = tmp_path / name
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def test_journal_returns_output_and_none_when_unreadable(tmp_path, monkeypatch):
    import subprocess

    class _P:
        def __init__(self, rc, out):
            self.returncode, self.stdout = rc, out

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _P(0, "ok\n"))
    assert bench_report._journal(["journalctl"]) == "ok\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _P(1, "ok\n"))
    assert bench_report._journal(["journalctl"]) is None

    def _boom(*a, **k):
        raise FileNotFoundError("no journalctl")

    monkeypatch.setattr(subprocess, "run", _boom)
    assert bench_report._journal(["journalctl"]) is None


def test_run_window_spans_messages_and_is_empty_without_them(tmp_path):
    start, end = bench_report.run_window([_session(tmp_path)])
    assert (end - start).total_seconds() == 35.0
    p = tmp_path / "none.jsonl"
    p.write_text(json.dumps({"type": "session", "timestamp": "2026-08-15T10:00:00.000Z"}) + "\n")
    assert bench_report.run_window([p]) == (None, None)


def test_gpu_hangs_reads_captured_logs(tmp_path):
    kern = tmp_path / "kernel.log"
    kern.write_text("NVRM: Xid (PCI:0000:01:00): 8, pid=1816640, name=llama-server, channel 0x5\n")
    olla = tmp_path / "ollama.log"
    olla.write_text("slot release: id 0\nCUDA error: the launch timed out and was terminated\n")
    res = bench_report.gpu_hangs(None, None, kernel_log=str(kern), ollama_log=str(olla))
    assert res["kernel"]["status"] == "hang" and "Xid" in res["kernel"]["lines"][0]
    assert res["ollama"]["status"] == "hang" and len(res["ollama"]["lines"]) == 1


def test_gpu_hangs_missing_capture_is_unavailable_not_clean(tmp_path):
    res = bench_report.gpu_hangs(None, None, kernel_log=str(tmp_path / "gone.log"))
    assert res["kernel"]["status"] == "unavailable"
    # no capture and no window to query either
    assert res["ollama"]["status"] == "unavailable"


def test_gpu_hangs_queries_the_journal_forward_of_the_run_only(tmp_path):
    start, end = bench_report.run_window([_session(tmp_path)])
    seen = []

    def _runner(cmd):
        seen.append(cmd)
        return "nothing to see\n"

    res = bench_report.gpu_hangs(start, end, pad_s=60, runner=_runner)
    assert [r["status"] for r in res.values()] == ["clean", "clean"]
    assert seen[0][:2] == ["journalctl", "-k"] and seen[1][:3] == ["journalctl", "-u", "ollama"]
    since = seen[0][seen[0].index("--since") + 1]
    until = seen[0][seen[0].index("--until") + 1]
    # start is the run's own first message (no backward pad: the previous run's crash is not ours)
    assert since == start.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    assert until == (end + timedelta(seconds=60)).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def test_dead_stream_detects_a_killed_stream(tmp_path):
    assert "usage 0/0" in bench_report.dead_stream([_dead_session(tmp_path)])
    # a run that ended by choice says something on its last turn
    assert bench_report.dead_stream([_session(tmp_path)]) is None


def test_dead_stream_ignores_healthy_and_empty_tails(tmp_path):
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert bench_report.dead_stream([empty]) is None
    # tokens were billed, so the stream was alive even with nothing said
    billed = tmp_path / "billed.jsonl"
    billed.write_text(json.dumps(_msg("2026-08-16T17:00:00.000Z", "assistant", [], {"input": 5, "output": 0})))
    assert bench_report.dead_stream([billed]) is None
    # a session whose last row is a tool result is truncated, not a dead turn
    tool = tmp_path / "tool.jsonl"
    tool.write_text(json.dumps(_msg("2026-08-16T17:00:00.000Z", "toolResult", [{"type": "text", "text": "ok"}])))
    assert bench_report.dead_stream([tool]) is None


def test_harness_death_collects_reasons_and_uncertified_notes(tmp_path):
    kern = tmp_path / "kernel.log"
    kern.write_text("NVRM: krcWatchdog_IMPL: RC watchdog: GPU is probably locked!\n")
    death = bench_report.harness_death([_dead_session(tmp_path)], kernel_log=str(kern), runner=lambda cmd: None)
    assert len(death["reasons"]) == 2  # dead stream + the kernel hang
    assert any("kernel log" in r for r in death["reasons"])
    assert death["notes"] == ["ollama log not checked (journal unreadable) — this row is not certified clean"]


def test_main_refuses_a_row_when_the_run_died_on_the_harness(tmp_path, capsys):
    kern = tmp_path / "kernel.log"
    kern.write_text("NVRM: Xid (PCI:0000:01:00): 8, pid=1, name=llama-server\n")
    argv = ["--label", "qwen38-27b-r4", "--kernel-log", str(kern), str(_dead_session(tmp_path))]
    assert bench_report.main(argv, runner=_clean) == 3
    cap = capsys.readouterr()
    assert cap.out == ""  # no row, not even a header
    assert "NO ROW" in cap.err and "Xid" in cap.err and "dead stream" in cap.err


def test_main_force_emits_the_row_and_no_hang_check_skips_the_guard(tmp_path, capsys):
    p = _dead_session(tmp_path)
    assert bench_report.main(["--label", "forced", "--force", str(p)], runner=lambda cmd: None) == 0
    cap = capsys.readouterr()
    assert "| forced |" in cap.out and "--force" in cap.err
    assert bench_report.main(["--label", "skipped", "--no-hang-check", str(p)]) == 0
    cap = capsys.readouterr()
    assert "| skipped |" in cap.out and cap.err == ""
