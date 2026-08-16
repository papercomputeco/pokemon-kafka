#!/usr/bin/env python3
"""Two advisors and a gate: turn operator sessions into validated tips, evals and learnings.

The operator (a model driving ``scripts/relay.py``) writes its own ``docs/learnings/`` — self-reported
and unverified, which is how fabricated Brock entries and "FIXED" claims without a passing segment
got written down (see ``docs/learnings/by-run/2026-08-16-local-roster/SUMMARY.md``). This module adds
the missing roles, after the shape of ``pcc-labs/inception`` (session → dream → gate → heal):

* **Investigator** (write path) — reads ONE captured pi session and dreams a *proposal*: a decisive
  tip, a learning draft, a model-eval case (prompt + rubric, i.e. inception's benchmark_task + check),
  optionally an agent-eval case. It asks the Oracle first so it does not re-derive what is known.
* **Gate** — the proposal's eval is run on fresh models control (no tip) vs treatment (tip injected
  into the system prompt); the tip is the only variable. It clears the gate only if it lifts the
  score. A rubric that cannot recognise its own reference answer is rejected first.
* **Oracle** (read path) — bears what has already been established: learnings, eval cases and
  results, benchmark rows, and past sessions (tapes semantic search). It cites or says it has
  nothing; it does not reason. Consulted by the Investigator before dreaming and by the operator at
  run time through the ``consult`` tool in ``scripts/pi-ext/guardrails.ts``.
* **Promote** — only gated proposals are written into the repo (eval case, learning, tip).

    uv run python scripts/advisor.py investigate ~/.pi/agent/sessions/<slug>/<id>.jsonl [--worktree DIR]
    uv run python scripts/advisor.py gate data/advisor/<date>/<id>.proposal.json --models a-128k,b-128k
    uv run python scripts/advisor.py promote data/advisor/<date>/<id>.proposal.json
    uv run python scripts/advisor.py oracle "why do lanes stall in Pewter?" [--json] [--no-tapes]

Model calls go through ``run_model_evals.ask_ollama`` (local Ollama, temperature 0). The Investigator
should be an *investigator*-class model (SUMMARY §10): default ``qwen38-27b-128k``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import run_model_evals as rme

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
DEFAULT_OUT = WORKSPACE / "data" / "advisor"
TIPS_FILE = WORKSPACE / "docs" / "prompts" / "tips.md"
DEFAULT_MODEL = os.environ.get("ADVISOR_MODEL", "qwen38-27b-128k")

# --------------------------------------------------------------------------- session digest


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
    return ""


def digest_session(
    path: Path, *, head: int = 15, tail: int = 60, text_chars: int = 400, result_chars: int = 300
) -> dict:
    """Condense a pi session jsonl into what an investigator needs: model, turn count, the tool
    calls (first ``head`` and last ``tail``), assistant text per turn, the final message and how it
    ended. Big sessions (400 tool calls, 12 compactions) must fit one prompt."""
    turns: list[dict] = []
    model = None
    stop = None
    for line in path.read_text().splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("type") == "model_change":
            model = d.get("modelId") or d.get("model") or model
        if d.get("type") != "message":
            continue
        m = d.get("message") or {}
        role = m.get("role")
        if role == "assistant":
            model = m.get("model") or model
            stop = m.get("stopReason") or stop
            calls = []
            for p in m.get("content") or []:
                if isinstance(p, dict) and p.get("type") == "toolCall":
                    a = p.get("arguments") or {}
                    calls.append({"tool": p.get("name"), "arg": (a.get("command") or a.get("path") or "")[:200]})
            turns.append({"text": _text_of(m.get("content"))[:text_chars], "calls": calls, "results": []})
        elif role == "toolResult" and turns:
            turns[-1]["results"].append(_text_of(m.get("content"))[:result_chars])
    n = len(turns)
    keep = (
        turns
        if n <= head + tail
        else turns[:head]
        + [{"text": f"... {n - head - tail} turns elided ...", "calls": [], "results": []}]
        + turns[-tail:]
    )
    return {
        "session": path.name,
        "model": model,
        "turns": n,
        "tool_calls": sum(len(t["calls"]) for t in turns),
        "stop_reason": stop,
        "final_text": turns[-1]["text"] if turns else "",
        "turns_digest": keep,
    }


def worktree_facts(worktree: Path | None) -> dict:
    """Ground truth the session cannot lie about: relay reports, learnings written, code diff."""
    if not worktree or not worktree.exists():
        return {}
    facts: dict = {"relay": [], "learnings": [], "diff": ""}
    for r in sorted(worktree.glob("data/relay/*/report.json")):
        try:
            d = json.loads(r.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        facts["relay"].append(
            {
                "run": r.parent.name,
                "segments": [{"name": s.get("name"), "winner": s.get("winner")} for s in d.get("segments", [])],
            }
        )
    ld = worktree / "docs" / "learnings"
    if ld.exists():
        facts["learnings"] = sorted(p.name for p in ld.glob("*.md"))
    try:
        facts["diff"] = subprocess.run(
            ["git", "-C", str(worktree), "diff", "--stat"], capture_output=True, text=True, timeout=30, check=False
        ).stdout[-2000:]
    except (OSError, subprocess.SubprocessError):
        facts["diff"] = ""
    return facts


def render_digest(digest: dict, facts: dict) -> str:
    out = [
        f"SESSION {digest['session']} — model {digest['model']} — {digest['turns']} assistant turns, "
        f"{digest['tool_calls']} tool calls, ended with stopReason={digest['stop_reason']}"
    ]
    if facts:
        out.append("GROUND TRUTH from the run's worktree (the session cannot contradict this):")
        for r in facts.get("relay", []):
            out.append(f"  relay {r['run']}: " + ", ".join(f"{s['name']}={s['winner']}" for s in r["segments"]))
        out.append("  learnings written: " + (", ".join(facts.get("learnings", [])) or "none"))
        out.append("  code diff: " + (facts.get("diff", "").strip().replace("\n", " | ") or "none"))
    out.append("TRANSCRIPT DIGEST:")
    for i, t in enumerate(digest["turns_digest"]):
        if t["text"]:
            out.append(f"[{i}] assistant: {t['text']}")
        for c in t["calls"]:
            out.append(f"[{i}] {c['tool']}: {c['arg']}")
        for r in t["results"]:
            out.append(f"[{i}] result: {r}")
    out.append(f"FINAL MESSAGE: {digest['final_text']}")
    return "\n".join(out)


# --------------------------------------------------------------------------- oracle (read path)

CORPUS_GLOBS = (
    "docs/learnings/**/*.md",
    "evals/model-cases/*.json",
    "evals/results/*.md",
    "benchmarks/*.md",
    "docs/prompts/tips.md",
)
_WORD = re.compile(r"[a-z0-9_]{2,}")


def _tokens(text: str) -> list[str]:
    return _WORD.findall(text.lower())


def load_corpus(workspace: Path = WORKSPACE, chunk_chars: int = 900) -> list[dict]:
    """Chunk the validated layer by blank-line paragraphs, keeping path:line for citations."""
    chunks = []
    for pattern in CORPUS_GLOBS:
        for p in sorted(workspace.glob(pattern)):
            try:
                text = p.read_text()
            except OSError:
                continue
            if p.suffix == ".json":
                try:
                    d = json.loads(text)
                    text = f"eval case {d.get('name')}: {d.get('prompt', '')}\nrubric: " + "; ".join(
                        i.get("id", "") for i in d.get("rubric", [])
                    )
                except json.JSONDecodeError:
                    pass
            buf, start = [], 1
            for ln, line in enumerate(text.splitlines(), 1):
                if not buf:
                    start = ln
                buf.append(line)
                if (not line.strip() and sum(len(b) for b in buf) > 200) or sum(len(b) for b in buf) > chunk_chars:
                    chunks.append(
                        {"path": str(p.relative_to(workspace)), "line": start, "text": "\n".join(buf).strip()}
                    )
                    buf = []
            if buf and "".join(buf).strip():
                chunks.append({"path": str(p.relative_to(workspace)), "line": start, "text": "\n".join(buf).strip()})
    return [c for c in chunks if c["text"]]


def rank_chunks(query: str, chunks: list[dict], k: int = 6) -> list[dict]:
    """BM25 over the chunks; deterministic, no model."""
    q = _tokens(query)
    if not q or not chunks:
        return []
    docs = [_tokens(c["text"] + " " + c.get("context", "")) for c in chunks]
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n
    df = Counter()
    for d in docs:
        for t in set(d):
            df[t] += 1
    scored = []
    for c, d in zip(chunks, docs):
        tf = Counter(d)
        s = 0.0
        for t in q:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (tf[t] * 2.2) / (tf[t] + 1.2 * (0.25 + 0.75 * len(d) / avgdl))
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: -x[0])
    return [{**c, "score": round(s, 2)} for s, c in scored[:k]]


def tapes_precedents(query: str, *, limit: int = 3, timeout: float = 60.0) -> list[dict]:
    """Past sessions via ``tapesctl search`` (semantic over captured spans). Empty if unavailable."""
    try:
        out = subprocess.run(
            ["tapesctl", "search", query], capture_output=True, text=True, timeout=timeout, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    hits, cur = [], None
    for line in out.splitlines():
        m = re.match(r"\s*#(\d+)\s+score:\s*([0-9.]+)", line)
        if m:
            cur = {"rank": int(m.group(1)), "score": float(m.group(2)), "snippet": "", "session": ""}
            hits.append(cur)
        elif cur is not None:
            sm = re.search(r"session\s+([0-9a-f-]+)", line)
            if sm:
                cur["session"] = sm.group(1)
            elif "├─" in line or line.strip().startswith("turn:"):
                cur["snippet"] = (cur["snippet"] + " " + line.split("├─")[-1].strip()).strip()[:300]
    return hits[:limit]


ORACLE_SYSTEM = (
    "You are the Oracle for a Pokemon Red speedrun harness: a knowledge bearer, not a reasoner. Answer the "
    "question ONLY from the excerpts provided, citing each fact as (path:line) or (session id). If the "
    "excerpts do not contain the answer, reply exactly: NO PRECEDENT. Never speculate, never propose fixes."
)


def oracle(
    question: str, *, workspace: Path | None = None, k: int = 6, use_tapes: bool = True, model: str | None = None
) -> dict:
    chunks = rank_chunks(question, load_corpus(workspace or WORKSPACE), k=k)
    tapes = tapes_precedents(question) if use_tapes else []
    answer = None
    if model and (chunks or tapes):
        excerpts = "\n\n".join(f"({c['path']}:{c['line']})\n{c['text']}" for c in chunks)
        excerpts += "".join(f"\n\n(session {t['session']}) {t['snippet']}" for t in tapes)
        got = rme.ask_ollama(
            model,
            f"QUESTION: {question}\n\nEXCERPTS:\n{excerpts}",
            ctx=32768,
            num_predict=600,
            seed=7,
            system=ORACLE_SYSTEM,
        )
        answer = got["answer"].strip() or None
    return {
        "question": question,
        "chunks": chunks,
        "tapes": tapes,
        "answer": answer,
        "precedent": bool(chunks or tapes),
    }


def format_oracle(res: dict) -> str:
    if not res["precedent"]:
        return "NO PRECEDENT"
    out = []
    if res.get("answer"):
        out.append(res["answer"] + "\n")
    out.append("Excerpts:")
    for c in res["chunks"]:
        first = c["text"].splitlines()[0][:160]
        out.append(f"- ({c['path']}:{c['line']}) {first}")
    for t in res["tapes"]:
        out.append(f"- (session {t['session']}, score {t['score']}) {t['snippet'][:160]}")
    return "\n".join(out)


# --------------------------------------------------------------------------- investigator (write path)

INVESTIGATOR_SYSTEM = (
    "You are the Investigator for a Pokemon Red speedrun harness (a Python repo driving PyBoy via scripts/agent.py "
    "and scripts/relay.py; the operator is an LLM that runs relay segments, reads results, changes code or genomes, "
    "and writes docs/learnings/). You are given the digest of ONE operator session plus ground truth from its "
    "worktree, and what the Oracle already knows. Reflect like an engineer reviewing someone else's run. Produce "
    "exactly ONE proposal: the single most decisive thing a future operator should know that is NOT already in the "
    "Oracle's precedents, plus the eval that would prove it. Be concrete and honest: if the session claims success "
    "the ground truth does not show, say so in the learning. Return ONLY a JSON object with this exact shape:\n"
    "{\n"
    '  "tip": "<one imperative sentence for a future operator>",\n'
    '  "rationale": "<why, 1-2 sentences>",\n'
    '  "decisive_because": "<why a fresh operator cannot derive this from the code alone>",\n'
    '  "learning": "<obstacle-format text: obstacle/category/symptom/failed/winner/'
    'why it worked/generalizes/artifacts>",\n'
    '  "heal": "<the concrete code/data/harness change, or null>",\n'
    '  "model_eval_case": {"name": "<kebab-case>", "category": "<...>", "prompt": "<standalone question for a fresh '
    'model that REQUIRES the tip; do not reveal the tip>", "rubric": [{"id": "...", "weight": 3, "any": '
    '["<regex>", ...]}], "anti": [{"id": "...", "weight": 2, "any": ["<regex>", ...]}]},\n'
    '  "agent_eval_case": null | {"seed_state_hint": "<which savestate>", "stop_on_map": <int>, "max_turns": <int>, '
    '"pass": {"final_map_id": <int>}}\n'
    "}\n"
    "Rules for the eval, because a gate will run it control-vs-treatment: (1) the prompt must NOT telegraph the "
    "answer — describe the situation neutrally as the operator would see it (files, results, what was run) and ask "
    "'what do you do next?' or 'what is wrong?'; a capable model WITHOUT the tip should plausibly answer wrongly or "
    "generically. (2) Rubric items are short paraphrase-tolerant regexes: single keywords or 2-4 word phrases, 4-8 "
    "alternatives per item, NEVER chained '.*' wildcards; anti items are the wrong answers the session itself made. "
    "(3) Prefer one strong rubric item for the decisive fact over three weak phrasing items."
)


def reference_text(p: dict) -> str:
    """What a good answer SAYS: tip + rationale + heal (not the learning, which narrates the failure)."""
    return f"{p.get('tip', '')}\n{p.get('rationale', '')}\n{p.get('heal') or ''}"


REPAIR_SYSTEM = (
    "You wrote an eval rubric that does not match your own reference answer. Rewrite ONLY the rubric (and anti) "
    "so that every rubric item matches the reference text below with short, paraphrase-tolerant regexes (single "
    "keywords or 2-4 word phrases, 4-8 alternatives, no chained '.*'), while still rejecting the wrong answers. "
    'Return ONLY JSON: {"rubric": [...], "anti": [...]} with the same item shape as before.'
)


def repair_rubric(proposal: dict, *, model: str, max_rounds: int = 2) -> dict:
    """Close the loop the gate would otherwise reject: make the rubric recognise the proposal's own reference."""
    for _ in range(max_rounds):
        case = proposal["model_eval_case"]
        verdict = rme.score_answer(case, reference_text(proposal))
        if verdict["score"] >= 0.9:
            break
        prompt = (
            f"REFERENCE ANSWER:\n{reference_text(proposal)}\n\nCURRENT RUBRIC:\n{json.dumps(case.get('rubric', []))}\n"
            f"CURRENT ANTI:\n{json.dumps(case.get('anti', []))}\n\nMISSED ITEMS: {verdict['misses']}; "
            f"ANTI ITEMS THAT WRONGLY FIRED ON THE REFERENCE: {verdict['antis']}"
        )
        # thinking models spend a small budget entirely on thinking (no visible answer); give room and retry once
        got = rme.ask_ollama(model, prompt, ctx=32768, num_predict=6000, seed=7, system=REPAIR_SYSTEM)
        if not got["answer"].strip():
            got = rme.ask_ollama(
                model,
                prompt + "\n\nAnswer with the JSON only, no deliberation.",
                ctx=32768,
                num_predict=8000,
                seed=11,
                system=REPAIR_SYSTEM,
            )
        try:
            fix = _extract_json(got["answer"])
        except (ValueError, json.JSONDecodeError):
            break
        if isinstance(fix.get("rubric"), list) and fix["rubric"]:
            case["rubric"] = fix["rubric"]
        if isinstance(fix.get("anti"), list):
            case["anti"] = fix["anti"]
        proposal.setdefault("_meta", {}).setdefault("rubric_repairs", 0)
        proposal["_meta"]["rubric_repairs"] += 1
    return proposal


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("no JSON object in investigator reply")
    return json.loads(m.group(0))


