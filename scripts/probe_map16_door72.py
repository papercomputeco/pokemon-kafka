"""Map 16's door at (10,21) into 72: the planner calls it unreachable from (4,0). Walk toward it and
read what happens. Boots cerulean.state (16,4,0)."""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/cerulean.state", live_label="probe — map 16 door (10,21) to 72")
io = rig.io
for _ in range(4):
    io.press("b")
    io.wait(20)
print("start", rig.pos(), "bodies", sorted(rig.bodies()), flush=True)
for target in ((7, 10), (7, 22), (10, 22)):
    r = rig.walk(16, {target}, cap=400)
    print(f"walk to {target} -> {r} at {rig.pos()} text={rig.textbox()!r}", flush=True)
before = rig.pos()
io.press("up", hold=15, release=15)
io.wait(90)
print("up into the door:", before, "->", rig.pos(), "text", repr(rig.textbox()), flush=True)
rig.finish(outcome="probe map 16 door 72", goals="reach (10,21)")
