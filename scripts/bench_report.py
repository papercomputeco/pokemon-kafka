#!/usr/bin/env python3
"""Summarize a pi operator session into one benchmark row (see benchmarks/README.md).

    uv run python scripts/bench_report.py --label sonnet ~/.pi/agent/sessions/<slug>/*.jsonl

Model time is the latency before each assistant message; tool time is the latency before each
tool result. Tokens and cost are whatever the provider reported in each assistant message's
``usage``. Multiple files (a run resumed across sessions) are summed.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _load(path):
    rows = []
    for line in Path(path).read_text().splitlines():
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def summarize(paths) -> dict:
    """One aggregate row across the given session files."""
    turns = tools = errors = compactions = 0
    model_s = tool_s = wall_s = 0.0
    inp = out = cache = 0
    cost = 0.0
    max_ctx = 0
    for path in paths:
        rows = _load(path)
        compactions += sum(1 for r in rows if r.get("type") == "compaction")
        msgs = [r for r in rows if r.get("type") == "message"]
        if len(msgs) >= 2:
            wall_s += (_ts(msgs[-1]["timestamp"]) - _ts(msgs[0]["timestamp"])).total_seconds()
        for i, m in enumerate(msgs):
            role = m["message"].get("role")
            gap = (_ts(m["timestamp"]) - _ts(msgs[i - 1]["timestamp"])).total_seconds() if i else 0.0
            if role == "assistant":
                turns += 1
                model_s += gap
                u = m["message"].get("usage") or {}
                inp += u.get("input", 0)
                out += u.get("output", 0)
                cache += u.get("cacheRead", 0)
                cost += (u.get("cost") or {}).get("total", 0)
                max_ctx = max(max_ctx, u.get("input", 0) + u.get("cacheRead", 0))
                if m["message"].get("stopReason") == "error":
                    errors += 1
                tools += sum(1 for c in m["message"].get("content", []) if c.get("type") == "toolCall")
            elif role == "toolResult":
                tool_s += gap
    return {
        "turns": turns,
        "tools": tools,
        "wall_s": wall_s,
        "model_s": model_s,
        "tool_s": tool_s,
        "input": inp,
        "cache_read": cache,
        "output": out,
        "cost": round(cost, 4),
        "out_tok_s": round(out / model_s, 1) if model_s else 0.0,
        "s_per_turn": round(model_s / turns, 1) if turns else 0.0,
        "errors": errors,
        "compactions": compactions,
        "max_ctx": max_ctx,
    }


HEADER = (
    "| model | wall | model time | turns | tools | out tok/s | s/turn | input tok | cache read | output tok "
    "| cost | max ctx | errors | compactions |"
)


def _row(label, r) -> str:
    return (
        f"| {label} | {r['wall_s'] / 60:.1f} m | {r['model_s'] / 60:.1f} m | {r['turns']} | {r['tools']} "
        f"| {r['out_tok_s']} | {r['s_per_turn']} | {r['input']:,} | {r['cache_read']:,} | {r['output']:,} "
        f"| ${r['cost']:.2f} | {r['max_ctx']:,} | {r['errors']} | {r['compactions']} |"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="pi session -> benchmark row")
    parser.add_argument("paths", nargs="*", help="pi session .jsonl files (summed)")
    parser.add_argument("--label", default="model", help="row label")
    args = parser.parse_args(argv)
    if not args.paths:
        parser.print_usage()
        return 2
    print(HEADER)
    print("|" + "---|" * (HEADER.count("|") - 1))
    print(_row(args.label, summarize(args.paths)))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