REQUIRED = ("tip", "rationale", "learning", "model_eval_case")


def validate_proposal(p: dict) -> list[str]:
    problems = [f"missing {k}" for k in REQUIRED if not p.get(k)]
    case = p.get("model_eval_case") or {}
    if not case.get("name") or not case.get("prompt") or not case.get("rubric"):
        problems.append("model_eval_case needs name, prompt, rubric")
    for item in case.get("rubric", []) + case.get("anti", []):
        for pat in item.get("any", []):
            try:
                re.compile(pat)
            except re.error as e:
                problems.append(f"bad regex {pat!r}: {e}")
    return problems


def investigate(
    session: Path,
    *,
    worktree: Path | None,
    model: str,
    out_dir: Path,
    workspace: Path | None = None,
    use_tapes: bool = True,
) -> Path:
    workspace = workspace or WORKSPACE
    digest = digest_session(session)
    facts = worktree_facts(worktree)
    text = render_digest(digest, facts)
    # Ask the Oracle what is already known about what this session was doing, so the dream is new.
    probe = " ".join(t["text"] for t in digest["turns_digest"][-8:] if t["text"])[:800] or digest["final_text"][:800]
    known = oracle(probe or "operator run", workspace=workspace, k=5, use_tapes=use_tapes)
    known_txt = (
        "\n".join(f"- ({c['path']}:{c['line']}) {c['text'].splitlines()[0][:200]}" for c in known["chunks"])
        or "- nothing"
    )
    prompt = f"ALREADY KNOWN (Oracle precedents — do not re-propose these):\n{known_txt}\n\n{text}"
    got = rme.ask_ollama(model, prompt, ctx=131072, num_predict=4000, seed=7, system=INVESTIGATOR_SYSTEM)
    proposal = _extract_json(got["answer"])
    problems = validate_proposal(proposal)
    if not problems:
        proposal = repair_rubric(proposal, model=model)
        problems = validate_proposal(proposal)
    repairs = proposal.get("_meta", {}).get("rubric_repairs", 0)
    proposal["_meta"] = {
        "session": str(session),
        "worktree": str(worktree) if worktree else None,
        "investigator_model": model,
        "digest": {k: digest[k] for k in ("model", "turns", "tool_calls", "stop_reason")},
        "precedents": [c["path"] for c in known["chunks"]],
        "problems": problems,
        "rubric_repairs": repairs,
        "reference_score": rme.score_answer(proposal["model_eval_case"], reference_text(proposal))["score"]
        if not problems
        else None,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{session.stem}.proposal.json"
    path.write_text(json.dumps(proposal, indent=2) + "\n")
    return path


# --------------------------------------------------------------------------- gate


def gate(
    proposal_path: Path,
    *,
    models: list[str],
    min_lift: float = 0.2,
    min_treatment: float = 0.6,
    ctx: int = 131072,
    results_dir: Path | None = None,
) -> dict:
    p = json.loads(proposal_path.read_text())
    case = p["model_eval_case"]
    ref = reference_text(p)
    ref_score = rme.score_answer(case, ref)["score"]
    result = {
        "proposal": str(proposal_path),
        "case": case["name"],
        "reference_score": ref_score,
        "arms": [],
        "passed": False,
        "reason": "",
    }
    if ref_score < 0.9:
        result["reason"] = (
            f"rubric cannot recognise its own reference answer ({ref_score}); rejected before any model ran"
        )
        return _finish_gate(proposal_path, result, results_dir)
    inject = (
        f"{rme.SYSTEM}\n\nRelevant knowledge from a prior session on this system: {p['tip']} {p.get('rationale', '')}"
    )
    for m in models:
        c = rme.ask_ollama(m, case["prompt"], ctx=ctx, num_predict=2500, seed=42)
        t = rme.ask_ollama(m, case["prompt"], ctx=ctx, num_predict=2500, seed=42, system=inject)
        cs, ts = rme.score_answer(case, c["answer"])["score"], rme.score_answer(case, t["answer"])["score"]
        result["arms"].append({"model": m, "control": cs, "treatment": ts, "lift": round(ts - cs, 3)})
    n = len(result["arms"]) or 1
    lift = sum(a["lift"] for a in result["arms"]) / n
    best = max((a["treatment"] for a in result["arms"]), default=0.0)
    result["mean_lift"], result["best_treatment"] = round(lift, 3), round(best, 3)
    # A tip earns its place if it lifts on average AND at least one model can act on it fully — a tip
    # that takes the target driver from 0 to 1 is exactly what we want even if weaker models cannot use it.
    result["passed"] = lift >= min_lift and best >= min_treatment
    result["reason"] = (
        f"mean lift {lift:.2f} ≥ {min_lift} and best treatment {best:.2f} ≥ {min_treatment}"
        if result["passed"]
        else f"mean lift {lift:.2f} (need ≥ {min_lift}), best treatment {best:.2f} (need ≥ {min_treatment})"
    )
    return _finish_gate(proposal_path, result, results_dir)


def _finish_gate(proposal_path: Path, result: dict, results_dir: Path | None) -> dict:
    proposal_path.with_suffix(".gate.json").write_text(json.dumps(result, indent=2) + "\n")
    if results_dir:
        results_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now(timezone.utc)
        path = results_dir / f"advisor-{now:%Y-%m-%d}.md"
        head = (
            ""
            if path.exists()
            else (
                f"# Advisor gate results — {now:%Y-%m-%d}\n\n"
                "| case | ref | arms (control→treatment) | mean lift | verdict | reason |\n|---|---|---|---|---|---|\n"
            )
        )
        arms = "; ".join(f"{a['model']} {a['control']:.2f}→{a['treatment']:.2f}" for a in result["arms"]) or "-"
        verdict = "PASS" if result["passed"] else "FAIL"
        row = (
            f"| {result['case']} | {result['reference_score']:.2f} | {arms} | {result.get('mean_lift', 0):.2f} "
            f"| {verdict} | {result['reason']} |\n"
        )
        path.write_text((path.read_text() if path.exists() else "") + head + row)
    return result


# --------------------------------------------------------------------------- promote


def promote(proposal_path: Path, *, workspace: Path | None = None, force: bool = False) -> list[Path]:
    workspace = workspace or WORKSPACE  # resolved at call time so tests (and PI_GUARD_REPO) can point elsewhere
    p = json.loads(proposal_path.read_text())
    g = proposal_path.with_suffix(".gate.json")
    if not force:
        if not g.exists():
            raise SystemExit("not gated: run `gate` first (or --force)")
        if not json.loads(g.read_text()).get("passed"):
            raise SystemExit("gate FAILED: refusing to promote (or --force)")
    written = []
    case = dict(p["model_eval_case"])
    case.setdefault("learning", f"docs/learnings/{case['name']}.md")
    case.setdefault("context", [])
    cp = workspace / "evals" / "model-cases" / f"{case['name']}.json"
    cp.write_text(json.dumps(case, indent=2) + "\n")
    written.append(cp)
    lp = workspace / "docs" / "learnings" / f"{case['name']}.md"
    src = p.get("_meta", {}).get("session", "?")
    lp.write_text(
        p["learning"].rstrip()
        + f"\n\nsource:        advisor (investigator {p.get('_meta', {}).get('investigator_model')}), "
        + f"gated; session {Path(src).name}\n"
    )
    written.append(lp)
    tips = workspace / "docs" / "prompts" / "tips.md"
    tips.parent.mkdir(parents=True, exist_ok=True)
    head = "" if tips.exists() else "# Gated tips (appended to the operator mission by scripts/local_relay_run.sh)\n\n"
    tips.write_text(
        (tips.read_text() if tips.exists() else "") + head + f"- {p['tip'].strip()} _(gated; {case['name']})_\n"
    )
    written.append(tips)
    return written


# --------------------------------------------------------------------------- cli


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("investigate")
    s.add_argument("session")
    s.add_argument("--worktree", default=None)
    s.add_argument("--model", default=DEFAULT_MODEL)
    s.add_argument("--out-dir", default=str(DEFAULT_OUT / datetime.now(timezone.utc).strftime("%Y-%m-%d")))
    s.add_argument("--no-tapes", action="store_true")
    s = sub.add_parser("gate")
    s.add_argument("proposal")
    s.add_argument("--models", default=None, help="comma-separated; default: every local -128k variant")
    s.add_argument("--min-lift", type=float, default=0.2)
    s.add_argument("--min-treatment", type=float, default=0.6)
    s.add_argument("--results-dir", default=str(WORKSPACE / "evals" / "results"))
    s = sub.add_parser("promote")
    s.add_argument("proposal")
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("oracle")
    s.add_argument("question")
    s.add_argument("--json", action="store_true")
    s.add_argument("--no-tapes", action="store_true")
    s.add_argument("--model", default=None, help="optional model to synthesise a cited answer")
    s.add_argument("-k", type=int, default=6)
    args = ap.parse_args(argv)

    if args.cmd == "investigate":
        path = investigate(
            Path(args.session),
            worktree=Path(args.worktree) if args.worktree else None,
            model=args.model,
            out_dir=Path(args.out_dir),
            use_tapes=not args.no_tapes,
        )
        p = json.loads(path.read_text())
        print(f"[advisor] proposal → {path}")
        print(f"[advisor] tip: {p.get('tip')}")
        if p["_meta"]["problems"]:
            print(f"[advisor] problems: {p['_meta']['problems']}")
        return 0
    if args.cmd == "gate":
        models = args.models.split(",") if args.models else rme.local_variants(131072)
        if not models:
            print("no models", file=sys.stderr)
            return 2
        r = gate(
            Path(args.proposal),
            models=models,
            min_lift=args.min_lift,
            min_treatment=args.min_treatment,
            results_dir=Path(args.results_dir),
        )
        for a in r["arms"]:
            print(
                f"[gate] {a['model']}: control {a['control']:.2f} → treatment {a['treatment']:.2f} "
                f"(lift {a['lift']:+.2f})"
            )
        print(f"[gate] {'PASS' if r['passed'] else 'FAIL'} — {r['reason']}")
        return 0 if r["passed"] else 1
    if args.cmd == "promote":
        for w in promote(Path(args.proposal), force=args.force):
            print(f"[promote] wrote {w}")
        return 0
    res = oracle(args.question, k=args.k, use_tapes=not args.no_tapes, model=args.model)
    print(json.dumps(res, indent=2) if args.json else format_oracle(res))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
