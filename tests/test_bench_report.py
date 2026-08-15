import json

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
    assert bench_report.main(["--label", "demo", str(p)]) == 0
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
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "cloud $" in out and "Wh" in out
    # input 3000*1 + cache 5000*0.1 + output 150*5 = 0.003+0.0005+0.00075 -> $0.0043
    assert "$0.0043" in out
