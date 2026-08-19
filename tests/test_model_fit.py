"""model_fit: the per-model operator character as mission context, kept measured."""

import json

import model_fit as mf


def _fit(tmp_path, **models):
    p = tmp_path / "fit.json"
    p.write_text(json.dumps({"characters": ["driver"], "models": models}))
    return p


def test_resolve_matches_exact_then_prefix_then_substring():
    models = {"haiku-4-5": {}, "qwen38-27b": {}, "laguna-xs": {}}
    assert mf.resolve(models, "haiku-4-5") == "haiku-4-5"
    assert mf.resolve(models, "haiku-4-5-20251001") == "haiku-4-5", "launcher SHORT name is a prefix match"
    assert mf.resolve(models, "qwen38-27b-128k") == "qwen38-27b", "Ollama tag carries the alias"
    assert mf.resolve(models, "claude-sonnet-5") is None, "an unlisted model must not match anything"


def test_section_renders_verdict_guidance_and_measured_numbers(tmp_path):
    p = _fit(
        tmp_path,
        **{
            "haiku-4-5": {
                "strong": ["driver"],
                "weak": ["experimenter"],
                "guidance": ["probe before a third relay"],
                "measured": {
                    "sessions": 2,
                    "probe_per_relay": 0.0,
                    "calls_before_first_relay": 28.5,
                    "early_exit_sessions": 2,
                },
            }
        },
    )
    out = mf.section("claude-haiku-4-5-20251001", p)
    assert "ASSIST=fit" in out and "assisted" in out, "the section must label itself as assistance"
    assert "strong as **driver**" in out and "weak as **experimenter**" in out
    assert "- probe before a third relay" in out
    assert "probe/relay 0.0" in out and "early exit in 2 of 2" in out


def test_section_is_empty_for_an_unknown_model(tmp_path):
    """A new roster entry must not silently become an assisted row."""
    p = _fit(tmp_path, **{"haiku-4-5": {"strong": [], "weak": [], "guidance": []}})
    assert mf.section("claude-sonnet-5", p) == ""


def test_update_folds_role_metrics_into_measured(tmp_path, monkeypatch):
    p = _fit(tmp_path, **{"haiku-4-5": {"strong": ["driver"], "weak": [], "guidance": [], "measured": {}}})
    # two fake claude logs: model name resolves to the fit key
    logs = []
    for i, (relays, probes, ms) in enumerate([(9, 0, 15 * 60_000), (9, 0, 38 * 60_000)]):
        lp = tmp_path / f"haiku-run{i}.claude.jsonl"
        rows = []
        for _ in range(relays):
            rows.append(
                {
                    "type": "assistant",
                    "message": {
                        "model": "claude-haiku-4-5-20251001",
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {"command": "uv run python scripts/relay.py rom.gb"},
                            }
                        ],
                    },
                }
            )
        for _ in range(probes):
            rows.append(
                {
                    "type": "assistant",
                    "message": {
                        "model": "claude-haiku-4-5-20251001",
                        "content": [
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {"command": "uv run python scripts/agent.py rom.gb --max-turns 5"},
                            }
                        ],
                    },
                }
            )
        rows.append({"type": "result", "subtype": "success", "duration_ms": ms})
        lp.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        logs.append(str(lp))
    d = mf.update(logs + [str(tmp_path / "missing.claude.jsonl")], p)
    me = d["models"]["haiku-4-5"]["measured"]
    assert me["sessions"] == 2 and me["probe_per_relay"] == 0.0 and me["early_exit_sessions"] == 2
    assert json.loads(p.read_text())["models"]["haiku-4-5"]["measured"]["sessions"] == 2, "written back"


def test_show_and_main_commands(tmp_path, capsys):
    p = _fit(
        tmp_path,
        **{
            "qwen38-27b": {
                "harness": "pi",
                "strong": ["investigator"],
                "weak": ["driver"],
                "guidance": ["x"],
                "measured": {
                    "sessions": 3,
                    "probe_per_relay": 4.5,
                    "calls_before_first_relay": 100,
                    "early_exit_sessions": 1,
                },
            }
        },
    )
    assert mf.main(["--fit", str(p), "show"]) == 0
    out = capsys.readouterr().out
    assert "| qwen38-27b | pi | investigator | driver | 3 | 4.5 | 100 | 1 |" in out
    assert mf.main(["--fit", str(p), "section", "qwen38-27b-128k"]) == 0
    assert "investigator" in capsys.readouterr().out
    lp = tmp_path / "q.claude.jsonl"
    lp.write_text(json.dumps({"type": "assistant", "message": {"model": "qwen38-27b-128k", "content": []}}) + "\n")
    assert mf.main(["--fit", str(p), "update", str(lp)]) == 0
    assert "| qwen38-27b |" in capsys.readouterr().out
