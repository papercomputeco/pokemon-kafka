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
    inp = out = cache = cache_w = 0
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
                cache_w += u.get("cacheWrite", 0)
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
        "cache_write": cache_w,
        "output": out,
        "cost": round(cost, 4),
        "out_tok_s": round(out / model_s, 1) if model_s else 0.0,
        "s_per_turn": round(model_s / turns, 1) if turns else 0.0,
        "errors": errors,
        "compactions": compactions,
        "max_ctx": max_ctx,
    }


def cloud_cost(row, rates) -> float:
    """USD at published per-million-token cloud rates — the cost of this run *at scale*.

    ``rates`` keys: in, out, cache_read, cache_write ($/M). Local and subscription runs report
    $0 from the provider; pricing them at cloud rates makes rows comparable.
    """
    m = 1_000_000
    return round(
        row["input"] / m * rates.get("in", 0)
        + row["cache_read"] / m * rates.get("cache_read", 0)
        + row.get("cache_write", 0) / m * rates.get("cache_write", 0)
        + row["output"] / m * rates.get("out", 0),
        4,
    )


def energy_wh(power_log) -> float:
    """Integrate a power_sampler.py CSV (ts_seconds, gpu_w, other_w) into watt-hours (trapezoid)."""
    path = Path(power_log)
    if not path.exists():
        return 0.0
    pts = []
    for line in path.read_text().splitlines()[1:]:
        parts = line.split(",")
        try:
            t = float(parts[0])
            w = sum(float(x) for x in parts[1:] if x.strip())
        except (ValueError, IndexError):
            continue
        pts.append((t, w))
    wh = 0.0
    for (t0, w0), (t1, w1) in zip(pts, pts[1:]):
        wh += (w0 + w1) / 2 * (t1 - t0) / 3600
    return wh


HEADER = (
    "| model | wall | model time | turns | tools | out tok/s | s/turn | input tok | cache read | output tok "
    "| provider $ | cloud $ | Wh | energy $ | max ctx | errors | compactions |"
)


def _row(label, r, cloud=0.0, wh=0.0, kwh_price=0.0) -> str:
    return (
        f"| {label} | {r['wall_s'] / 60:.1f} m | {r['model_s'] / 60:.1f} m | {r['turns']} | {r['tools']} "
        f"| {r['out_tok_s']} | {r['s_per_turn']} | {r['input']:,} | {r['cache_read']:,} | {r['output']:,} "
        f"| ${r['cost']:.2f} | ${cloud:.4f} | {wh:.1f} | ${wh / 1000 * kwh_price:.4f} "
        f"| {r['max_ctx']:,} | {r['errors']} | {r['compactions']} |"
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="pi session -> benchmark row")
    parser.add_argument("paths", nargs="*", help="pi session .jsonl files (summed)")
    parser.add_argument("--label", default="model", help="row label")
    parser.add_argument("--rate-in", type=float, default=0.0, help="cloud $/M input tokens")
    parser.add_argument("--rate-out", type=float, default=0.0, help="cloud $/M output tokens")
    parser.add_argument("--rate-cache-read", type=float, default=0.0, help="cloud $/M cache-read tokens")
    parser.add_argument("--rate-cache-write", type=float, default=0.0, help="cloud $/M cache-write tokens")
    parser.add_argument("--power-log", default=None, help="power_sampler.py CSV for this run")
    parser.add_argument("--kwh-price", type=float, default=0.0, help="$ per kWh for the energy $ column")
    args = parser.parse_args(argv)
    if not args.paths:
        parser.print_usage()
        return 2
    print(HEADER)
    print("|" + "---|" * (HEADER.count("|") - 1))
    r = summarize(args.paths)
    rates = {
        "in": args.rate_in,
        "out": args.rate_out,
        "cache_read": args.rate_cache_read,
        "cache_write": args.rate_cache_write,
    }
    wh = energy_wh(args.power_log) if args.power_log else 0.0
    print(_row(args.label, r, cloud=cloud_cost(r, rates), wh=wh, kwh_price=args.kwh_price))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
