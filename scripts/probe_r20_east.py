"""Measure Route 20's east edge (31 -> 30) row by row: which rows at x=99 open, what the game says.

Boots probe_r20-31.state (arrived on 31 at (0,14) by SURF, still afloat), surfs east along the
model's water to x=99 on each candidate row, presses right, and reads position + text box.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
import road  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/probe_r20-31.state", live_label="probe — r20 east edge rows")
io, truth = rig.io, rig.truth
m = truth["maps"]["31"]
print("start", rig.pos(), "battle", io.read(ADDR_IN_BATTLE), "text", repr(rig.textbox()), flush=True)


def step(k, hold=15, release=15, wait=45):
    before = rig.pos()
    io.press(k, hold=hold, release=release)
    io.wait(wait)
    if io.read(ADDR_IN_BATTLE):
        rig.battle()
        io.press(k, hold=hold, release=release)
        io.wait(wait)
    return before, rig.pos()


def goto(target):
    """BFS over the water model from here to target, pressing each step; True on arrival."""
    mp, x, y = rig.pos()
    prev = road._water_reach(m, x, y, set())
    if target not in prev:
        return False
    path = [target]
    while prev[path[-1]] is not None:
        path.append(prev[path[-1]])
    path.reverse()
    for a, b in zip(path, path[1:]):
        k = "right" if b[0] > a[0] else "left" if b[0] < a[0] else "down" if b[1] > a[1] else "up"
        for _ in range(3):
            _before, now = step(k)
            if now[0] != 31 or now[1:] == b:
                break
        if rig.pos()[0] != 31:
            return True
        if rig.pos()[1:] != b:
            print("  refused", k, "at", rig.pos(), "text", repr(rig.textbox()), flush=True)
            return False
    return True


mp, x, y = rig.pos()
print("water model at start cell:", road._water_model(m, x, y), flush=True)
for row in sorted(range(18), key=lambda r: abs(r - 14)):
    if not road._water_model(m, 99, row):
        continue
    if rig.pos()[0] != 31:
        break
    ok = goto((99, row))
    if not ok:
        print(f"row {row}: could not reach (99,{row}); at {rig.pos()}", flush=True)
        continue
    before, now = step("right")
    print(f"row {row}: at {before} -> right -> {now}  text={rig.textbox()!r}", flush=True)
    if now[0] != 31:
        print("CROSSED to", now, flush=True)
        break
print("end", rig.pos(), flush=True)
rig.finish(outcome="probe r20 east edge", goals="31->30 rows")
