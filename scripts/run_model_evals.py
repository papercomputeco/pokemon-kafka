#!/usr/bin/env python3
"""Score a *model* on the diagnoses this repo already knows the answer to (see evals/README.md).

``run_evals.py`` scores the headless agent — deterministic, no LLM. This scores the operator model
instead: each case is an obstacle from ``docs/learnings/`` replayed as a question whose real answer
is on record, plus a rubric of the claims that answer has to contain. It takes seconds per model
instead of the 2.5 h a relay run costs, so it can rank candidates before one gets a run slot.

    uv run python scripts/run_model_evals.py                          # every local -128k variant
    uv run python scripts/run_model_evals.py --models laguna-xs-128k  # explicit list
    uv run python scripts/run_model_evals.py --case flee-loop-cap --show

Scoring is deterministic regex matching (temperature 0, fixed seed), not an LLM judge: a rubric
item is worth its weight when any of its patterns appears in the answer, an ``anti`` item subtracts
its weight when it does. Score is ``max(0, hit) / total_weight``. That rewards *saying the true
thing*, so it is a floor on capability, not a ceiling — a model can be right in words the rubric
does not know. Read the saved answers (``--out-dir``) before trusting a low score, and treat the
column as a screen, not a verdict.

A case with no visible answer (the model spent its whole budget in the ``thinking`` field) is
reported as ``trunc`` per-case and scored **0** in the overall — silence is a failure mode, not an
excused absence.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
DEFAULT_CASES = WORKSPACE / "evals" / "model-cases"
DEFAULT_RESULTS = WORKSPACE / "evals" / "results"
DEFAULT_OUT = WORKSPACE / "data" / "evals" / "model"
OLLAMA_URL = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
GPU_LOCK = WORKSPACE / "data" / "local_runs" / "GPU_BUSY"


def check_gpu_free(force: bool = False) -> None:
    """Refuse to load models while scripts/local_relay_run.sh owns the card (see the lock's contents).
    Loading a second model evicts the relay's model mid-stream and kills the run — an invalid row that
    looks like the model quitting. Override with --force-gpu / ADVISOR_FORCE_GPU=1 only if you know."""
    if force or os.environ.get("ADVISOR_FORCE_GPU") == "1" or not GPU_LOCK.exists():
        return
    raise SystemExit(
        f"GPU busy — a relay run owns the card ({GPU_LOCK.read_text().strip()}); wait for it or --force-gpu"
    )


SYSTEM = (
    "You are the operator agent for a Pokemon Red speedrun harness: a Python codebase that drives "
    "PyBoy, publishes telemetry to Kafka, and records what it learns in docs/learnings/. Answer as "
    "an engineer debugging your own repo — concrete, specific, and short. No preamble."
)


def load_cases(cases_dir: Path, only: str | None = None) -> list[dict]:
    cases = [json.loads(p.read_text()) for p in sorted(Path(cases_dir).glob("*.json"))]
    return [c for c in cases if only is None or c["name"] == only]


def read_context(entry: dict, workspace: Path = WORKSPACE) -> str:
    """One context block: a file excerpt by line range, labelled for the prompt."""
    path = workspace / entry["path"]
    lines = path.read_text().splitlines()
    start = max(1, int(entry.get("start", 1)))
    end = min(len(lines), int(entry.get("end", len(lines))))
    body = "\n".join(f"{n:5d}  {lines[n - 1]}" for n in range(start, end + 1))
    return f"--- {entry.get('label', entry['path'])} ---\n{body}\n"


def build_prompt(case: dict, workspace: Path = WORKSPACE) -> str:
    blocks = [read_context(c, workspace) for c in case.get("context", [])]
    return case["prompt"] if not blocks else case["prompt"] + "\n\n" + "\n".join(blocks)


def _hit(patterns: list[str], text: str) -> str | None:
    for p in patterns:
        if re.search(p, text, re.IGNORECASE | re.MULTILINE):
            return p
    return None


def score_answer(case: dict, answer: str) -> dict:
    """Weighted rubric match; ``anti`` items subtract. Returns score, and what hit/missed."""
    total = sum(item["weight"] for item in case.get("rubric", [])) or 1
    earned, hits, misses, antis = 0, [], [], []
    for item in case.get("rubric", []):
        if _hit(item["any"], answer):
            earned += item["weight"]
            hits.append(item["id"])
        else:
            misses.append(item["id"])
    for item in case.get("anti", []):
        if _hit(item["any"], answer):
            earned -= item["weight"]
            antis.append(item["id"])
    return {
        "score": round(max(0, earned) / total, 3),
        "earned": earned,
        "total": total,
        "hits": hits,
        "misses": misses,
        "antis": antis,
    }


def ask_ollama(
    model: str,
    prompt: str,
    *,
    ctx: int,
    num_predict: int,
    seed: int,
    timeout: float = 900.0,
    system: str = SYSTEM,
) -> dict:
    """One chat completion. ``system`` is overridable so the advisor's gate can inject a tip."""
    payload = {
        "model": model,
        "stream": False,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "options": {"temperature": 0, "seed": seed, "num_ctx": ctx, "num_predict": num_predict},
    }
    req = urllib.request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    msg = body.get("message", {}) or {}
    # Thinking models put the chain of thought in a separate field; score the visible answer, but
    # keep the thinking for the saved transcript (a model that reasons right and answers vaguely is
    # a prompt problem, not a capability one, and the transcript is how you tell).
    return {
        "answer": msg.get("content", "") or "",
        "thinking": msg.get("thinking", "") or "",
        "wall_s": round(time.time() - t0, 1),
        "out_tok": body.get("eval_count", 0),
        "out_tok_s": round(body["eval_count"] / (body["eval_duration"] / 1e9), 1) if body.get("eval_duration") else 0.0,
    }


def local_variants(ctx: int) -> list[str]:
    """Every ``-<ctx>k`` model Ollama has, i.e. what local_models.py created."""
    suffix = f"-{ctx // 1024}k"
    try:
        with urllib.request.urlopen(OLLAMA_URL + "/api/tags", timeout=30) as resp:
            names = [m["name"] for m in json.loads(resp.read().decode()).get("models", [])]
    except OSError:
        return []
    return sorted(n for n in names if n.split(":")[0].endswith(suffix))


HEADER = "| model | overall | {cases} | no answer | out tok/s | wall s |"


def _append_results(results_dir: Path, rows: list[dict], case_names: list[str], ctx: int) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    path = results_dir / f"models-{now:%Y-%m-%d}.md"
    out = []
    if not path.exists():
        out.append(f"# Model eval results — {now:%Y-%m-%d}\n")
        out.append(
            "\nLearnings-derived diagnostic cases scored by rubric match (see "
            "`scripts/run_model_evals.py`). Screen, not verdict — read the saved answers.\n"
        )
    out.append(f"\n## {now:%H:%M}Z — {ctx // 1024}k ctx, temperature 0\n")
    out.append(HEADER.format(cases=" | ".join(case_names)))
    out.append("|" + "---|" * (len(case_names) + 5))
    for r in sorted(rows, key=lambda r: -r["overall"]):
        cells = " | ".join("trunc" if r["scores"].get(c) is None else f"{r['scores'][c]:.2f}" for c in case_names)
        out.append(
            f"| {r['model']} | **{r['overall']:.2f}** | {cells} | {r.get('truncated', 0)} "
            f"| {r['out_tok_s']} | {r['wall_s']} |"
        )
    path.write_text((path.read_text() if path.exists() else "") + "\n".join(out) + "\n")
    return path


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Score models on learnings-derived diagnostic cases")
    p.add_argument("--cases", default=str(DEFAULT_CASES))
    p.add_argument("--case", default=None, help="run one case by name")
    p.add_argument("--models", default=None, help="comma-separated model names (default: every -<ctx>k variant)")
    p.add_argument("--ctx", type=int, default=131072)
    p.add_argument(
        "--num-predict",
        type=int,
        default=4000,
        help="output budget; thinking models spend most of it before the visible answer starts",
    )
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--out-dir", default=str(DEFAULT_OUT), help="where full answers are saved")
    p.add_argument("--results-dir", default=str(DEFAULT_RESULTS))
    p.add_argument("--show", action="store_true", help="print each answer as it arrives")
    p.add_argument("--force-gpu", action="store_true", help="run even if a relay run owns the GPU")
    args = p.parse_args(argv)
    check_gpu_free(args.force_gpu)

    cases = load_cases(Path(args.cases), only=args.case)
    if not cases:
        print("no cases found", file=sys.stderr)
        return 2
    models = args.models.split(",") if args.models else local_variants(args.ctx)
    if not models:
        print("no models found — run `local_models.py create` first", file=sys.stderr)
        return 2

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_dir = Path(args.out_dir) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    case_names = [c["name"] for c in cases]
    rows = []
    for model in models:
        scores, tok_s, wall = {}, [], 0.0
        for case in cases:
            prompt = build_prompt(case)
            try:
                got = ask_ollama(
                    model,
                    prompt,
                    ctx=args.ctx,
                    # long cases can declare their own budget; thinking eats the default
                    num_predict=int(case.get("num_predict", args.num_predict)),
                    seed=args.seed,
                )
            except OSError as e:
                print(f"[eval] {model} {case['name']}: ERROR {str(e)[:120]}", flush=True)
                scores[case["name"]] = 0.0
                continue
            truncated = not got["answer"].strip() and bool(got["thinking"].strip())
            verdict = score_answer(case, got["answer"])
            # A model that burned the whole budget thinking has not answered *badly* — it has not
            # answered. Scoring that 0 would rank it below a wrong answer, so record it separately.
            scores[case["name"]] = None if truncated else verdict["score"]
            tok_s.append(got["out_tok_s"])
            wall += got["wall_s"]
            safe = model.replace(":", "_").replace("/", "_")
            shown_score = "truncated (no visible answer)" if truncated else verdict["score"]
            (out_dir / f"{safe}__{case['name']}.md").write_text(
                f"# {model} — {case['name']}\n\nscore {shown_score} "
                f"(hits: {', '.join(verdict['hits']) or '-'}; misses: {', '.join(verdict['misses']) or '-'}; "
                f"anti: {', '.join(verdict['antis']) or '-'})\n\n## answer\n\n{got['answer']}\n"
                + (f"\n## thinking\n\n{got['thinking']}\n" if got["thinking"] else "")
            )
            shown = "trunc" if truncated else f"{verdict['score']:.2f}"
            print(
                f"[eval] {model:32} {case['name']:28} {shown:>5} "
                f"(-{','.join(verdict['antis']) or ''}) {got['out_tok_s']} tok/s",
                flush=True,
            )
            if args.show:
                print(got["answer"][:2000] + "\n---")
        # Truncation counts as 0 in the overall, not as an excused absence: on the real harness a
        # turn that produces no visible action is a wasted turn (Gemma's 2026-08-15 run exited on a
        # thinking-only turn). Averaging only the answered cases would rank silence above wrongness.
        scored = [0.0 if v is None else v for v in scores.values()]
        rows.append(
            {
                "model": model,
                "scores": scores,
                "truncated": sum(1 for v in scores.values() if v is None),
                "overall": round(sum(scored) / len(cases), 3) if cases else 0.0,
                "out_tok_s": round(sum(tok_s) / len(tok_s), 1) if tok_s else 0.0,
                "wall_s": round(wall, 1),
            }
        )
    path = _append_results(Path(args.results_dir), rows, case_names, args.ctx)
    print(f"[eval] answers in {out_dir}, table appended to {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
