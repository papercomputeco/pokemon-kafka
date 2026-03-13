#!/usr/bin/env python3
"""Query telemetry JSONL files with DuckDB.

Usage:
    python scripts/query_telemetry.py [DATA_DIR] [QUERY]

    DATA_DIR defaults to ./data/telemetry
    QUERY defaults to a token usage summary

Examples:
    # Default summary
    python scripts/query_telemetry.py

    # Custom query
    python scripts/query_telemetry.py ./data/telemetry "SELECT node.bucket.role, count(*) FROM events GROUP BY 1"

    # Interactive mode
    python scripts/query_telemetry.py --interactive
"""

import sys
from pathlib import Path

try:
    import duckdb
except ImportError:  # pragma: no cover
    print("Install duckdb: pip install duckdb", file=sys.stderr)
    sys.exit(1)

DEFAULT_DIR = Path("data/telemetry")

SUMMARY_QUERY = """
SELECT
    node.bucket.role AS role,
    node.bucket.model AS model,
    count(*) AS events,
    sum(node.usage.input_tokens) AS total_input_tokens,
    sum(node.usage.output_tokens) AS total_output_tokens,
    min(occurred_at) AS first_seen,
    max(occurred_at) AS last_seen
FROM events
GROUP BY 1, 2
ORDER BY events DESC
"""

SESSIONS_QUERY = """
SELECT
    root_hash,
    count(*) AS turns,
    sum(node.usage.input_tokens) AS input_tokens,
    sum(node.usage.output_tokens) AS output_tokens,
    min(occurred_at) AS started,
    max(occurred_at) AS ended
FROM events
GROUP BY root_hash
ORDER BY started DESC
LIMIT 20
"""


_WAREHOUSE_VIEW = """\
CREATE VIEW events AS SELECT
    *,
    {
        'bucket': {'role': node__bucket__role, 'model': node__bucket__model},
        'usage': {'input_tokens': node__usage__input_tokens, 'output_tokens': node__usage__output_tokens},
        'project': node__project
    } AS node
FROM warehouse.raw.events
"""


def create_connection(data_dir: Path, db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    if db_path and db_path.exists():
        conn = duckdb.connect()
        conn.execute(f"ATTACH '{db_path}' AS warehouse (READ_ONLY)")
        conn.execute(_WAREHOUSE_VIEW)
    else:
        pattern = str(data_dir / "*.jsonl")
        conn = duckdb.connect()
        conn.execute(f"CREATE VIEW events AS SELECT * FROM read_json_auto('{pattern}')")
    return conn


def _parse_db_flag(args: list[str]) -> tuple[list[str], Path | None]:
    """Extract --db PATH from raw argv, return remaining args and db_path."""
    db_path = None
    remaining = []
    i = 0
    while i < len(args):
        if args[i] == "--db" and i + 1 < len(args):
            db_path = Path(args[i + 1])
            i += 2
        else:
            remaining.append(args[i])
            i += 1
    return remaining, db_path


def main():
    raw_args = sys.argv[1:]

    if "--help" in raw_args or "-h" in raw_args:
        print(__doc__)
        sys.exit(0)

    args, db_path = _parse_db_flag(raw_args)

    data_dir = DEFAULT_DIR
    query = SUMMARY_QUERY

    if args and args[0] == "--interactive":
        data_dir = Path(args[1]) if len(args) > 1 else DEFAULT_DIR
        conn = create_connection(data_dir, db_path=db_path)
        source = str(db_path) if db_path and db_path.exists() else f"{data_dir}/*.jsonl"
        print(f"DuckDB connected to {source}")
        print("Table: events | Type SQL queries, empty line to quit.\n")
        while True:
            try:
                line = input("duckdb> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not line:
                break
            try:
                print(conn.execute(line).fetchdf().to_string())
            except Exception as exc:
                print(f"Error: {exc}")
        return

    if args and args[0] == "--sessions":
        query = SESSIONS_QUERY
        data_dir = Path(args[1]) if len(args) > 1 else DEFAULT_DIR
    elif args:
        data_dir = Path(args[0])
        if len(args) > 1:
            query = args[1]

    # In warehouse mode, skip JSONL existence checks
    if db_path and db_path.exists():
        conn = create_connection(data_dir, db_path=db_path)
        print(conn.execute(query).fetchdf().to_string())
        return

    if not data_dir.exists():
        print(f"No data directory at {data_dir}", file=sys.stderr)
        sys.exit(1)

    if not list(data_dir.glob("*.jsonl")):
        print(f"No .jsonl files in {data_dir}", file=sys.stderr)
        sys.exit(1)

    conn = create_connection(data_dir)
    print(conn.execute(query).fetchdf().to_string())


if __name__ == "__main__":
    main()
