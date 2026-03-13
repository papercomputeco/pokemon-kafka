#!/usr/bin/env python3
"""Load telemetry JSONL files into a persistent DuckDB warehouse via dlt.

Usage:
    uv run scripts/dlt_pipeline.py [DATA_DIR] [--destination duckdb|snowflake] [--db-path PATH]

Examples:
    uv run scripts/dlt_pipeline.py                              # JSONL -> local DuckDB
    uv run scripts/dlt_pipeline.py --destination snowflake       # JSONL -> Snowflake
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import dlt
except ImportError:
    print(
        "dlt is not installed. Install it with:\n  uv sync --group dlt",
        file=sys.stderr,
    )
    sys.exit(1)

DEFAULT_DATA_DIR = Path("data/telemetry")
DEFAULT_DB_PATH = Path("data/telemetry.duckdb")


@dlt.resource(write_disposition="merge", merge_key="occurred_at")
def telemetry_events(data_dir: Path = DEFAULT_DATA_DIR):
    """Yield telemetry event dicts from JSONL files in *data_dir*."""
    data_dir = Path(data_dir)
    if not data_dir.exists():
        return

    for jsonl_file in sorted(data_dir.glob("*.jsonl")):
        for line in jsonl_file.read_text().splitlines():
            line = line.strip()
            if line:
                yield json.loads(line)


def create_pipeline(destination: str = "duckdb", db_path: Path = DEFAULT_DB_PATH) -> dlt.Pipeline:
    """Return a configured dlt pipeline."""
    if destination == "duckdb":
        dest = dlt.destinations.duckdb(credentials=str(db_path))
    else:
        dest = destination
    return dlt.pipeline(
        pipeline_name="pokemon_telemetry",
        destination=dest,
        dataset_name="telemetry",
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Load telemetry JSONL into a warehouse via dlt")
    parser.add_argument(
        "data_dir",
        nargs="?",
        default=str(DEFAULT_DATA_DIR),
        help=f"Directory containing JSONL files (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--destination",
        default="duckdb",
        choices=["duckdb", "snowflake"],
        help="dlt destination (default: duckdb)",
    )
    parser.add_argument(
        "--db-path",
        default=str(DEFAULT_DB_PATH),
        help=f"Path for local DuckDB file (default: {DEFAULT_DB_PATH})",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    pipeline = create_pipeline(destination=args.destination, db_path=Path(args.db_path))

    print(f"[dlt] Loading from {data_dir} -> {args.destination}")
    info = pipeline.run(telemetry_events(data_dir=data_dir), table_name="events")
    print(f"[dlt] Load complete: {info}")


if __name__ == "__main__":
    main()
