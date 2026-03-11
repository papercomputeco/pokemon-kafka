"""Reader for Tapes SQLite database.

Parses conversation nodes from tapes.sqlite into structured Python objects
for analysis. Pure stdlib — no external dependencies beyond sqlite3.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Generator


@dataclass
class ToolUse:
    """A tool invocation from an assistant message."""

    id: str = ""
    name: str = ""
    input_summary: str = ""


@dataclass
class ToolResult:
    """A tool result from a user message (tool_result content block)."""

    tool_use_id: str = ""
    content_summary: str = ""
    is_error: bool = False


@dataclass
class TokenUsage:
    """Token counts from an assistant response."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation: int = 0
    cache_read: int = 0


@dataclass
class TapeEntry:
    """Single parsed node from the Tapes database."""

    type: str = ""
    timestamp: str = ""
    session_id: str = ""
    text_content: str = ""
    tool_uses: list[ToolUse] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    token_usage: TokenUsage = field(default_factory=TokenUsage)
    raw: dict = field(default_factory=dict)


@dataclass
class TapeSession:
    """A conversation thread traced through parent_hash chains."""

    session_id: str = ""
    entries: list[TapeEntry] = field(default_factory=list)
    start_time: str = ""
    end_time: str = ""


# Recursive CTE that walks the parent_hash chain from a root node.
# Used by both read_session (fetchall) and iter_entries (cursor iteration).
_CHAIN_QUERY = (
    "WITH RECURSIVE chain(h) AS ("
    "  SELECT ? "
    "  UNION ALL "
    "  SELECT n.hash FROM nodes n "
    "  JOIN chain ON n.parent_hash = chain.h"
    ") "
    "SELECT n.hash, n.role, n.content, n.created_at, "
    "  n.prompt_tokens, n.completion_tokens, "
    "  n.cache_creation_input_tokens, n.cache_read_input_tokens, "
    "  n.parent_hash, n.model, n.agent_name "
    "FROM chain JOIN nodes n ON n.hash = chain.h "
    "ORDER BY n.created_at"
)


class TapeReader:
    """Reads and parses the Tapes SQLite database.

    Supports context manager protocol for connection reuse::

        with TapeReader(path) as reader:
            for sid in reader.list_sessions():
                session = reader.read_session(sid)

    Also works without a context manager (opens/closes per call).
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None

    def __enter__(self) -> "TapeReader":
        self._conn = sqlite3.connect(str(self.db_path))
        return self

    def __exit__(self, *exc) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        """Return the managed connection or open a temporary one."""
        if self._conn:
            return self._conn
        return sqlite3.connect(str(self.db_path))

    def _release_conn(self, conn: sqlite3.Connection) -> None:
        """Close the connection only if it's not the managed one."""
        if conn is not self._conn:
            conn.close()

    def list_sessions(self) -> list[str]:
        """Return hashes of root nodes (conversation starts) ordered by time."""
        conn = self._get_conn()
        try:
            rows = conn.execute("SELECT hash FROM nodes WHERE parent_hash IS NULL ORDER BY created_at").fetchall()
            return [r[0] for r in rows]
        finally:
            self._release_conn(conn)

    def read_session(self, root_hash: str) -> TapeSession:
        """Walk the parent_hash chain from a root node into a TapeSession."""
        conn = self._get_conn()
        try:
            rows = conn.execute(_CHAIN_QUERY, (root_hash,)).fetchall()
        finally:
            self._release_conn(conn)

        entries = [self._row_to_entry(row) for row in rows]
        session = TapeSession(
            session_id=root_hash,
            entries=entries,
        )
        if entries:
            session.start_time = entries[0].timestamp
            session.end_time = entries[-1].timestamp
        return session

    def iter_entries(self, root_hash: str) -> Generator[TapeEntry, None, None]:
        """Lazy generator over entries in a conversation chain."""
        conn = self._get_conn()
        try:
            cursor = conn.execute(_CHAIN_QUERY, (root_hash,))
            for row in cursor:
                yield self._row_to_entry(row)
        finally:
            self._release_conn(conn)

    def _row_to_entry(self, row: tuple) -> TapeEntry:
        """Convert a database row into a TapeEntry."""
        (
            hash_val,
            role,
            content_blob,
            created_at,
            prompt_tokens,
            completion_tokens,
            cache_creation,
            cache_read,
            parent_hash,
            model,
            agent_name,
        ) = row

        role = role or ""
        content = _parse_content_blob(content_blob)

        entry = TapeEntry(
            type=role,
            timestamp=created_at or "",
            session_id=hash_val or "",
            raw={
                "hash": hash_val,
                "role": role,
                "parent_hash": parent_hash,
                "model": model,
                "agent_name": agent_name,
            },
        )

        if role == "assistant":
            entry.token_usage = TokenUsage(
                input_tokens=prompt_tokens or 0,
                output_tokens=completion_tokens or 0,
                cache_creation=cache_creation or 0,
                cache_read=cache_read or 0,
            )
            texts = []
            for block in content:
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_input = block.get("tool_input", {})
                    name = block.get("tool_name", "")
                    summary = _summarize_tool_input(name, tool_input)
                    entry.tool_uses.append(
                        ToolUse(
                            id=block.get("tool_use_id", ""),
                            name=name,
                            input_summary=summary,
                        )
                    )
            entry.text_content = "\n".join(texts)

        elif role == "user":
            texts = []
            for block in content:
                if block.get("type") == "text":
                    texts.append(block.get("text", ""))
                elif block.get("type") == "tool_result":
                    result_content = block.get("content", "")
                    if isinstance(result_content, list):
                        parts = [p.get("text", "") for p in result_content if isinstance(p, dict)]
                        result_content = "\n".join(parts)
                    entry.tool_results.append(
                        ToolResult(
                            tool_use_id=block.get("tool_use_id", ""),
                            content_summary=str(result_content)[:500],
                            is_error=bool(block.get("is_error", False)),
                        )
                    )
            entry.text_content = "\n".join(texts)

        return entry


def _parse_content_blob(blob) -> list[dict]:
    """Parse the content column (JSON blob or None) into a list of blocks."""
    if blob is None:
        return []
    try:
        parsed = json.loads(blob) if isinstance(blob, (str, bytes)) else blob
    except (json.JSONDecodeError, TypeError):
        return []
    if isinstance(parsed, list):
        return [b for b in parsed if isinstance(b, dict)]
    return []


_TOOL_SUMMARY_KEY: dict[str, str] = {
    "Read": "file_path",
    "Write": "file_path",
    "Edit": "file_path",
    "Bash": "command",
    "Grep": "pattern",
    "Glob": "pattern",
    "Agent": "description",
}

_TOOL_PREFIX_KEY: set[str] = {"Grep", "Glob"}


def _summarize_tool_input(name: str, tool_input: dict) -> str:
    """Create a short summary of a tool invocation's input."""
    if not isinstance(tool_input, dict):
        return str(tool_input)[:200]

    key = _TOOL_SUMMARY_KEY.get(name)
    if key:
        val = str(tool_input.get(key, ""))[:200]
        return f"{key}={val}" if name in _TOOL_PREFIX_KEY else val

    for key in ("prompt", "query", "description", "command", "file_path"):
        if key in tool_input:
            return f"{key}={str(tool_input[key])[:200]}"
    return str(tool_input)[:200]
