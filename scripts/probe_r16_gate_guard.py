"""What does the Route 16 gate guard say, in full? The leg recorded only "Excuse me! Wait up
please!" at (186,4,7). Boots r16_awake-28.state (186,5,7), walks west along row 7, and turns the
pages, reading each.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/r16_awake-28.state", live_label="probe — Route 16 gate guard, full text")
io = rig.io
for _ in range(4):
    io.press("b")
    io.wait(20)
print("start", rig.pos(), "bodies", sorted(rig.bodies()), flush=True)
pages = []
for _ in range(6):
    before = rig.pos()
    io.press("left", hold=15, release=15)
    io.wait(90)
    t = rig.textbox()
    print(f"  left: {before} -> {rig.pos()} text={t!r}", flush=True)
    if t and t != "OPTION EXIT":
        pages.append(t)
        for _ in range(8):
            io.press("a")
            io.wait(50)
            t2 = rig.textbox()
            if t2 and t2 != pages[-1]:
                pages.append(t2)
                print(f"    page: {t2!r}", flush=True)
            if not t2:
                break
        break
print("pages:", pages, "| pos", rig.pos(), "bodies", sorted(rig.bodies()), flush=True)
rig.finish(outcome="probe r16 gate guard", goals="full text")
