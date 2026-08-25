#!/usr/bin/env python3
"""Server-side snapshot build via the Daytona SDK — no CLI, no registry.

Stages exactly the files git would ship (`git ls-files -co --exclude-standard`),
which is provably free of ROMs and secrets because both are gitignored, then
builds remotely with Image.from_dockerfile. Used by build_snapshot.sh when the
daytona CLI is unavailable; usable directly too:

    uv run --group fanout scripts/fanout/sdk_build.py <snapshot-name>
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ROM_SUFFIXES = (".gb", ".gbc", ".ram", ".sav", ".state")
SECRET_NAMES = (".env",)


def stage_clean_context(dest: Path) -> int:
    """Copy the git-visible file set into dest; return the file count.

    gitignore already excludes rom/, .env, *.key, api-key-*.txt, .worktrees/
    and .venv/, so this context cannot leak them — but verify anyway, because
    "cannot" backed by a check beats "cannot" backed by an assumption.
    """
    listing = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    for rel in listing:
        src = REPO_ROOT / rel
        if not src.is_file():
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
    shutil.copy2(REPO_ROOT / "docker/fanout/Dockerfile", dest / "Dockerfile")

    leaks = [
        p
        for p in dest.rglob("*")
        if p.suffix in ROM_SUFFIXES or p.name in SECRET_NAMES or p.name.startswith("api-key-")
    ]
    if leaks:
        raise SystemExit(f"REFUSING to build: {len(leaks)} ROM/secret file(s) staged, e.g. {leaks[0]}")
    return len(listing)


def build(name: str) -> None:
    from daytona import CreateSnapshotParams, Daytona, Image, Resources

    with tempfile.TemporaryDirectory(prefix="fanout-snap-") as tmp:
        stage = Path(tmp)
        count = stage_clean_context(stage)
        print(f"[sdk-build] staged {count} git-clean files; building {name} remotely")
        Daytona().snapshot.create(
            CreateSnapshotParams(
                name=name,
                image=Image.from_dockerfile(stage / "Dockerfile"),
                resources=Resources(cpu=2, memory=4, disk=10),
            ),
            on_logs=lambda chunk: print(chunk, end="", flush=True),
        )
    print(f"\n[sdk-build] DONE: {name}")


if __name__ == "__main__":  # pragma: no cover - entrypoint
    if len(sys.argv) != 2:
        raise SystemExit("usage: sdk_build.py <snapshot-name>")
    build(sys.argv[1])
