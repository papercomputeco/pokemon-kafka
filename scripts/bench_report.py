#!/usr/bin/env python3
"""Summarize a pi operator session into one benchmark row (see benchmarks/README.md).

    uv run python scripts/bench_report.py --label sonnet ~/.pi/agent/sessions/<slug>/*.jsonl

Model time is the latency before each assistant message; tool time is the latency before each
tool result. Tokens and cost are whatever the provider reported in each assistant message's
``usage``. Multiple files (a run resumed across sessions) are summed.
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
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


# --- harness-death guard ---------------------------------------------------------------------
# A local run can be killed by the box rather than the model, and from pi's side the two look
# identical: the stream goes silent and the last turn is recorded as a normal ``stopReason: stop``
# with usage 0/0 and nothing said. Three qwen38-27b runs were lost this way to eGPU hangs
# (``NVRM: Xid 8``) and one to a self-inflicted model eviction — see
# benchmarks/2026-08-16-qwen38-27b-egpu-hangs.md. Publishing any of them as a row would have read
# as "the model quit at 3 minutes", so the rule is: no row until the logs are clean for the run's
# window.

KERNEL_HANG = ("NVRM: Xid", "GPU is probably locked", "GPU has fallen off the bus")
OLLAMA_HANG = ("CUDA error", "llama-server terminated", "core dumped")


def _journal(cmd):
    """Run a journalctl query. ``None`` means the journal could not be read — never 'clean'."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout if p.returncode == 0 else None


def run_window(paths):
    """(first, last) message timestamp across the session files; (None, None) if there are none."""
    stamps = [_ts(r["timestamp"]) for path in paths for r in _load(path) if r.get("type") == "message"]
    return (min(stamps), max(stamps)) if stamps else (None, None)


def _hits(text, needles):
    return [ln for ln in (text or "").splitlines() if any(n in ln for n in needles)]


def gpu_hangs(start, end, *, kernel_log=None, ollama_log=None, pad_s=120.0, runner=_journal) -> dict:
    """Kernel Xids and Ollama CUDA crashes inside the run window, extended ``pad_s`` past its end.

    The window starts exactly at the first message and is padded only *forward*: the hang that kills
    a run is logged at or just after its last turn (r4: last turn 10:14:16, ``Xid`` 10:14:16), while
    a crash from the run *before* this one cannot have killed it. Padding backwards instead flagged
    the healthy `laguna-xs` r1 row, which started two seconds after the previous model's Xid.

    A source is ``clean``, ``hang`` or ``unavailable``; an unreadable journal is never ``clean``,
    because "we did not look" and "we looked and it was fine" certify different things. Pass an
    already-windowed capture with ``kernel_log``/``ollama_log`` (what ``local_relay_run.sh`` saves)
    to make the check reproducible after the journal has rotated.
    """
    out = {}
    for name, log, sel, needles in (
        ("kernel", kernel_log, ["-k"], KERNEL_HANG),
        ("ollama", ollama_log, ["-u", "ollama"], OLLAMA_HANG),
    ):
        if log:
            path = Path(log)
            text = path.read_text() if path.exists() else None
        elif start:
            span = [
                "--since",
                start.astimezone().strftime("%Y-%m-%d %H:%M:%S"),
                "--until",
                (end + timedelta(seconds=pad_s)).astimezone().strftime("%Y-%m-%d %H:%M:%S"),
            ]
            text = runner(["journalctl", *sel, *span, "--no-pager"])
        else:
            text = None
        lines = _hits(text, needles)
        status = "unavailable" if text is None else ("hang" if lines else "clean")
        out[name] = {"status": status, "lines": lines}
    return out


def dead_stream(paths):
    """The signature of a killed stream, or None: a final assistant turn that said nothing.

    ``stopReason`` is whatever the provider managed to write (``stop`` for a mid-generation CUDA
    abort), so the tell is usage 0/0 with no text and no tool call — thinking cut mid-sentence.
    """
    msgs = [r for path in paths for r in _load(path) if r.get("type") == "message"]
    if not msgs:
        return None
    last = msgs[-1]["message"]
    usage = last.get("usage") or {}
    said = any(c.get("type") in ("text", "toolCall") for c in last.get("content") or [])
    if last.get("role") != "assistant" or said or usage.get("input", 0) or usage.get("output", 0):
        return None
    return f"dead stream — last assistant turn: stopReason={last.get('stopReason')!r}, usage 0/0, nothing said"


def harness_death(paths, **kw) -> dict:
    """``reasons`` this session must not become a row, and ``notes`` for checks that could not run."""
    reasons, notes = [], []
    dead = dead_stream(paths)
    if dead:
        reasons.append(dead)
    start, end = run_window(paths)
    for name, res in gpu_hangs(start, end, **kw).items():
        if res["status"] == "hang":
            reasons.append(f"{name} log, in the run window: " + " | ".join(res["lines"][:3]))
        elif res["status"] == "unavailable":
            notes.append(f"{name} log not checked (journal unreadable) — this row is not certified clean")
    return {"reasons": reasons, "notes": notes}


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


def main(argv=None, runner=_journal) -> int:
    parser = argparse.ArgumentParser(description="pi session -> benchmark row")
    parser.add_argument("paths", nargs="*", help="pi session .jsonl files (summed)")
    parser.add_argument("--label", default="model", help="row label")
    parser.add_argument("--rate-in", type=float, default=0.0, help="cloud $/M input tokens")
    parser.add_argument("--rate-out", type=float, default=0.0, help="cloud $/M output tokens")
    parser.add_argument("--rate-cache-read", type=float, default=0.0, help="cloud $/M cache-read tokens")
    parser.add_argument("--rate-cache-write", type=float, default=0.0, help="cloud $/M cache-write tokens")
    parser.add_argument("--power-log", default=None, help="power_sampler.py CSV for this run")
    parser.add_argument("--kwh-price", type=float, default=0.0, help="$ per kWh for the energy $ column")
    parser.add_argument("--kernel-log", default=None, help="captured kernel log (else journalctl -k)")
    parser.add_argument("--ollama-log", default=None, help="captured Ollama log (else journalctl -u ollama)")
    parser.add_argument("--hang-pad", type=float, default=120.0, help="seconds of slack after the run's last turn")
    parser.add_argument("--no-hang-check", action="store_true", help="skip the harness-death guard")
    parser.add_argument("--force", action="store_true", help="emit the row even if the run died on the harness")
    args = parser.parse_args(argv)
    if not args.paths:
        parser.print_usage()
        return 2
    if not args.no_hang_check:
        death = harness_death(
            args.paths,
            kernel_log=args.kernel_log,
            ollama_log=args.ollama_log,
            pad_s=args.hang_pad,
            runner=runner,
        )
        for note in death["notes"]:
            print(f"note: {note}", file=sys.stderr)
        if death["reasons"]:
            print("NO ROW — this run died on the harness, not on the model:", file=sys.stderr)
            for reason in death["reasons"]:
                print(f"  ! {reason}", file=sys.stderr)
            if not args.force:
                print(
                    "Write the attempt up instead of publishing a row (see "
                    "benchmarks/2026-08-16-qwen38-27b-egpu-hangs.md); --force to emit anyway.",
                    file=sys.stderr,
                )
                return 3
            print("  (--force: emitting anyway — label the row as an invalid attempt)", file=sys.stderr)
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
