#!/usr/bin/env python3
"""On-demand Ollama host on a Daytona GPU sandbox — the cloud arm of the bench.

The model bench is already host-agnostic: `run_model_evals.py` talks to
whatever `OLLAMA_HOST_URL` names, which is how local vs cloud Ollama stay one
harness. This adds a fourth backend the same way — boot a GPU sandbox, pull
roster models into it, print the URL. Nothing downstream changes:

    uv run --group fanout scripts/fanout/ollama_host.py up --models gpt-oss-120b
    OLLAMA_HOST_URL=<printed url> uv run python scripts/run_model_evals.py --models gpt-oss-120b
    uv run --group fanout scripts/fanout/ollama_host.py down

Models are named by their `local_models.py` roster alias (ROSTER plus the
H100-only DAYTONA_ROSTER). The sandbox carries a TTL backstop (default 2h): a
forgotten host reaps itself instead of billing overnight.

A persistent weights volume exists (--volume fanout-ollama-models) but is
OFF by default, on measured evidence (2026-08-25): the registry pulls at
~100 MB/s while the FUSE volume reads at ~75 MB/s single-stream AND 78 MB/s
with 8 parallel readers — bandwidth-capped, so a "warm" 65 GB session pays
~13 min of load, more than the ~11 min pull it was meant to avoid. Every
session moves the bytes either way; the volume only buys registry
independence. Opt in if ollama.com is down or rate-limiting you.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR.parent) not in sys.path:  # pragma: no cover - direct-execution only
    sys.path.insert(0, str(SCRIPT_DIR.parent))

from local_models import BY_ALIAS, DAYTONA_BY_ALIAS  # noqa: E402

GPU_SNAPSHOT = "daytona-gpu"  # stock image; probed 2026-08-24: provisions an H100 80GB
OLLAMA_PORT = 11434
# Weights live on a persistent volume, mounted here and pointed at via
# OLLAMA_MODELS — explicit path, so it works whatever user ollama runs as.
DEFAULT_VOLUME = "fanout-ollama-models"
VOLUME_MOUNT = "/models"
STATE_FILE = SCRIPT_DIR.parent.parent / "runs" / "fanout" / "ollama_host.json"
INSTALL_CMD = "command -v ollama >/dev/null 2>&1 || curl -fsSL https://ollama.com/install.sh | sh"
# $HOME, expanded in-sandbox: the GPU snapshot runs as user `daytona`,
# not root — a hardcoded /root store made the server die on startup
# (found live 2026-08-25).
LOCAL_STORE = "$HOME/.ollama/models"
# OLLAMA_LOAD_TIMEOUT: loading 61 GB from the FUSE volume takes ~13 min at
# its measured 75 MB/s; ollama's default 5-minute load timeout turned that
# into an HTTP 500 mid-eval (live, 2026-08-25).
SERVE_CMD = "OLLAMA_MODELS={models_dir} OLLAMA_LOAD_TIMEOUT=40m nohup ollama serve > /tmp/ollama.log 2>&1 &"
# In-script wait: `break`, never `exit 0` — these snippets are inlined into a
# larger `set -e` script, where an exit would silently truncate provisioning.
WAIT_SNIPPET = (
    f"ok=0; for i in $(seq 1 30); do curl -s http://127.0.0.1:{OLLAMA_PORT} >/dev/null"
    ' && { ok=1; break; }; sleep 1; done; [ "$ok" = 1 ]'
)
STOP_SNIPPET = "pkill -x ollama || true; for i in $(seq 1 15); do pgrep -x ollama >/dev/null || break; sleep 1; done"


def resolve_models(aliases: list[str]) -> list[str]:
    """Roster aliases -> ollama model tags; unknown names are an error, not a
    silent pull of whatever Ollama guesses."""
    tags = []
    for alias in aliases:
        # The host runs both tiers: everything the local card runs, plus the
        # H100-only models (DAYTONA_ROSTER) that exist precisely because this
        # host has 80 GB and the local card has 32.
        spec = BY_ALIAS.get(alias) or DAYTONA_BY_ALIAS.get(alias)
        if spec is None:
            raise SystemExit(f"unknown roster alias {alias!r} — see ROSTER and DAYTONA_ROSTER in local_models.py")
        tags.append(spec.tag)
    return tags


def _marker(tag: str) -> str:
    """Volume-resident marker recording that a tag's blobs are on the volume."""
    return f"{VOLUME_MOUNT}/.pulled-" + tag.replace(":", "-").replace("/", "-")


