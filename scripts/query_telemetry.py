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


def create_connection(data_dir: Path) -> duckdb.DuckDBPyConnection:
    pattern = str(data_dir / "*.jsonl")
    conn = duckdb.connect()
    conn.execute(f"CREATE VIEW events AS SELECT * FROM read_json_auto('{pattern}')")
    return conn


def main():
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(__doc__)
        sys.exit(0)

    data_dir = DEFAULT_DIR
    query = SUMMARY_QUERY

    if args and args[0] == "--interactive":
        data_dir = Path(args[1]) if len(args) > 1 else DEFAULT_DIR
        conn = create_connection(data_dir)
        print(f"DuckDB connected to {data_dir}/*.jsonl")
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
