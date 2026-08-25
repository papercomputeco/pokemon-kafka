"""Fan-out backends for parameter races.

`local` is the default and always available. `daytona` is opt-in and imports
its SDK lazily, so this package stays importable without it installed.
"""

from __future__ import annotations

from fanout.backend import RaceBackend, degraded_fitness
from fanout.local import LocalBackend

__all__ = ["LocalBackend", "RaceBackend", "degraded_fitness", "get_backend"]


def get_backend(name: str, **kwargs):
    """Resolve a backend by name.

    Daytona is constructed here rather than imported at module scope so that
    `--backend local` never touches the optional dependency.
    """
    if name == "local":
        return LocalBackend()
    if name == "daytona":
        from fanout.daytona_backend import DaytonaBackend, DaytonaSettings

        snapshot = kwargs.pop("snapshot", None)
        cohort = kwargs.pop("cohort", None)
        if not snapshot or not cohort:
            raise ValueError("daytona backend needs --snapshot and --cohort")
        return DaytonaBackend(DaytonaSettings.from_env(snapshot=snapshot, cohort=cohort, **kwargs))
    raise ValueError(f"unknown backend: {name!r} (expected 'local' or 'daytona')")
