"""At (28,1,123) every press is refused, on foot and on the bicycle, and the baton would not
settle. What is parking movement? Dump the window, turn pages with A, test START, retry moves.
Boots r16_bike-187.state.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/r16_bike-187.state", live_label="probe — Cycling Road: what parks movement")
io = rig.io


def rows(tag):
    shown = [(r, rig.window_row(r).strip()) for r in range(18) if rig.window_row(r).strip()]
    print(f"  [{tag}] battle={io.read(ADDR_IN_BATTLE)} pos={rig.pos()} window={shown}", flush=True)


rows("boot")
for i in range(10):
    io.press("a")
    io.wait(45)
rows("after A x10")
for k in ("down", "up", "left", "right"):
    before = rig.pos()
    io.press(k, hold=15, release=15)
    io.wait(70)
    print(f"  {k}: {before} -> {rig.pos()}", flush=True)
io.press("start")
io.wait(60)
rows("after START")
for _ in range(4):
    io.press("b")
    io.wait(25)
for k in ("down", "down", "down"):
    before = rig.pos()
    io.press(k, hold=30, release=30)
    io.wait(120)
    print(f"  long {k}: {before} -> {rig.pos()}", flush=True)
rows("end")
rig.finish(outcome="probe cycling road stuck", goals="what parks movement")
