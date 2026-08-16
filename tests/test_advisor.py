import json
import subprocess

import advisor as adv
import pytest


def _session(tmp_path, n_turns=3, tool_calls=True, stop="stop", model="laguna-xs-128k"):
    lines = [json.dumps({"type": "model_change", "modelId": model})]
    for i in range(n_turns):
        content = [{"type": "text", "text": f"turn {i} thinking about the flee loop"}]
        if tool_calls:
            content.append(
                {
                    "type": "toolCall",
                    "name": "bash",
                    "arguments": {"command": f"uv run python scripts/relay.py rom/x.gb --segments s{i}"},
                }
            )
        lines.append(
            json.dumps(
                {
                    "type": "message",
                    "message": {"role": "assistant", "content": content, "stopReason": stop, "model": model},
                }
            )
        )
        lines.append(
            json.dumps(
                {"type": "message", "message": {"role": "toolResult", "content": [{"type": "text", "text": "x" * 500}]}}
            )
        )
    lines.append("not json")
    p = tmp_path / "2026-08-16T00-00-00_abc.jsonl"
    p.write_text("\n".join(lines) + "\n")
    return p


# ---------------------------------------------------------------- digest


def test_digest_counts_and_truncates(tmp_path):
    d = adv.digest_session(_session(tmp_path, n_turns=4))
    assert d["turns"] == 4 and d["tool_calls"] == 4 and d["stop_reason"] == "stop" and d["model"] == "laguna-xs-128k"
    assert d["turns_digest"][0]["results"][0] == "x" * 300
    assert d["final_text"].startswith("turn 3")


def test_digest_elides_the_middle_of_long_sessions(tmp_path):
    d = adv.digest_session(_session(tmp_path, n_turns=100), head=5, tail=10)
    assert len(d["turns_digest"]) == 16 and "85 turns elided" in d["turns_digest"][5]["text"]


