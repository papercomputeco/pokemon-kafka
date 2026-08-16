#!/usr/bin/env python3
"""Local (Ollama / RTX 5090) model roster for operator-agent runs.

The point of local rows in ``benchmarks/`` is to find out whether an open model that runs on the
box — pushing the GPU's power budget — gets comparable to Haiku 4.5 (91.9 out tok/s, 4.8 s/turn,
2/4 Mt. Moon segments). Two things bit the 2026-08-15 local runs and are handled here:

* Ollama's default ``num_ctx`` (4k) silently truncates the *front* of the prompt (the mission),
  so every roster model gets a ``<alias>-<ctx>k`` variant with an explicit ``num_ctx``
  (128k by default; needs ``OLLAMA_FLASH_ATTENTION=1`` + ``OLLAMA_KV_CACHE_TYPE=q8_0`` on the
  service to fit next to a 20 GB model — see ``scripts/ollama-ctx.conf``).
* Neither pi nor Ollama tells you when a model spilled to CPU; ``--bench`` reports the
  ``ollama ps`` GPU/CPU split, VRAM, decode tok/s and peak watts so a row can be judged
  before a 2.5 h run is spent on it.

    uv run python scripts/local_models.py list                 # roster + what is pulled / creatable
    uv run python scripts/local_models.py pull [alias...]      # ollama pull the base tags
    uv run python scripts/local_models.py create [alias...]    # build the -128k variants (Modelfiles)
    uv run python scripts/local_models.py register             # add variants to ~/.pi/agent/models.json
    uv run python scripts/local_models.py bench [alias...]     # tok/s, VRAM, GPU split, peak W

``--ctx`` (default 131072 = 128k) is the harness constant; keep it identical across models you compare.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

OLLAMA_URL = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
PI_MODELS_JSON = Path(os.environ.get("PI_MODELS_JSON", Path.home() / ".pi" / "agent" / "models.json"))
DEFAULT_CTX = 131072


@dataclass(frozen=True)
class Spec:
    alias: str  # short name used for the -<ctx>k variant and in benchmark tables
    tag: str  # ollama library tag
    group: str  # comparison class — only compare rows inside a group (see GROUPS)
    note: str
    reasoning: bool = True
    vision: bool = False
    params: dict = field(default_factory=dict)  # extra Modelfile PARAMETERs (sampling defaults)


# Comparison classes. Decode speed tracks *active* parameters and residency, not total size, so a
# 30B-A3B MoE and a 27B dense model are different questions even though both "fit". Compare rows
# within a group; across groups, read the group description first.
GROUPS: dict[str, str] = {
    "moe-30b": "sparse MoE, ~30B total / ~3B active — the fast lane: dense-model knowledge, small-model decode",
    "dense-27b": "dense 27-35B — slower per token, stronger single-pass reasoning; the honest 'big local model' test",
    "baseline": "already benched on 2026-08-15 at 64k ctx; kept so `bench` can rebaseline them at 128k",
}

# Every entry must run on this box: Blackwell (RTX 5090, 32 GB), CUDA, Linux, fully GPU-resident at
# DEFAULT_CTX. Two exclusion rules keep it that way:
#   1. Apple-only distribution formats — ``mlx`` builds, and (counter-intuitively) the Blackwell
#      ``nvfp4`` FP4 builds, which Ollama's registry 412s on Linux with "this model requires macOS"
#      (checked 2026-08-15). ``check_runnable`` blocks both before a pull wastes bandwidth.
#   2. Models whose weights + a 128k q8_0 KV cache do not fit in 32 GB.
#   3. Models removed by decision after a run: ``qwen3-coder:30b`` (2026-08-16) — fastest good decoder
#      and second on the eval quiz, but as the autonomous operator it went 0/4 in 12 min, never
#      opened agent.py, shortened the timeout, fabricated Brock/Route 3 learnings and declared
#      success. Tuned to edit code it is pointed at, no thinking mode; a fixer, not an investigator.
#      See benchmarks/2026-08-16-local-relay-qwen3-coder.md. Kept in RETIRED so `list` can say why.
#   (Rule 2 example: ``qwen3:8b`` — native context 40k, so 128k of KV is bigger than the model and it
#   spills to CPU: 81 % resident, 48 tok/s, slower than models 4x its size.)
# Sizes are the on-disk quant published on ollama.com (2026-08); ``bench`` is the ground truth.
MACOS_ONLY_MARKERS: tuple[str, ...] = ("mlx", "nvfp4")
ROSTER: tuple[Spec, ...] = (
    # --- moe-30b: ~3B active, expected 240-300 tok/s -------------------------------------------
    Spec("glm47-flash", "glm-4.7-flash", "moe-30b", "GLM-4.7-Flash 30B MoE Q4, 19 GB — tools+thinking"),
    Spec("gpt-oss-20b", "gpt-oss:20b", "moe-30b", "OpenAI gpt-oss 20B MXFP4 native, 14 GB — cheap reasoning"),
    Spec(
        "nemotron35-lightning",
        "nemotron-3.5-lightning:30b-a3b",
        "moe-30b",
        "NVIDIA 30B-A3B MoE for always-on agents, 25 GB",
    ),
    # --- dense-27b: full-weight decode every token ----------------------------------------------
    Spec("qwen38-27b", "qwen3.8:27b", "dense-27b", "Qwen3.8 27B dense, 18 GB — newest Qwen, long-horizon agentic"),
    Spec("qwen36-35b", "qwen3.6:35b", "dense-27b", "Qwen3.6 35B, 24 GB — the previous generation at full size"),
    Spec(
        "muse-glimmer",
        "muse-glimmer:30b",
        "dense-27b",
        "27.9B tuned for tool use and failure recovery, 18 GB — branded 30B, decodes dense (81 tok/s)",
    ),
    Spec(
        "gemma4-31b", "gemma4:31b", "dense-27b", "Gemma 4 31B, 20 GB — the big sibling of the E4B baseline", vision=True
    ),
    # --- baseline: the 2026-08-15 rows ----------------------------------------------------------
    Spec(
        "qwen35b", "qwen3.5:35b", "baseline", "35B-A3B MoE Q4_K_M, 23 GB — 2026-08-15 row (20 tok/s, truncated at 64k)"
    ),
    Spec("gemma4", "gemma4:latest", "baseline", "Gemma 4 E4B, 9.6 GB — 2026-08-15 row (143 tok/s, tiny)"),
)
BY_ALIAS = {s.alias: s for s in ROSTER}

# Removed from the roster on purpose; alias -> reason. Their benchmark rows stay in benchmarks/.
RETIRED: dict[str, str] = {
    "qwen3-coder-30b": "0/4 relay in 12 min: fabricated learnings, no investigation (2026-08-16)",
}


def check_runnable(tag: str) -> str | None:
    """Reason this tag cannot run on the Blackwell/CUDA/Linux box, or None if it can."""
    for marker in MACOS_ONLY_MARKERS:
        if marker in tag.rsplit(":", 1)[-1].split("-"):
            return f"{marker} builds are macOS-only in Ollama's registry (412) — not runnable on Blackwell/Linux"
    return None


# What a local row has to beat to be "comparable to Haiku" (2026-08-15 Mt. Moon relay).
HAIKU_REF = {"out_tok_s": 91.9, "s_per_turn": 4.8, "segs": "2/4", "cloud_usd": 0.87}


def variant_name(spec: Spec, ctx: int) -> str:
    return f"{spec.alias}-{ctx // 1024}k"


def modelfile(spec: Spec, ctx: int) -> str:
    lines = [f"FROM {spec.tag}", f"PARAMETER num_ctx {ctx}"]
    for k, v in spec.params.items():
        lines.append(f"PARAMETER {k} {v}")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- ollama helpers


def _api(path: str, payload: dict | None = None, timeout: float = 600.0) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(OLLAMA_URL + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode() or "{}")


def installed_models() -> set[str]:
    try:
        return {m["name"] for m in _api("/api/tags").get("models", [])}
    except OSError:
        return set()


def _has(name: str, installed: set[str]) -> bool:
    return name in installed or f"{name}:latest" in installed


def ollama_ps() -> list[dict]:
    try:
        return _api("/api/ps").get("models", [])
    except OSError:
        return []


def _same_model(a: str, b: str) -> bool:
    """Ollama reports names with an implicit ``:latest`` tag."""
    return a.removesuffix(":latest") == b.removesuffix(":latest")


def gpu_split(ps_entry: dict) -> tuple[float, int]:
    """(fraction of the model resident on GPU, total bytes) from an /api/ps entry."""
    size = int(ps_entry.get("size") or 0)
    vram = int(ps_entry.get("size_vram") or 0)
    return (vram / size if size else 0.0), size


# --------------------------------------------------------------------------- power sampling


class PowerSampler(threading.Thread):
    """Peak / mean nvidia-smi power.draw while a probe runs (same source as power_sampler.py)."""

    def __init__(self, interval: float = 0.5):
        super().__init__(daemon=True)
        self.interval = interval
        self.samples: list[float] = []
        self._halt = threading.Event()

    def run(self):
        while not self._halt.is_set():
            try:
                out = subprocess.run(
                    ["nvidia-smi", "--query-gpu=power.draw", "--format=csv,noheader,nounits"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                ).stdout
                self.samples.append(float(out.strip().splitlines()[0]))
            except (OSError, ValueError, IndexError):
                pass
            self._halt.wait(self.interval)

    def stop(self) -> tuple[float | None, float | None]:
        self._halt.set()
        self.join(timeout=5)
        if not self.samples:
            return None, None
        return max(self.samples), sum(self.samples) / len(self.samples)


BENCH_PROMPT = (
    "You are an operator agent driving a Pokémon Red speedrun harness. In about 400 words, "
    "explain how you would diagnose an agent that is stuck walking into a wall on Route 1, "
    "listing the log files you would grep, the savestate you would reload, and the code you "
    "would read first. Be concrete."
)


def bench_one(model: str, ctx: int, num_predict: int = 400) -> dict:
    """One decode probe: returns tok/s, prompt tok/s, VRAM split, peak/mean W, load time."""
    sampler = PowerSampler()
    sampler.start()
    t0 = time.time()
    try:
        r = _api(
            "/api/generate",
            {
                "model": model,
                "prompt": BENCH_PROMPT,
                "stream": False,
                "keep_alive": "2m",
                "options": {"num_predict": num_predict, "num_ctx": ctx},
            },
            timeout=1800,
        )
    except OSError as e:
        sampler.stop()
        return {"model": model, "error": str(e)[:200]}
    wall = time.time() - t0
    peak_w, mean_w = sampler.stop()
    ps = next((m for m in ollama_ps() if _same_model(m.get("name") or m.get("model") or "", model)), {})
    frac, size = gpu_split(ps) if ps else (0.0, 0)
    eval_s = (r.get("eval_duration") or 0) / 1e9
    prompt_s = (r.get("prompt_eval_duration") or 0) / 1e9
    return {
        "model": model,
        "wall_s": round(wall, 1),
        "load_s": round((r.get("load_duration") or 0) / 1e9, 1),
        "out_tok": r.get("eval_count", 0),
        "out_tok_s": round(r.get("eval_count", 0) / eval_s, 1) if eval_s else 0.0,
        "prompt_tok_s": round(r.get("prompt_eval_count", 0) / prompt_s, 1) if prompt_s else 0.0,
        "gpu_frac": round(frac, 2),
        "size_gb": round(size / 1e9, 1),
        "peak_w": peak_w,
        "mean_w": mean_w,
    }


BENCH_HEADER = "| model | out tok/s | prompt tok/s | GPU % | resident GB | peak W | mean W | load s | note |"


def bench_row(row: dict, note: str = "") -> str:
    if "error" in row:
        return f"| {row['model']} | error | | | | | | | {row['error']} |"
    flag = "" if row["gpu_frac"] >= 0.99 else " **CPU spill**"
    return (
        f"| {row['model']} | {row['out_tok_s']} | {row['prompt_tok_s']} | {int(row['gpu_frac'] * 100)}{flag} "
        f"| {row['size_gb']} | {row['peak_w'] or '-'} | {row['mean_w'] and round(row['mean_w']) or '-'} "
        f"| {row['load_s']} | {note} |"
    )


# --------------------------------------------------------------------------- pi registration


def pi_entry(spec: Spec, ctx: int) -> dict:
    return {
        "id": variant_name(spec, ctx),
        "contextWindow": ctx,
        "input": ["text", "image"] if spec.vision else ["text"],
        "reasoning": spec.reasoning,
    }


def register(models_json: Path, specs: list[Spec], ctx: int, provider: str = "ollama") -> list[str]:
    """Add the -<ctx>k variants under models.json providers.<provider>.models (idempotent)."""
    data = json.loads(models_json.read_text()) if models_json.exists() else {"providers": {}}
    prov = data.setdefault("providers", {}).setdefault(provider, {"models": []})
    models = prov.setdefault("models", [])
    known = {m.get("id") for m in models}
    added = []
    for spec in specs:
        entry = pi_entry(spec, ctx)
        if entry["id"] in known:
            continue
        models.append(entry)
        added.append(entry["id"])
    if added:
        models_json.write_text(json.dumps(data, indent=2) + "\n")
    return added


# --------------------------------------------------------------------------- commands


def _pick(selectors: list[str]) -> list[Spec]:
    """Aliases and/or group names; no selector means the whole roster (grouped order)."""
    if not selectors:
        return list(ROSTER)
    picked: list[Spec] = []
    unknown = []
    for sel in selectors:
        if sel in BY_ALIAS:
            picked.append(BY_ALIAS[sel])
        elif sel in GROUPS:
            picked.extend(s for s in ROSTER if s.group == sel)
        else:
            unknown.append(sel)
    retired = [u for u in unknown if u in RETIRED]
    if retired:
        sys.exit("retired from the roster: " + "; ".join(f"{a} — {RETIRED[a]}" for a in retired))
    if unknown:
        sys.exit(f"unknown alias/group: {', '.join(unknown)}; see `list` (groups: {', '.join(GROUPS)})")
    return picked


def _by_group(specs: list[Spec]) -> list[tuple[str, list[Spec]]]:
    out: list[tuple[str, list[Spec]]] = []
    for g in GROUPS:
        members = [s for s in specs if s.group == g]
        if members:
            out.append((g, members))
    return out


def cmd_list(args) -> int:
    inst = installed_models()
    if RETIRED and not args.aliases:
        print("\n### retired\n")
        for a, why in RETIRED.items():
            print(f"- `{a}` — {why}")
    for group, members in _by_group(_pick(args.aliases)):
        print(f"\n### {group} — {GROUPS[group]}\n")
        print(f"| alias | ollama tag | base pulled | {args.ctx // 1024}k variant | note |")
        print("|---|---|---|---|---|")
        for s in members:
            print(
                f"| {s.alias} | `{s.tag}` | {'yes' if _has(s.tag, inst) else 'no'} "
                f"| {'yes' if _has(variant_name(s, args.ctx), inst) else 'no'} | {s.note} |"
            )
    return 0


def cmd_pull(args) -> int:
    rc = 0
    for s in _pick(args.aliases):
        reason = check_runnable(s.tag)
        if reason:
            print(f"-- skip {s.alias}: {reason}")
            rc = 1
            continue
        print(f"== pull {s.tag}", flush=True)
        r = subprocess.run(["ollama", "pull", s.tag], check=False)
        if r.returncode:
            rc = 1
            print(f"   FAILED ({r.returncode}) — pull failed for {s.tag}", flush=True)
    return rc


def cmd_create(args) -> int:
    inst = installed_models()
    rc = 0
    for s in _pick(args.aliases):
        if not _has(s.tag, inst):
            print(f"-- skip {s.alias}: base {s.tag} not pulled")
            continue
        name = variant_name(s, args.ctx)
        print(f"== create {name} (num_ctx={args.ctx})", flush=True)
        with tempfile.NamedTemporaryFile("w", suffix=".Modelfile", delete=False) as fh:
            fh.write(modelfile(s, args.ctx))
        try:
            r = subprocess.run(["ollama", "create", name, "-f", fh.name], check=False)
        finally:
            os.unlink(fh.name)
        rc = rc or r.returncode
    return rc


def cmd_register(args) -> int:
    inst = installed_models()
    specs = [s for s in _pick(args.aliases) if _has(variant_name(s, args.ctx), inst)]
    added = register(PI_MODELS_JSON, specs, args.ctx)
    print(f"registered {len(added)} new model(s) in {PI_MODELS_JSON}: {', '.join(added) or '-'}")
    print("(pi's tapes proxy points at Ollama, so nothing else to wire)")
    return 0


def cmd_bench(args) -> int:
    inst = installed_models()
    for group, members in _by_group(_pick(args.aliases)):
        print(f"\n### {group} — {GROUPS[group]}\n", flush=True)
        print(BENCH_HEADER)
        print("|" + "---|" * (BENCH_HEADER.count("|") - 1))
        print(
            f"| _Haiku 4.5 (target)_ | _{HAIKU_REF['out_tok_s']}_ | | | | | | "
            f"| _{HAIKU_REF['segs']} segs, {HAIKU_REF['s_per_turn']} s/turn, ${HAIKU_REF['cloud_usd']}_ |"
        )
        for s in members:
            name = variant_name(s, args.ctx)
            if not _has(name, inst):
                print(f"| {name} | not created | | | | | | | run `create` first |", flush=True)
                continue
            rows = [bench_one(name, args.ctx) for _ in range(args.repeat)]
            best = max(rows, key=lambda r: r.get("out_tok_s", 0))  # warm run
            print(bench_row(best, s.note.split(" — ")[0]), flush=True)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--ctx", type=int, default=DEFAULT_CTX, help="num_ctx for the variants (harness constant)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("list", cmd_list), ("pull", cmd_pull), ("create", cmd_create), ("register", cmd_register)):
        sp = sub.add_parser(name)
        sp.add_argument("aliases", nargs="*")
        sp.set_defaults(fn=fn)
    sp = sub.add_parser("bench")
    sp.add_argument("aliases", nargs="*")
    sp.add_argument("--repeat", type=int, default=2, help="probes per model (first one warms the load)")
    sp.set_defaults(fn=cmd_bench)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
