#!/usr/bin/env python3
"""Model fit as context: render a per-model section for the mission, and keep it measured.

The verdicts in docs/model-fit.md are knowledge from other runs, so a run that carries them is an
*assisted* row (benchmarks/README.md, "Assisted vs unassisted rows"). This makes that a mode the
launchers can label — `ASSIST=fit` — and a question the gate can answer: does telling a Driver to
probe change its probe/relay?

    uv run python scripts/model_fit.py section haiku-4-5        # text the launcher appends to the mission
    uv run python scripts/model_fit.py update <session.jsonl>... # fold role_metrics into `measured`
    uv run python scripts/model_fit.py show                       # table of every model's verdict + measured

`section` prints nothing for an unknown model (an unlisted model runs unassisted, and the launcher
says so), so adding a model to the roster never silently changes its row.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

FIT_PATH = Path(__file__).resolve().parent.parent / "references" / "model_fit.json"


def load(path: Path | None = None) -> dict:
    return json.loads((path or FIT_PATH).read_text())


def resolve(models: dict, name: str) -> str | None:
    """Map a launcher model name to a fit key: exact, then the key that is a prefix of the name."""
    if name in models:
        return name
    n = name.lower()
    for key in sorted(models, key=len, reverse=True):
        if n.startswith(key) or key in n:
            return key
    return None


def section(name: str, path: Path | None = None) -> str:
    d = load(path)
    key = resolve(d["models"], name)
    if key is None:
        return ""
    m = d["models"][key]
    strong = ", ".join(m.get("strong", [])) or "—"
    weak = ", ".join(m.get("weak", [])) or "—"
    lines = [
        "## Operator notes for this model (ASSIST=fit — this row is assisted; compare only with other assisted rows)",
        f"Measured over earlier runs of this model: strong as **{strong}**; weak as **{weak}**. "
        "These are tendencies, not rules — the point is to notice when you are about to do the weak thing.",
    ]
    lines += [f"- {g}" for g in m.get("guidance", [])]
    meas = m.get("measured") or {}
    if meas.get("sessions"):
        lines.append(
            f"- Your numbers so far ({meas['sessions']} sessions): probe/relay {meas.get('probe_per_relay')}, "
            f"calls before first relay {meas.get('calls_before_first_relay')}, early exit in "
            f"{meas.get('early_exit_sessions')} of {meas['sessions']}."
        )
    return "\n".join(lines) + "\n"


def update(sessions: list[str], path: Path | None = None, repo: Path | None = None) -> dict:
    """Fold role_metrics over the sessions into each model's `measured` block. Returns the new doc."""
    import role_metrics

    p = path or FIT_PATH
    d = load(p)
    rows = []
    for s in sessions:
        sp = Path(s).expanduser()
        if not sp.exists():
            continue
        sig = role_metrics.parse_claude(sp) if sp.name.endswith(".claude.jsonl") else role_metrics.parse_pi(sp)
        rows.append(sig)
    by_key: dict[str, list] = {}
    for sig in rows:
        key = resolve(d["models"], sig.model) or resolve(d["models"], sig.label)
        if key:
            by_key.setdefault(key, []).append(sig)
    for key, sigs in by_key.items():
        relays = sum(s.relay_calls for s in sigs)
        probes = sum(s.probe_calls for s in sigs)
        early = sum(1 for s in sigs if s.ended_by_choice and 0 < s.wall_min < 90)
        d["models"][key]["measured"] = {
            "sessions": len(sigs),
            "probe_per_relay": round(probes / relays, 2) if relays else None,
            "calls_before_first_relay": round(sum(s.calls_before_first_relay or 0 for s in sigs) / len(sigs), 1),
            "code_files_edited_per_session": round(sum(len(s.code_files_edited) for s in sigs) / len(sigs), 1),
            "early_exit_sessions": early,
            "labels": sorted(s.label for s in sigs),
        }
    p.write_text(json.dumps(d, indent=2) + "\n")
    return d


def show(path: Path | None = None) -> str:
    d = load(path)
    out = [
        "| model | harness | strong | weak | sessions | probe/relay | calls→1st relay | early exits |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for key, m in d["models"].items():
        me = m.get("measured") or {}
        strong = ", ".join(m.get("strong", [])) or "—"
        weak = ", ".join(m.get("weak", [])) or "—"
        cells = [
            key,
            m.get("harness", "?"),
            strong,
            weak,
            me.get("sessions", "—"),
            me.get("probe_per_relay", "—"),
            me.get("calls_before_first_relay", "—"),
            me.get("early_exit_sessions", "—"),
        ]
        out.append("| " + " | ".join(str(c) for c in cells) + " |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("section")
    s.add_argument("model")
    u = sub.add_parser("update")
    u.add_argument("sessions", nargs="+")
    sub.add_parser("show")
    ap.add_argument("--fit", default=str(FIT_PATH))
    args = ap.parse_args(argv)
    fit = Path(args.fit)
    if args.cmd == "section":
        sys.stdout.write(section(args.model, fit))
    elif args.cmd == "update":
        d = update(args.sessions, fit)
        sys.stdout.write(show(fit))
        return 0 if d else 1
    else:
        sys.stdout.write(show(fit))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
