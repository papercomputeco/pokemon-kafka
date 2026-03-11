"""CLI wrapper for the observational memory observer.

Usage:
    python3 scripts/observe_cli.py [--db PATH] [--memory-dir DIR] [--dry-run] [--session HASH] [--reset]
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from observer import Observer


def detect_db_path() -> str:
    """Auto-detect tapes.sqlite from .tapes/ in the current working directory."""
    return str(Path(os.getcwd()) / ".tapes" / "tapes.sqlite")


def detect_memory_dir() -> str:
    """Default memory directory alongside the tapes database."""
    return str(Path(os.getcwd()) / ".tapes" / "memory")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Distill Tapes sessions into observational memory")
    parser.add_argument(
        "--db",
        help="Path to tapes.sqlite (default: .tapes/tapes.sqlite)",
    )
    parser.add_argument(
        "--memory-dir",
        help="Directory for observations output (default: .tapes/memory/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print observations without writing to disk",
    )
    parser.add_argument(
        "--session",
        help="Process a single session (root node hash) only",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Clear watermark and reprocess all sessions",
    )

    args = parser.parse_args(argv)

    db_path = args.db or detect_db_path()
    memory_dir = args.memory_dir or detect_memory_dir()

    observer = Observer(db_path=db_path, memory_dir=memory_dir)

    if args.reset:
        if observer.state_path.exists():
            observer.state_path.unlink()
        print("Watermark cleared.")

    if args.session:
        session = observer.reader.read_session(args.session)
        observations = observer.observe_session(session)
        if not args.dry_run and observations:
            observer.write_observations(observations)
            print(f"Wrote {len(observations)} observation(s) to {observer.observations_path}")
        else:
            for obs in observations:
                print(f"[{obs.priority}] {obs.content} (session: {obs.source_session[:8]})")
            print(f"\n{len(observations)} observation(s) found.")
    elif args.dry_run:
        sessions = observer.get_unprocessed_sessions()
        observations = []
        for sid in sessions:
            session = observer.reader.read_session(sid)
            observations.extend(observer.observe_session(session))
        for obs in observations:
            print(f"[{obs.priority}] {obs.content} (session: {obs.source_session[:8]})")
        print(f"\n{len(observations)} observation(s) found.")
    else:
        observations = observer.run()
        print(f"Wrote {len(observations)} observation(s) to {observer.observations_path}")


if __name__ == "__main__":  # pragma: no cover
    main()
