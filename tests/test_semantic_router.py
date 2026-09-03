"""The semantic router config stays coherent and routes the skill missions to the measured winners.

references/semantic_router.yaml encodes benchmarks/2026-08-22-skill-matrix.md; these tests pin
the encoding to the evidence. If a route changes here, a benchmark row must have changed first.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest
import semantic_router as sr
import yaml

CFG = sr.load_config()
MISSIONS = {
    "operator_prompt_skill_recon.md": ("recon-to-investigator", "qwen38-27b-128k"),
    "operator_prompt_skill_battle.md": ("battle-to-driver", "laguna-xs-128k"),
    "operator_prompt_skill_nav.md": ("navigation-to-best-line", "qwen38-27b-128k"),
    "operator_prompt_skill_puzzle.md": ("puzzle-to-deepest", "kimi-k2.6:cloud"),
}


def test_config_is_coherent():
    assert sr.check(CFG) == []


def test_version_and_default():
    assert CFG["version"] == "v0.3"
    assert CFG["providers"]["defaults"]["default_model"] == "qwen38-27b-128k"


@pytest.mark.parametrize("mission,expected", MISSIONS.items())
def test_skill_missions_route_to_measured_winners(mission, expected):
    text = (sr.PROMPTS_DIR / mission).read_text()
    decision, model, hits = sr.classify(text, CFG)
    assert (decision, model) == expected, f"{mission} matched {hits}"


def test_unmatched_text_falls_to_default():
    decision, model, hits = sr.classify("compose a haiku about kafka topics", CFG)
    assert decision is None
    assert model == CFG["providers"]["defaults"]["default_model"]
    assert hits == []


@pytest.mark.parametrize(
    "signal,lower_missions",
    [
        # A higher-priority decision's vocabulary firing on a lower leg's mission would
        # steal that leg's traffic — the exact contamination the priorities can't fix.
        # recon outranks all three, so its vocabulary must fire on none of their missions
        (
            "recon_keywords",
            [
                "operator_prompt_skill_battle.md",
                "operator_prompt_skill_nav.md",
                "operator_prompt_skill_puzzle.md",
            ],
        ),
        ("puzzle_keywords", ["operator_prompt_skill_battle.md", "operator_prompt_skill_nav.md"]),
        ("navigation_keywords", ["operator_prompt_skill_battle.md"]),
    ],
)
def test_no_downward_contamination(signal, lower_missions):
    sig = next(s for s in CFG["routing"]["signals"]["keywords"] if s["name"] == signal)
    for mission in lower_missions:
        text = (sr.PROMPTS_DIR / mission).read_text()
        assert sr._signal_hits(sig, text) == [], f"{signal} fires on {mission}"


def test_backends_go_through_the_tapes_proxy():
    # Routed sessions must stay captured: every backend is the tapes proxy hop pi uses.
    # The full agent path lives in chat_path because the extproc uses it verbatim — a
    # base_url path prefix silently never applies (verified 2026-08-25, capture server).
    for model in CFG["providers"]["models"]:
        for ref in model["backend_refs"]:
            assert "42345" in ref["base_url"], f"{model['name']} bypasses the tapes proxy"
            assert ref["chat_path"] == "/agents/pi/v1/chat/completions"


def test_register_is_idempotent(tmp_path, monkeypatch):
    target = tmp_path / "models.json"
    monkeypatch.setattr(sr, "PI_MODELS_JSON", target)

    class A:
        config = None

    assert sr.cmd_register(A) == 0
    first = target.read_text()
    assert sr.cmd_register(A) == 0
    assert target.read_text() == first
    import json

    entry = json.loads(first)["providers"]["vllm-sr"]["models"][0]
    assert entry["id"] == sr.AUTO_MODEL
    assert entry["contextWindow"] == 131072  # the smallest routed card: any mission must fit it


def test_config_file_is_the_one_the_serve_command_uses():
    assert sr.CONFIG_PATH == Path(sr.WORKSPACE, "references", "semantic_router.yaml")
    assert sr.CONFIG_PATH.exists()


# ------------------------------------------------------------------ check() catches every drift


def _drop_default(c):
    del c["providers"]["defaults"]["default_model"]


def _unknown_default(c):
    c["providers"]["defaults"]["default_model"] = "nope"


def _empty_keywords(c):
    c["routing"]["signals"]["keywords"][0]["keywords"] = []


def _no_decisions(c):
    c["routing"]["decisions"] = []


def _dup_priorities(c):
    for d in c["routing"]["decisions"]:
        d["priority"] = 100


def _undefined_signal(c):
    c["routing"]["decisions"][0]["rules"]["conditions"][0]["name"] = "ghost"


def _no_model_refs(c):
    c["routing"]["decisions"][0]["modelRefs"] = []


def _undefined_model(c):
    c["routing"]["decisions"][0]["modelRefs"] = [{"model": "ghost"}]


def _missing_card(c):
    c["routing"]["modelCards"].pop()


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (_drop_default, "default_model is missing"),
        (_unknown_default, "not in providers.models"),
        (_empty_keywords, "has no keywords"),
        (_no_decisions, "decisions is empty"),
        (_dup_priorities, "not unique"),
        (_undefined_signal, "undefined signal"),
        (_no_model_refs, "has no modelRefs"),
        (_undefined_model, "undefined model"),
        (_missing_card, "has no modelCard"),
    ],
)
def test_check_catches_drift(mutate, expected):
    broken = deepcopy(CFG)
    mutate(broken)
    assert any(expected in p for p in sr.check(broken)), expected


# ------------------------------------------------------------------ the CLI surface


def test_cli_check_ok(capsys):
    assert sr.main(["check"]) == 0
    assert "OK" in capsys.readouterr().out


def test_cli_check_reports_problems(tmp_path, capsys):
    broken = deepcopy(CFG)
    _undefined_model(broken)
    p = tmp_path / "broken.yaml"
    p.write_text(yaml.safe_dump(broken))
    assert sr.main(["--config", str(p), "check"]) == 1
    out = capsys.readouterr().out
    assert "FAIL" in out and str(p) in out


def test_cli_route_offline_text_and_file(tmp_path, capsys):
    assert sr.main(["route", "win the badge"]) == 0
    assert "laguna-xs-128k" in capsys.readouterr().out
    f = tmp_path / "mission.txt"
    f.write_text("route-finding to the ladder")
    assert sr.main(["route", "--file", str(f)]) == 0
    assert "qwen38-27b-128k" in capsys.readouterr().out


def test_cli_route_requires_text():
    with pytest.raises(SystemExit):
        sr.main(["route"])


def test_cli_route_live(monkeypatch, capsys):
    fake = {"model": "kimi-k2.6", "headers": {"x-vsr-selected-model": "kimi-k2.6:cloud"}}
    monkeypatch.setattr(sr, "route_live", lambda text: fake)
    assert sr.main(["route", "--live", "diagnose the spring"]) == 0
    assert "kimi-k2.6" in capsys.readouterr().out


def test_route_live_parses_response(monkeypatch):
    class FakeResp:
        headers = {"X-VSR-Selected-Model": "laguna-xs-128k", "Content-Type": "application/json"}

        def read(self):
            return json.dumps({"model": "laguna-xs-128k"}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    seen = {}

    def fake_urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data)
        return FakeResp()

    monkeypatch.setattr(sr.urllib.request, "urlopen", fake_urlopen)
    out = sr.route_live("win the badge", url="http://router.test")
    assert out["model"] == "laguna-xs-128k"
    assert out["headers"] == {"X-VSR-Selected-Model": "laguna-xs-128k"}
    assert seen["url"] == "http://router.test/v1/chat/completions"
    assert seen["body"]["model"] == sr.AUTO_MODEL


def test_cli_missions_table(capsys):
    assert sr.main(["missions"]) == 0
    out = capsys.readouterr().out
    for mission, (_, model) in MISSIONS.items():
        assert any(mission in line and model in line for line in out.splitlines()), mission


def test_cli_serve_requires_the_cli(monkeypatch):
    monkeypatch.setattr(sr.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit, match="uv tool install vllm-sr"):
        sr.main(["serve"])


def test_cli_serve_execs_with_repo_config(monkeypatch):
    monkeypatch.setattr(sr.shutil, "which", lambda name: "/usr/bin/vllm-sr")
    seen = {}
    monkeypatch.setattr(sr.os, "execvp", lambda prog, argv: seen.update(prog=prog, argv=argv))
    sr.main(["serve"])
    assert seen["prog"] == "vllm-sr"
    assert seen["argv"][-1] == str(sr.CONFIG_PATH)
