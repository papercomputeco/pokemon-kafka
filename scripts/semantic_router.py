#!/usr/bin/env python3
"""Semantic router — choose the right bot for the right situation (issue #103).

``references/semantic_router.yaml`` is the skill matrix (benchmarks/2026-08-22-skill-matrix.md)
and docs/model-fit.md rendered as a vllm-project/semantic-router config: keyword signals
classify a request into battle / navigation / puzzle and the matching decision names the
measured winner. The container serves it; this module keeps it honest:

* ``check``    — structural invariants (every decision cites a defined signal and model, the
                 default model exists, priorities are unique). Run by the tests.
* ``route``    — classify text offline with a faithful mirror of the keyword signals (presence
                 of any keyword, case-insensitive, approximating ``bm25_threshold: 0.1``); with
                 ``--live``, ask the running router on :8899 instead — the container is the
                 authority, the mirror is for tests and dry runs.
* ``missions`` — the routing table over ``docs/prompts/operator_prompt_skill_*.md``: which
                 model each skill mission would be handed to.
* ``register`` — add the router as a pi provider (``vllm-sr/auto`` on :8899/v1), the same
                 idempotent shape as ``local_models.py register``.
* ``serve``    — exec ``vllm-sr serve --config references/semantic_router.yaml`` (install the
                 CLI once with ``uv tool install vllm-sr``).

    uv run python scripts/semantic_router.py check
    uv run python scripts/semantic_router.py route "diagnose the spring anomaly on B1F"
    uv run python scripts/semantic_router.py route --live "same text, but ask the container"
    uv run python scripts/semantic_router.py missions
    uv run python scripts/semantic_router.py register
    uv run python scripts/semantic_router.py serve
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import urllib.request
from pathlib import Path

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
CONFIG_PATH = WORKSPACE / "references" / "semantic_router.yaml"
PROMPTS_DIR = WORKSPACE / "docs" / "prompts"
PI_MODELS_JSON = Path(os.environ.get("PI_MODELS_JSON", Path.home() / ".pi" / "agent" / "models.json"))
ROUTER_URL = os.environ.get("SEMANTIC_ROUTER_URL", "http://127.0.0.1:8899")
AUTO_MODEL = "vllm-sr/auto"


def load_config(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CONFIG_PATH).read_text())


# --------------------------------------------------------------------------- validation


def check(cfg: dict) -> list[str]:
    """Structural invariants. Returns problems; empty means the config is coherent."""
    problems: list[str] = []
    models = {m.get("name") for m in cfg.get("providers", {}).get("models", [])}
    default = cfg.get("providers", {}).get("defaults", {}).get("default_model")
    if not default:
        problems.append("providers.defaults.default_model is missing")
    elif default not in models:
        problems.append(f"default_model {default!r} is not in providers.models")

    routing = cfg.get("routing", {})
    signals = {s.get("name"): s for s in routing.get("signals", {}).get("keywords", [])}
    for name, sig in signals.items():
        if not sig.get("keywords"):
            problems.append(f"signal {name!r} has no keywords")

    decisions = routing.get("decisions", [])
    if not decisions:
        problems.append("routing.decisions is empty")
    priorities = [d.get("priority") for d in decisions]
    if len(set(priorities)) != len(priorities):
        problems.append(f"decision priorities are not unique: {priorities}")
    for d in decisions:
        dname = d.get("name", "?")
        for cond in d.get("rules", {}).get("conditions", []):
            if cond.get("name") not in signals:
                problems.append(f"decision {dname!r} references undefined signal {cond.get('name')!r}")
        refs = [r.get("model") for r in d.get("modelRefs", [])]
        if not refs:
            problems.append(f"decision {dname!r} has no modelRefs")
        for ref in refs:
            if ref not in models:
                problems.append(f"decision {dname!r} routes to undefined model {ref!r}")

    cards = {c.get("name") for c in routing.get("modelCards", [])}
    for missing in models - cards:
        problems.append(f"model {missing!r} has no modelCard")
    return problems


# --------------------------------------------------------------------------- offline mirror


def _signal_hits(sig: dict, text: str) -> list[str]:
    """Keywords present in *text* — case-insensitive substring, approximating an OR
    keyword signal at ``bm25_threshold: 0.1`` (any keyword present fires it)."""
    hay = text if sig.get("case_sensitive") else text.lower()
    hits = []
    for kw in sig.get("keywords", []):
        needle = kw if sig.get("case_sensitive") else kw.lower()
        if needle in hay:
            hits.append(kw)
    return hits


def classify(text: str, cfg: dict) -> tuple[str | None, str, list[str]]:
    """(decision name, model, matched keywords) for *text*; (None, default, []) when
    nothing fires. Mirrors ``strategy: priority`` — the highest-priority decision whose
    conditions all fire wins."""
    routing = cfg.get("routing", {})
    signals = {s.get("name"): s for s in routing.get("signals", {}).get("keywords", [])}
    for d in sorted(routing.get("decisions", []), key=lambda d: -d.get("priority", 0)):
        rules = d.get("rules", {})
        conditions = rules.get("conditions", [])
        hits_per_cond = [_signal_hits(signals.get(c.get("name"), {}), text) for c in conditions]
        fired = [bool(h) for h in hits_per_cond]
        ok = any(fired) if rules.get("operator") == "OR" else all(fired) and bool(fired)
        if conditions and ok:
            return d["name"], d["modelRefs"][0]["model"], sorted({k for h in hits_per_cond for k in h})
    return None, cfg["providers"]["defaults"]["default_model"], []


def route_live(text: str, url: str = ROUTER_URL) -> dict:
    """Ask the running container: one tiny completion with model "vllm-sr/auto"; the
    response's ``model`` field (and any x-vsr-* headers) says who was selected."""
    body = json.dumps({"model": AUTO_MODEL, "messages": [{"role": "user", "content": text}], "max_tokens": 1}).encode()
    req = urllib.request.Request(f"{url}/v1/chat/completions", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        headers = {k: v for k, v in resp.headers.items() if k.lower().startswith("x-vsr")}
        payload = json.loads(resp.read())
    return {"model": payload.get("model"), "headers": headers}


# --------------------------------------------------------------------------- commands


def cmd_check(args) -> int:
    problems = check(load_config(args.config))
    for p in problems:
        print(f"FAIL {p}")
    label = args.config or CONFIG_PATH.relative_to(WORKSPACE)
    print(f"{label}: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def cmd_route(args) -> int:
    text = Path(args.file).read_text() if args.file else args.text
    if not text:
        sys.exit("route: pass TEXT or --file")
    if args.live:
        out = route_live(text)
        print(f"live   model={out['model']}  {out['headers'] or ''}".rstrip())
        return 0
    decision, model, hits = classify(text, load_config(args.config))
    print(f"offline decision={decision or 'default'}  model={model}  matched={hits or '-'}")
    return 0


def cmd_missions(args) -> int:
    cfg = load_config(args.config)
    for path in sorted(PROMPTS_DIR.glob("operator_prompt_skill_*.md")):
        decision, model, _ = classify(path.read_text(), cfg)
        print(f"{path.name:40s} -> {model}  ({decision or 'default'})")
    return 0


def cmd_register(args) -> int:
    """Add the router as a pi provider (idempotent, same shape as local_models.register)."""
    cfg = load_config(args.config)
    ctx = min(c.get("context_window_size", 0) for c in cfg["routing"]["modelCards"])
    data = json.loads(PI_MODELS_JSON.read_text()) if PI_MODELS_JSON.exists() else {"providers": {}}
    prov = data.setdefault("providers", {}).setdefault(
        "vllm-sr",
        {
            "api": "openai-completions",
            "apiKey": "vllm-sr",
            "baseUrl": f"{ROUTER_URL}/v1",
            "compat": {"supportsDeveloperRole": False, "supportsReasoningEffort": False},
            "models": [],
        },
    )
    models = prov.setdefault("models", [])
    if any(m.get("id") == AUTO_MODEL for m in models):
        print(f"{AUTO_MODEL} already registered in {PI_MODELS_JSON}")
        return 0
    # The router picks the backend, so the entry advertises the smallest routed context —
    # a mission must fit whichever model the classifier lands on.
    models.append({"id": AUTO_MODEL, "contextWindow": ctx, "input": ["text"], "reasoning": False})
    PI_MODELS_JSON.write_text(json.dumps(data, indent=2) + "\n")
    print(f"registered {AUTO_MODEL} (ctx {ctx}) under provider vllm-sr in {PI_MODELS_JSON}")
    return 0


def cmd_serve(args) -> int:
    if not shutil.which("vllm-sr"):
        sys.exit("vllm-sr CLI not found — install it once with: uv tool install vllm-sr")
    os.execvp("vllm-sr", ["vllm-sr", "serve", "--config", str(args.config or CONFIG_PATH)])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", type=Path, default=None, help=f"config path (default {CONFIG_PATH})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    p = sub.add_parser("route")
    p.add_argument("text", nargs="?", default=None)
    p.add_argument("--file", default=None)
    p.add_argument("--live", action="store_true")
    sub.add_parser("missions")
    sub.add_parser("register")
    sub.add_parser("serve")
    args = ap.parse_args(argv)
    return {
        "check": cmd_check,
        "route": cmd_route,
        "missions": cmd_missions,
        "register": cmd_register,
        "serve": cmd_serve,
    }[args.cmd](args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