def warm_check_command(tags: list[str]) -> str:
    """Prints WARM when every tag's marker is on the volume, COLD otherwise."""
    tests = " && ".join(f"test -e {_marker(t)}" for t in tags)
    return f"({tests}) && echo WARM || echo COLD"


def serve_command(models_dir: str) -> str:
    """Start ollama against a store and wait for the socket — one bounded exec."""
    return f"{SERVE_CMD.format(models_dir=models_dir)}\n{WAIT_SNIPPET}"


def copy_start_command(tags: list[str]) -> str:
    """Kick off the store copy DETACHED, its exit code parked in a file.

    The copy of a 60+ GB store onto the FUSE volume runs 10-20 minutes with no
    output; run as one exec, the silent stream died mid-copy and took the
    remote shell with it (observed live 2026-08-25) — the markers were never
    written and the driver hung. Detached-plus-poll keeps every exec short.
    Stray *partial* files (from any earlier failed pull attempt against the
    mount) are cleared first so they never shadow a real blob.
    """
    touches = " && ".join(f"touch {_marker(t)}" for t in tags)
    return (
        "rm -f /tmp/cp.rc; nohup sh -c '"
        f'find {VOLUME_MOUNT} -name "*partial*" -delete 2>/dev/null; '
        f"mkdir -p {VOLUME_MOUNT} && cp -an {LOCAL_STORE}/. {VOLUME_MOUNT}/ && {touches}; "
        "echo $? > /tmp/cp.rc' > /dev/null 2>&1 &"
    )


COPY_POLL_CMD = "cat /tmp/cp.rc 2>/dev/null || echo RUNNING"


def save_state(sandbox_id: str, url: str) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps({"sandbox_id": sandbox_id, "url": url, "created_at": time.time()}))


