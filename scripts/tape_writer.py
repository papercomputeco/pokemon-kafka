"""Writer for Tapes SQLite database.

Inserts synthetic conversation nodes into tapes.sqlite so that external
agents (e.g. Flink alerts) can feed observations into the memory loop.
Pure stdlib — no external dependencies beyond sqlite3.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_CREATE_TABLE = (
    "CREATE TABLE IF NOT EXISTS nodes ("
    "  hash TEXT PRIMARY KEY,"
    "  role TEXT,"
    "  content JSON,"
    "  created_at DATETIME,"
    "  prompt_tokens INTEGER,"
    "  completion_tokens INTEGER,"
    "  cache_creation_input_tokens INTEGER,"
    "  cache_read_input_tokens INTEGER,"
    "  parent_hash TEXT,"
    "  model TEXT,"
    "  agent_name TEXT"
    ")"
)


class TapeWriter:
    """Writes synthetic nodes to the Tapes SQLite ``nodes`` table.

    Reuses a single connection across calls. Can be used as a context manager::

        with TapeWriter("tapes.sqlite") as w:
            w.write_node(role="assistant", ...)
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._schema_ready = False

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path))
        return self._conn

    def close(self):
        """Close the underlying connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            self._schema_ready = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def ensure_schema(self):
        """Create the nodes table if it doesn't exist."""
        if self._schema_ready:
            return
        conn = self._get_conn()
        conn.execute(_CREATE_TABLE)
        conn.commit()
        self._schema_ready = True

    def write_node(
        self,
        role: str,
        content_blocks: list[dict],
        parent_hash: str | None = None,
        model: str | None = None,
        agent_name: str | None = None,
    ) -> str:
        """Insert a node and return its content-addressable hash."""
        self.ensure_schema()

        now = datetime.now(timezone.utc).isoformat()
        content_json = json.dumps(content_blocks)
        node_hash = hashlib.sha256((content_json + now).encode()).hexdigest()

        conn = self._get_conn()
        conn.execute(
            "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                node_hash,
                role,
                content_json,
                now,
                None,  # prompt_tokens
                None,  # completion_tokens
                None,  # cache_creation_input_tokens
                None,  # cache_read_input_tokens
                parent_hash,
                model,
                agent_name,
            ),
        )
        conn.commit()

        return node_hash