def test_digest_handles_empty_and_string_content(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(json.dumps({"type": "message", "message": {"role": "assistant", "content": "plain string"}}) + "\n")
    d = adv.digest_session(p)
    assert d["turns"] == 1 and d["final_text"] == "plain string"
    assert adv._text_of(42) == ""
    e = adv.digest_session(tmp_path / "missing.jsonl") if False else adv.digest_session(p)
    assert e["turns"] == 1


def test_worktree_facts_reads_reports_learnings_and_diff(tmp_path, monkeypatch):
    wt = tmp_path / "wt"
    (wt / "data/relay/r1").mkdir(parents=True)
    (wt / "data/relay/r1/report.json").write_text(
        json.dumps({"segments": [{"name": "a", "winner": "base"}, {"name": "b", "winner": None}]})
    )
    (wt / "data/relay/r2").mkdir()
    (wt / "data/relay/r2/report.json").write_text("{broken")
    (wt / "docs/learnings").mkdir(parents=True)
    (wt / "docs/learnings/x.md").write_text("obstacle: x")
    monkeypatch.setattr(adv.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": " scripts/agent.py | 3 +\n"})())
    f = adv.worktree_facts(wt)
    assert f["relay"] == [{"run": "r1", "segments": [{"name": "a", "winner": "base"}, {"name": "b", "winner": None}]}]
    assert f["learnings"] == ["x.md"] and "agent.py" in f["diff"]
    assert adv.worktree_facts(None) == {} and adv.worktree_facts(tmp_path / "nope") == {}


def test_worktree_facts_survives_git_failure(tmp_path, monkeypatch):
    wt = tmp_path / "wt"
    wt.mkdir()

    def boom(*a, **k):
        raise OSError("no git")

    monkeypatch.setattr(adv.subprocess, "run", boom)
    assert adv.worktree_facts(wt)["diff"] == ""


def test_render_digest_includes_ground_truth(tmp_path):
    d = adv.digest_session(_session(tmp_path, n_turns=1))
    txt = adv.render_digest(
        d, {"relay": [{"run": "r1", "segments": [{"name": "a", "winner": None}]}], "learnings": [], "diff": ""}
    )
    assert "GROUND TRUTH" in txt and "relay r1: a=None" in txt and "learnings written: none" in txt
    assert "GROUND TRUTH" not in adv.render_digest(d, {})


# ---------------------------------------------------------------- oracle


def _corpus(tmp_path):
    (tmp_path / "docs/learnings").mkdir(parents=True)
    (tmp_path / "docs/learnings/pewter.md").write_text(
        "# Pewter Pokecenter wedge\n\nLanes walk into map 58 and press up into the counter at (11,3) "
        "for 3000 turns.\n\n"
        "The Gym is map 54, not 58.\n"
    )
    (tmp_path / "docs/learnings/flee.md").write_text(
        "# Route 2 flee loop\n\nThe stall guard returns run forever against a Weedle at 4/23 HP.\n"
    )
    (tmp_path / "evals/model-cases").mkdir(parents=True)
    (tmp_path / "evals/model-cases/c.json").write_text(
        json.dumps({"name": "c", "prompt": "why does the wild battle loop?", "rubric": [{"id": "r"}]})
    )
    (tmp_path / "evals/model-cases/bad.json").write_text("{not json")
    return tmp_path


def test_oracle_ranks_the_relevant_file_and_cites(tmp_path):
    ws = _corpus(tmp_path)
    res = adv.oracle("why do lanes stall in Pewter at (11,3)?", workspace=ws, use_tapes=False)
    assert res["precedent"] and res["chunks"][0]["path"] == "docs/learnings/pewter.md"
    txt = adv.format_oracle(res)
    assert "(docs/learnings/pewter.md:" in txt and "NO PRECEDENT" not in txt
    res2 = adv.oracle("wild battle loop", workspace=ws, use_tapes=False, k=2)
    assert {c["path"] for c in res2["chunks"]} & {"docs/learnings/flee.md", "evals/model-cases/c.json"}


def test_oracle_says_no_precedent(tmp_path):
    ws = _corpus(tmp_path)
    res = adv.oracle("zzqx qqzz", workspace=ws, use_tapes=False)
    assert not res["precedent"] and adv.format_oracle(res) == "NO PRECEDENT"
    assert adv.rank_chunks("", [{"text": "a", "path": "p", "line": 1}]) == []
    assert adv.rank_chunks("x", []) == []


def test_oracle_with_model_synthesises_from_excerpts(tmp_path, monkeypatch):
    ws = _corpus(tmp_path)
    seen = {}

    def fake(model, prompt, **kw):
        seen["system"] = kw["system"]
        seen["prompt"] = prompt
        return {
            "answer": "Map 58 is the Pokecenter (docs/learnings/pewter.md:3)",
            "thinking": "",
            "wall_s": 1,
            "out_tok": 5,
            "out_tok_s": 5.0,
        }

    monkeypatch.setattr(adv.rme, "ask_ollama", fake)
    res = adv.oracle("pewter counter", workspace=ws, use_tapes=False, model="m")
    assert res["answer"].startswith("Map 58") and "EXCERPTS" in seen["prompt"] and "knowledge bearer" in seen["system"]
    assert adv.format_oracle(res).startswith("Map 58")


def test_tapes_precedents_parses_cli_output(monkeypatch):
    out = (
        'Span Search Results for: "q"\n\n  #1  score: 0.5054  trc_x/llm_y\n  turn: You are the operator ...\n'
        "   ├─ The agent is stuck in an endless battle loop on Route 1\n"
        "  2026-08-15T20:06:35Z  session 01a00703-7350\n\n"
        "  #2  score: 0.4996  trc_a/llm_b\n   ├─ Critical issue: infinite loop fleeing a Weedle\n"
        "  2026-08-15T17:08:38Z  session 01a00651-2d74\n"
    )
    monkeypatch.setattr(adv.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": out})())
    hits = adv.tapes_precedents("q")
    assert [h["session"] for h in hits] == ["01a00703-7350", "01a00651-2d74"]
    assert hits[0]["score"] == 0.5054 and "endless battle loop" in hits[0]["snippet"]


def test_tapes_precedents_empty_when_cli_missing(monkeypatch):
    def boom(*a, **k):
        raise OSError("no tapesctl")

    monkeypatch.setattr(adv.subprocess, "run", boom)
    assert adv.tapes_precedents("q") == []


def test_tapes_precedents_timeout(monkeypatch):
    def slow(*a, **k):
        raise subprocess.TimeoutExpired("tapesctl", 1)

    monkeypatch.setattr(adv.subprocess, "run", slow)
    assert adv.tapes_precedents("q") == []


# ---------------------------------------------------------------- investigator


GOOD_PROPOSAL = {
    "tip": "Inside the Pewter Gym do not pilot north; route to Brock at the north end of map 54.",
    "rationale": "GO_NORTH_PILOT_MAPS lists PEWTER_GYM so cross_step walks into a wall.",
    "decisive_because": "the code comment argues the opposite",
    "learning": (
        "obstacle: gym-pilot-north\ncategory: navigation\nsymptom: lanes wedge inside map 54\n"
        "winner: remove PEWTER_GYM from GO_NORTH_PILOT_MAPS and route to Brock at the north end"
    ),
    "heal": "remove PEWTER_GYM from GO_NORTH_PILOT_MAPS",
    "model_eval_case": {
        "name": "gym-pilot-north",
        "category": "navigation",
        "prompt": "Lanes reach map 54 and stall with a 2800 stuck streak. What is wrong?",
        "rubric": [
            {"id": "pilot", "weight": 3, "any": ["pilot.?north", "GO_NORTH_PILOT_MAPS", "cross_step"]},
            {"id": "fix", "weight": 2, "any": ["remove PEWTER_GYM", "route to Brock", "north end"]},
        ],
        "anti": [{"id": "blame-env", "weight": 2, "any": ["misconfigur"]}],
    },
    "agent_eval_case": None,
}


def test_validate_proposal_flags_problems():
    assert adv.validate_proposal(GOOD_PROPOSAL) == []
    bad = dict(
        GOOD_PROPOSAL, tip="", model_eval_case={"name": "x", "prompt": "", "rubric": [{"id": "r", "any": ["("]}]}
    )
    probs = adv.validate_proposal(bad)
    assert (
        any("missing tip" in p for p in probs)
        and any("needs name" in p for p in probs)
        and any("bad regex" in p for p in probs)
    )


def test_extract_json_handles_prose_and_rejects_none():
    assert adv._extract_json('here you go:\n{"a": 1}\nthanks') == {"a": 1}
    with pytest.raises(ValueError):
        adv._extract_json("no json here")


def test_investigate_writes_a_proposal_with_meta(tmp_path, monkeypatch):
    ws = _corpus(tmp_path)
    sess = _session(tmp_path, n_turns=6)
    wt = tmp_path / "wt"
    (wt / "data/relay/r1").mkdir(parents=True)
    (wt / "data/relay/r1/report.json").write_text(
        json.dumps({"segments": [{"name": "pewter_to_badge", "winner": None}]})
    )
    monkeypatch.setattr(adv.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": ""})())
    seen = {}

    def fake(model, prompt, **kw):
        seen["prompt"] = prompt
        seen["system"] = kw["system"]
        return {
            "answer": "```json\n" + json.dumps(GOOD_PROPOSAL) + "\n```",
            "thinking": "",
            "wall_s": 1,
            "out_tok": 1,
            "out_tok_s": 1.0,
        }

    monkeypatch.setattr(adv.rme, "ask_ollama", fake)
    out = adv.investigate(
        sess, worktree=wt, model="qwen38-27b-128k", out_dir=tmp_path / "out", workspace=ws, use_tapes=False
    )
    p = json.loads(out.read_text())
    assert p["tip"] == GOOD_PROPOSAL["tip"] and p["_meta"]["problems"] == []
    assert p["_meta"]["digest"]["turns"] == 6 and p["_meta"]["investigator_model"] == "qwen38-27b-128k"
    assert (
        "ALREADY KNOWN" in seen["prompt"]
        and "GROUND TRUTH" in seen["prompt"]
        and "pewter_to_badge=None" in seen["prompt"]
    )
    assert "Investigator" in seen["system"]


# ---------------------------------------------------------------- gate + promote


def _write_proposal(tmp_path, proposal=GOOD_PROPOSAL):
    p = tmp_path / "s.proposal.json"
    p.write_text(json.dumps(dict(proposal, _meta={"session": "/x/abc.jsonl", "investigator_model": "q"})))
    return p


def test_gate_passes_when_the_tip_lifts(tmp_path, monkeypatch):
    p = _write_proposal(tmp_path)

    def fake(model, prompt, **kw):
        treated = "prior session" in kw.get("system", "")
        ans = (
            "GO_NORTH_PILOT_MAPS makes it pilot north; remove PEWTER_GYM and route to Brock"
            if treated
            else "probably misconfigured"
        )
        return {"answer": ans, "thinking": "", "wall_s": 1, "out_tok": 1, "out_tok_s": 1.0}

    monkeypatch.setattr(adv.rme, "ask_ollama", fake)
    r = adv.gate(p, models=["a-128k", "b-128k"], results_dir=tmp_path / "res")
    assert r["passed"] and r["reference_score"] >= 0.9 and r["mean_lift"] == 1.0
    assert json.loads(p.with_suffix(".gate.json").read_text())["passed"]
    md = next((tmp_path / "res").glob("advisor-*.md")).read_text()
    assert "| gym-pilot-north |" in md and "PASS" in md
    adv.gate(p, models=["a-128k"], results_dir=tmp_path / "res")  # append, header once
    assert next((tmp_path / "res").glob("advisor-*.md")).read_text().count("# Advisor gate results") == 1


def test_gate_fails_without_lift(tmp_path, monkeypatch):
    p = _write_proposal(tmp_path)
    monkeypatch.setattr(
        adv.rme,
        "ask_ollama",
        lambda model, prompt, **kw: {
            "answer": "GO_NORTH_PILOT_MAPS; remove PEWTER_GYM",
            "thinking": "",
            "wall_s": 1,
            "out_tok": 1,
            "out_tok_s": 1.0,
        },
    )
    r = adv.gate(p, models=["a-128k"])
    assert not r["passed"] and "mean lift 0.00" in r["reason"]


def test_gate_rejects_a_rubric_that_cannot_recognise_its_reference(tmp_path, monkeypatch):
    bad = json.loads(json.dumps(GOOD_PROPOSAL))
    bad["model_eval_case"]["rubric"] = [{"id": "impossible", "weight": 3, "any": ["zzqx never appears"]}]
    p = _write_proposal(tmp_path, bad)
    called = []
    monkeypatch.setattr(adv.rme, "ask_ollama", lambda *a, **k: called.append(1))
    r = adv.gate(p, models=["a-128k"])
    assert not r["passed"] and "reference" in r["reason"] and called == []


def test_promote_refuses_ungated_and_failed(tmp_path):
    p = _write_proposal(tmp_path)
    with pytest.raises(SystemExit, match="not gated"):
        adv.promote(p, workspace=tmp_path)
    p.with_suffix(".gate.json").write_text(json.dumps({"passed": False}))
    with pytest.raises(SystemExit, match="FAILED"):
        adv.promote(p, workspace=tmp_path)


def test_promote_writes_case_learning_and_tip(tmp_path):
    p = _write_proposal(tmp_path)
    p.with_suffix(".gate.json").write_text(json.dumps({"passed": True}))
    (tmp_path / "evals/model-cases").mkdir(parents=True)
    (tmp_path / "docs/learnings").mkdir(parents=True)
    written = adv.promote(p, workspace=tmp_path)
    assert [w.name for w in written] == ["gym-pilot-north.json", "gym-pilot-north.md", "tips.md"]
    case = json.loads((tmp_path / "evals/model-cases/gym-pilot-north.json").read_text())
    assert case["learning"] == "docs/learnings/gym-pilot-north.md" and case["context"] == []
    assert "source:        advisor" in (tmp_path / "docs/learnings/gym-pilot-north.md").read_text()
    tips = (tmp_path / "docs/prompts/tips.md").read_text()
    assert tips.startswith("# Gated tips") and "route to Brock" in tips
    adv.promote(p, workspace=tmp_path, force=True)  # idempotent-ish: appends a second tip line, header once
    assert (tmp_path / "docs/prompts/tips.md").read_text().count("# Gated tips") == 1


# ---------------------------------------------------------------- cli


def test_cli_investigate_gate_promote_oracle(tmp_path, monkeypatch, capsys):
    ws = _corpus(tmp_path)
    monkeypatch.setattr(adv, "WORKSPACE", ws)
    sess = _session(tmp_path, n_turns=2)
    monkeypatch.setattr(adv.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": ""})())

    def fake(model, prompt, **kw):
        if "Investigator" in kw.get("system", ""):
            return {"answer": json.dumps(GOOD_PROPOSAL), "thinking": "", "wall_s": 1, "out_tok": 1, "out_tok_s": 1.0}
        treated = "prior session" in kw.get("system", "")
        return {
            "answer": "GO_NORTH_PILOT_MAPS, remove PEWTER_GYM" if treated else "no idea",
            "thinking": "",
            "wall_s": 1,
            "out_tok": 1,
            "out_tok_s": 1.0,
        }

    monkeypatch.setattr(adv.rme, "ask_ollama", fake)
    out_dir = tmp_path / "adv"
    assert adv.main(["investigate", str(sess), "--out-dir", str(out_dir), "--no-tapes"]) == 0
    prop = out_dir / f"{sess.stem}.proposal.json"
    out = capsys.readouterr().out
    assert prop.exists() and "[investigator] tip:" in out and "[oracle]" in out and "ALREADY KNOWN" in out
    assert adv.main(["gate", str(prop), "--models", "a-128k", "--results-dir", str(tmp_path / "r")]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "the tip is the only variable" in out
    monkeypatch.setattr(adv, "WORKSPACE", ws)
    (ws / "evals/model-cases").mkdir(exist_ok=True)
    assert adv.main(["promote", str(prop)]) == 0
    assert "[promote] wrote" in capsys.readouterr().out
    assert adv.main(["oracle", "pewter counter", "--no-tapes", "--json"]) == 0
    assert '"precedent": true' in capsys.readouterr().out
    assert adv.main(["oracle", "zzqx", "--no-tapes"]) == 0
    out = capsys.readouterr().out
    assert "NO PRECEDENT" in out and "[oracle] 0 excerpt(s)" in out


def test_cli_investigate_reports_problems(tmp_path, monkeypatch, capsys):
    sess = _session(tmp_path, n_turns=1)
    monkeypatch.setattr(adv.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": ""})())
    bad = dict(GOOD_PROPOSAL, tip="")
    monkeypatch.setattr(
        adv.rme,
        "ask_ollama",
        lambda *a, **k: {"answer": json.dumps(bad), "thinking": "", "wall_s": 1, "out_tok": 1, "out_tok_s": 1.0},
    )
    assert adv.main(["investigate", str(sess), "--out-dir", str(tmp_path / "o"), "--no-tapes"]) == 0
    assert "problems" in capsys.readouterr().out


def test_cli_gate_without_models(monkeypatch, tmp_path):
    p = _write_proposal(tmp_path)
    monkeypatch.setattr(adv.rme, "local_variants", lambda ctx: [])
    assert adv.main(["gate", str(p)]) == 2


def test_cli_gate_fail_returns_1(monkeypatch, tmp_path):
    p = _write_proposal(tmp_path)
    monkeypatch.setattr(
        adv.rme,
        "ask_ollama",
        lambda *a, **k: {"answer": "no idea", "thinking": "", "wall_s": 1, "out_tok": 1, "out_tok_s": 1.0},
    )
    assert adv.main(["gate", str(p), "--models", "a", "--results-dir", str(tmp_path / "r")]) == 1


def test_load_corpus_skips_unreadable_files(tmp_path, monkeypatch):
    ws = _corpus(tmp_path)
    real = adv.Path.read_text

    def flaky(self, *a, **k):
        if self.name == "flee.md":
            raise OSError("unreadable")
        return real(self, *a, **k)

    monkeypatch.setattr(adv.Path, "read_text", flaky)
    paths = {c["path"] for c in adv.load_corpus(ws)}
    assert "docs/learnings/pewter.md" in paths and "docs/learnings/flee.md" not in paths


def test_format_oracle_lists_tapes_hits():
    res = {
        "precedent": True,
        "answer": None,
        "chunks": [],
        "tapes": [{"session": "abc", "score": 0.5, "snippet": "stuck fleeing a Weedle"}],
    }
    assert "(session abc, score 0.5) stuck fleeing" in adv.format_oracle(res)


def test_repair_rubric_fixes_a_self_inconsistent_rubric(monkeypatch):
    bad = json.loads(json.dumps(GOOD_PROPOSAL))
    bad["model_eval_case"]["rubric"] = [{"id": "pilot", "weight": 3, "any": ["zzqx never"]}]
    calls = []

    def fake(model, prompt, **kw):
        calls.append(prompt)
        assert "REFERENCE ANSWER" in prompt and "MISSED ITEMS" in prompt
        return {
            "answer": json.dumps(
                {"rubric": [{"id": "pilot", "weight": 3, "any": ["pilot north", "GO_NORTH_PILOT_MAPS"]}], "anti": []}
            ),
            "thinking": "",
            "wall_s": 1,
            "out_tok": 1,
            "out_tok_s": 1.0,
        }

    monkeypatch.setattr(adv.rme, "ask_ollama", fake)
    fixed = adv.repair_rubric(bad, model="m")
    assert len(calls) == 1 and fixed["_meta"]["rubric_repairs"] == 1
    assert adv.rme.score_answer(fixed["model_eval_case"], adv.reference_text(fixed))["score"] >= 0.9


def test_repair_rubric_noop_when_consistent_and_stops_on_bad_reply(monkeypatch):
    calls = []
    monkeypatch.setattr(
        adv.rme,
        "ask_ollama",
        lambda *a, **k: (
            calls.append(1) or {"answer": "not json", "thinking": "", "wall_s": 1, "out_tok": 1, "out_tok_s": 1.0}
        ),
    )
    good = json.loads(json.dumps(GOOD_PROPOSAL))
    assert adv.repair_rubric(good, model="m") is good and calls == []
    bad = json.loads(json.dumps(GOOD_PROPOSAL))
    bad["model_eval_case"]["rubric"] = [{"id": "pilot", "weight": 3, "any": ["zzqx never"]}]
    adv.repair_rubric(bad, model="m")
    assert calls == [1] and "rubric_repairs" not in bad.get("_meta", {})


def test_investigate_records_reference_score_and_repairs(tmp_path, monkeypatch):
    ws = _corpus(tmp_path)
    sess = _session(tmp_path, n_turns=2)
    monkeypatch.setattr(adv.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": ""})())
    bad = json.loads(json.dumps(GOOD_PROPOSAL))
    bad["model_eval_case"]["rubric"] = [{"id": "pilot", "weight": 3, "any": ["zzqx never"]}]

    def fake(model, prompt, **kw):
        if "REFERENCE ANSWER" in prompt:
            return {
                "answer": json.dumps({"rubric": GOOD_PROPOSAL["model_eval_case"]["rubric"], "anti": []}),
                "thinking": "",
                "wall_s": 1,
                "out_tok": 1,
                "out_tok_s": 1.0,
            }
        return {"answer": json.dumps(bad), "thinking": "", "wall_s": 1, "out_tok": 1, "out_tok_s": 1.0}

    monkeypatch.setattr(adv.rme, "ask_ollama", fake)
    out = adv.investigate(sess, worktree=None, model="m", out_dir=tmp_path / "o", workspace=ws, use_tapes=False)
    meta = json.loads(out.read_text())["_meta"]
    assert meta["rubric_repairs"] == 1 and meta["reference_score"] >= 0.9


def test_repair_rubric_retries_when_reply_is_thinking_only(monkeypatch):
    bad = json.loads(json.dumps(GOOD_PROPOSAL))
    bad["model_eval_case"]["rubric"] = [{"id": "pilot", "weight": 3, "any": ["zzqx never"]}]
    calls = []

    def fake(model, prompt, **kw):
        calls.append(kw["num_predict"])
        if len(calls) == 1:
            return {"answer": "", "thinking": "hmm" * 100, "wall_s": 1, "out_tok": 1, "out_tok_s": 1.0}
        return {
            "answer": json.dumps({"rubric": GOOD_PROPOSAL["model_eval_case"]["rubric"]}),
            "thinking": "",
            "wall_s": 1,
            "out_tok": 1,
            "out_tok_s": 1.0,
        }

    monkeypatch.setattr(adv.rme, "ask_ollama", fake)
    fixed = adv.repair_rubric(bad, model="m")
    assert calls == [6000, 8000] and fixed["_meta"]["rubric_repairs"] == 1
