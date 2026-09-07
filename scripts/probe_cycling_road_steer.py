"""Cycling Road (map 28) from its top, (1,46): does a press to the right steer on the slope, does a
press up climb, and how far does one 'down' carry? The bottom-left corner (1,123) is a dead end
(measured: every direction refused there), so the descent must be steered to x=6..7.
Boots r16_bike-28.state.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/r16_bike-28.state", live_label="probe — Cycling Road steering")
io = rig.io
for _ in range(4):
    io.press("b")
    io.wait(20)
print("start", rig.pos(), flush=True)


def press(k, hold=8, wait=40):
    before = rig.pos()
    io.press(k, hold=hold, release=8)
    io.wait(wait)
    if io.read(ADDR_IN_BATTLE):
        rig.battle()
    print(f"  {k} (hold {hold}, wait {wait}): {before} -> {rig.pos()}", flush=True)


print("idle 120 frames (does the slope move us on its own?)", rig.pos(), flush=True)
io.wait(120)
print("  after idle:", rig.pos(), flush=True)
for _ in range(3):
    press("right")
for _ in range(2):
    press("up")
for _ in range(3):
    press("down")
for _ in range(3):
    press("right", hold=16, wait=60)
print("end", rig.pos(), flush=True)
rig.finish(outcome="probe cycling road steering", goals="slope mechanics")
