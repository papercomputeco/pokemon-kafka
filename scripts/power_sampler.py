#!/usr/bin/env python3
"""Sample local power draw while a run is in flight (see benchmarks/README.md).

    uv run python scripts/power_sampler.py --out data/power/<run>.csv --interval 5

Columns: ts (seconds), gpu_w (nvidia-smi power.draw — the discrete GPU Ollama runs on),
other_w (amdgpu hwmon, i.e. the iGPU), cpu_w (RAPL package energy delta ÷ interval; blank when
the counter is root-only, as it is on stock Ubuntu). Feed the CSV to
``bench_report.py --power-log`` to get Wh and $/kWh columns. Stop with Ctrl-C or --max-samples.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

HWMON = Path("/sys/class/hwmon")
RAPL = Path("/sys/class/powercap")


def _run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False).stdout


def read_gpu_watts():
    try:
        out = _run(["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"])
        return float(out.strip().splitlines()[0])
    except (OSError, ValueError, IndexError):
        return None


def read_hwmon_watts(root=None):
    """Sum of amdgpu hwmon power1_input (microwatts) — the iGPU on this box."""
    total = None
    for h in sorted(Path(root or HWMON).glob("hwmon*")):
        try:
            if (h / "name").read_text().strip() != "amdgpu":
                continue
            uw = float((h / "power1_input").read_text().strip())
        except (OSError, ValueError):
            continue
        total = (total or 0.0) + uw / 1_000_000
    return total


def read_rapl_joules(root=None):
    """CPU package energy counter in joules, or None when absent/unreadable."""
    p = Path(root or RAPL) / "intel-rapl:0" / "energy_uj"
    try:
        return float(p.read_text().strip()) / 1_000_000
    except (OSError, ValueError):
        return None


def sample_loop(out, interval=5.0, max_samples=None, clock=time.time):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    last_j = last_t = None
    with open(out, "w") as f:
        f.write("ts,gpu_w,other_w,cpu_w\n")
        while max_samples is None or n < max_samples:
            t = clock()
            gpu = read_gpu_watts()
            other = read_hwmon_watts()
            j = read_rapl_joules()
            cpu = ""
            if j is not None and last_j is not None and t > last_t:
                cpu = f"{(j - last_j) / (t - last_t):.1f}"
            last_j, last_t = j, t
            f.write(f"{t},{'' if gpu is None else gpu},{'' if other is None else other},{cpu}\n")
            f.flush()
            n += 1
            if max_samples is None or n < max_samples:
                time.sleep(interval)
    return n


def main(argv=None):
    parser = argparse.ArgumentParser(description="Sample GPU/iGPU/CPU power to CSV")
    parser.add_argument("--out", required=True)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--max-samples", type=int, default=None)
    args = parser.parse_args(argv)
    n = sample_loop(args.out, interval=args.interval, max_samples=args.max_samples)
    print(f"[power] {n} samples -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
