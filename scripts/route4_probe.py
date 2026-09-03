#!/usr/bin/env python3
"""Route-4 boundary probe: which street (3) west-edge rows cross into which map-15 cells,
   and which of those cells connect to the south exit toward map 14.

The 2026-09-03 badge-8 leg crossed at (15, 89, 11) and found the cell sealed from the south
exit by the grid-and-pair pathfinder — the fourth time a street-side entry landed in a pocket
map 15 seals. This probe measures instead of assuming: cross at every open west-edge row of
map 3, record the landing in 15, and BFS from each landing to the south-edge cells. The rows
are tried far-to-near so the first crossing is the one we most likely already burned.

Banks ``route4_e.state`` when a landing connects to the exit, for the leg to resume from.
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import road  # noqa: E402
from expedition_rig import Rig  # noqa: E402

BANK_DIR = SCRIPT_DIR.parent / "data" / "local_runs" / "roster-bench"


def log(*args) -> None:
    print(*args, flush=True)


def connected15(rig: Rig, landing: tuple[int, int]) -> bool:
    exits = {(x, 17) for x in (6, 7, 8, 9, 10, 11, 86, 87, 88, 89)}
    region = road.reachable(rig.truth, rig.pairs, 15, landing)
    return bool(region & exits)


def main() -> int:
    started = sys.argv[1] if len(sys.argv) > 1 else str(BANK_DIR / "m2_route4.state")
    rig = Rig(started, run_id="route4-probe")
    mp0, x0, y0 = rig.pos()
    log(f"probe starts at ({mp0},{x0},{y0})")
    rig.emit("probe_open", pos=list(rig.pos()))

    def back_to_3() -> None:
        if rig.pos()[0] == 15:
            pos_before = rig.pos()
            rig.io.press("right", hold=8, release=8)
            rig.io.wait(40)
            log(f"  back-step from {pos_before} -> {rig.pos()}")
        rig.settle()

    if mp0 == 15:
        back_to_3()

    m3 = rig.truth["maps"]["3"]
    rows = sorted({y for y in range(m3["height"]) if m3["grid"][y][0] == "1"}, key=lambda y: (y > 17, -y))
    log(f"street west-edge rows, far first: {rows}")
    for r in rows:
        if rig.pos()[0] != 3:
            back_to_3()
            if rig.pos()[0] != 3:
                log(f"cannot return to the street (now {rig.pos()}); stopping")
                return 1
        w = rig.walk(3, {(0, r)}, cap=120)
        if rig.pos()[1:] != (0, r):
            log(f"row {r}: could not walk to (0,{r}) ({w}) @ {rig.pos()}")
            continue
        rig.io.press("left", hold=10, release=10)
        rig.io.wait(40)
        landed = rig.pos()
        if landed[0] == 15:
            ok = connected15(rig, landed[1:])
            log(f"row {r}: crossed -> 15 at {landed[1:]} exit-connected={ok}")
            rig.emit("probe_row", source_row=r, landed=list(landed), exit_connected=ok)
            if ok:
                rig.bank("route4_e", directory=BANK_DIR)
                rig.emit("probe_found", source_row=r, landed=list(landed))
                log("FOUND a crossing that reaches the south exit — banked route4_e.state")
                return 0
            rig.io.press("right", hold=8, release=8)
            rig.io.wait(40)
            log(f"  row {r} sealed; back at {rig.pos()}")
        else:
            log(f"row {r}: crossed to map {landed[0]} at {landed[1:]} — not the route, stopping")
            rig.emit("probe_row", source_row=r, landed=list(landed), exit_connected=None, off_target=True)
            rig.bank("route4-offtrack", directory=BANK_DIR)
            return 2
    log("every street west-edge row was asked; none reached the south exit")
    rig.emit("probe_exhausted", rows=rows)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
