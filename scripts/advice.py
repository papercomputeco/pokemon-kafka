"""Advice inbox — the in-run return path of the feedback loop.

The agent stays broker-free: advice arrives as JSONL files in an inbox
directory (mirroring publisher.py's JSONL-out), written by the Flink
alerts-consumer, an operator, or a future cassette's advise surface. The
agent polls new complete lines between turns and applies typed advice
mid-run. Same byte-offset discipline as the game-event bridge: a partial
trailing line stays unread until the writer finishes it.

Expiry is mandatory hygiene (the stale-worldmap / hard-block-expiry
lesson): a missing expires_at never expires — an explicit choice by the
writer — but an unparseable one drops the advice.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_ADVICE = "pokemon.advice.v1"


def read_new_lines(path: Path, offset: int) -> tuple[list[str], int]:
    """Read complete lines from byte *offset*; a partial trailing line stays unread."""
    with open(path, "rb") as f:
        f.seek(offset)
        chunk = f.read()
    last_newline = chunk.rfind(b"\n")
    if last_newline < 0:
        return [], offset
    complete = chunk[: last_newline + 1]
    lines = [line for line in complete.decode("utf-8").split("\n") if line.strip()]
    return lines, offset + last_newline + 1


def poll_inbox(inbox_dir: str, offsets: dict[str, int]) -> tuple[list[dict], dict[str, int]]:
    """Return (new advice dicts, updated offsets) across the inbox's *.jsonl files.

    Malformed lines and foreign schemas are skipped, but offsets advance past
    them — a bad line is never re-read.
    """
    new_offsets = dict(offsets)
    items: list[dict] = []
    root = Path(inbox_dir)
    if not root.is_dir():
        return items, new_offsets
    for path in sorted(root.glob("*.jsonl")):
        lines, new_offsets[path.name] = read_new_lines(path, new_offsets.get(path.name, 0))
        for line in lines:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("schema") == SCHEMA_ADVICE:
                items.append(parsed)
    return items, new_offsets


def is_expired(advice: dict, now: datetime | None = None) -> bool:
    """True when expires_at is present and in the past — or unparseable (fail closed)."""
    expires_at = advice.get("expires_at")
    if not expires_at:
        return False
    now = now or datetime.now(timezone.utc)
    try:
        expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
    except ValueError:
        return True
    return expiry <= now