def load_state() -> dict | None:
    try:
        return json.loads(STATE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def up(aliases: list[str], ttl_minutes: int = 120, volume: str = "", client=None) -> str:
    """Boot the host, pull any missing models, print and return the base URL."""
    from daytona import CreateSandboxFromSnapshotParams, Daytona

    tags = resolve_models(aliases)
    d = client or Daytona()
    existing = load_state()
    if existing:
        raise SystemExit(f"host already up ({existing['url']}) — run `down` first, one host at a time")

    volumes = None
    if volume:
        from daytona import VolumeMount

        # create=True makes the first `up` provision the volume; later hosts
        # find warm weights and `ollama pull` becomes an instant no-op.
        vol = d.volume.get(volume, create=True)
        # get() returns while a fresh volume is still pending_create, and
        # sandbox creation rejects a non-ready volume — wait it out.
        deadline = time.time() + 180
        while "ready" not in str(getattr(vol, "state", "")).lower():
            if time.time() > deadline:
                raise SystemExit(f"volume {volume!r} never became ready (state: {vol.state})")
            time.sleep(2)
            vol = d.volume.get(volume)
        volumes = [VolumeMount(volume_id=vol.id, mount_path=VOLUME_MOUNT)]

    sandbox = d.create(
        CreateSandboxFromSnapshotParams(
            snapshot=GPU_SNAPSHOT,
            labels={"purpose": "ollama-bench-host"},
            # public: the preview URL must be callable by plain OLLAMA_HOST_URL
            # consumers (urllib, no auth headers). Obscure hostname + TTL bound
            # the exposure; the endpoint holds no data, only inference.
            public=True,
            ephemeral=True,
            ttl_minutes=ttl_minutes,
            volumes=volumes,
        ),
        timeout=300,
    )

    def step(cmd: str, timeout: int, what: str):
        r = sandbox.process.exec(cmd, timeout=timeout)
        if r.exit_code != 0:
            raise SystemExit(f"{what} failed: {r.result[-300:]}")
        return r

    try:
        step(INSTALL_CMD, 300, "install")
        warm = False
        if volumes:
            warm = "WARM" in step(warm_check_command(tags), 30, "warm check").result
        if warm:
            print("[host] warm volume — serving straight from it", file=sys.stderr)
            step(serve_command(VOLUME_MOUNT), 60, "serve")
        else:
            # Cold: pull to LOCAL disk (the FUSE volume cannot take ollama's
            # partial writes), then hand off to the volume when one is in use.
            step(serve_command(LOCAL_STORE), 60, "serve")
            for tag in tags:
                print(f"[host] pulling {tag} ...", file=sys.stderr)
                step(f"ollama pull {tag}", 1800, f"pull {tag}")
            if volumes:
                print("[host] copying store to volume (detached; polling) ...", file=sys.stderr)
                step(STOP_SNIPPET, 60, "stop server")
                step(copy_start_command(tags), 30, "start copy")
                # Poll in short execs: the one long silent exec died mid-copy
                # and took the remote shell with it (live, 2026-08-25).
                deadline = time.time() + 2700
                while True:
                    rc = step(COPY_POLL_CMD, 30, "copy poll").result.strip().splitlines()[-1]
                    if rc == "0":
                        break
                    if rc not in ("RUNNING", ""):
                        raise SystemExit(f"store copy failed (rc={rc})")
                    if time.time() > deadline:
                        raise SystemExit("store copy timed out after 45 min")
                    time.sleep(15)
                step(serve_command(VOLUME_MOUNT), 60, "serve from volume")
    except BaseException:
        d.delete(sandbox)  # a half-built host must not survive to bill idle
        raise

    url = sandbox.get_preview_link(OLLAMA_PORT).url
    save_state(sandbox.id, url)
    print(f"[host] up: {url} (ttl {ttl_minutes}m, models: {', '.join(tags)})", file=sys.stderr)
    print(url)
    return url


def down(client=None) -> int:
    """Tear the host down by state file; idempotent."""
    from daytona import Daytona

    state = load_state()
    if not state:
        print("[host] no host recorded — nothing to do", file=sys.stderr)
        return 0
    d = client or Daytona()
    try:
        d.delete(d.get(state["sandbox_id"]))
        print(f"[host] deleted {state['sandbox_id']}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - already gone (TTL) is success, not failure
        print(f"[host] delete skipped ({type(exc).__name__}) — likely already reaped", file=sys.stderr)
    STATE_FILE.unlink(missing_ok=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="On-demand Ollama host on a Daytona GPU sandbox")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_up = sub.add_parser("up", help="boot the host and pull models")
    p_up.add_argument(
        "--models", default="qwen38-27b", help="comma-separated roster aliases (ROSTER or DAYTONA_ROSTER)"
    )
    p_up.add_argument("--ttl", type=int, default=120, help="minutes before the sandbox self-reaps")
    p_up.add_argument(
        "--volume",
        default="",
        help=f"persistent weights volume, e.g. {DEFAULT_VOLUME!r} — OFF by default: measured FUSE "
        "read (75-78 MB/s) is slower than a registry pull, so it only helps when ollama.com is "
        "unavailable",
    )
    sub.add_parser("down", help="tear the host down")
    args = parser.parse_args(argv)

    if args.cmd == "up":
        up([a.strip() for a in args.models.split(",") if a.strip()], ttl_minutes=args.ttl, volume=args.volume)
        return 0
    return down()


if __name__ == "__main__":  # pragma: no cover - entrypoint
    sys.exit(main())
