"""Shared test helpers for Tapes SQLite database setup."""

import json
import sqlite3


def create_test_db(path):
    """Create a tapes.sqlite with the nodes schema."""
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE nodes ("
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
    conn.commit()
    return conn


def insert_test_node(conn, hash_val, role="user", content=None, created_at="2026-03-09T10:00:00Z",
                     prompt_tokens=None, completion_tokens=None, cache_creation=None,
                     cache_read=None, parent_hash=None, model=None, agent_name=None):
    """Insert a node into the test database."""
    content_json = json.dumps(content) if content is not None else None
    conn.execute(
        "INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (hash_val, role, content_json, created_at,
         prompt_tokens, completion_tokens, cache_creation, cache_read,
         parent_hash, model, agent_name),
    )
    conn.commit()
