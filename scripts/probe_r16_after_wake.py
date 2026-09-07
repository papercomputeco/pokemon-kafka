"""After the flute wakes Route 16's sleeper and the fight ends, does its sprite still block (26,10)?
Boots fly_won-27.state (27,27,10): talks, plays the flute, fights, then reads the sprite table and
tries to step west; if refused, leaves to map 6 and comes back and tries again.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/fly_won-27.state", live_label="probe — Route 16 sleeper after the wake")
io = rig.io


def step_left():
    before = rig.pos()
    io.press("left", hold=15, release=15)
    io.wait(60)
    if io.read(ADDR_IN_BATTLE):
        rig.battle()
    return before, rig.pos()


io.press("left")
io.wait(25)
print("talk:", repr(rig.talk("left")), "| bodies:", sorted(rig.bodies()), flush=True)
ok = rig.use_item("POKe FLUTE", face="left")
print("use_item ->", ok, "text:", repr(rig.textbox()), flush=True)
for _ in range(20):
    if io.read(ADDR_IN_BATTLE):
        print("  battle opened; fighting", flush=True)
        rig.battle()
        break
    io.press("a")
    io.wait(40)
rig.settle()
print("after the fight: pos", rig.pos(), "bodies", sorted(rig.bodies()), "text", repr(rig.textbox()), flush=True)
print("step left:", step_left(), flush=True)
print("step left:", step_left(), flush=True)
if rig.pos()[1:] == (27, 10):
    print("still blocked; leaving to map 6 and coming back", flush=True)
    print("  cross 27->6:", rig.cross(27, 6), rig.pos(), flush=True)
    print("  cross 6->27:", rig.cross(6, 27), rig.pos(), flush=True)
    r = rig.walk(27, {(27, 10)}, cap=300)
    print("  back at (27,10):", r, rig.pos(), "bodies", sorted(rig.bodies()), flush=True)
    print("  step left:", step_left(), flush=True)
    print("  step left:", step_left(), flush=True)
rig.finish(outcome=f"probe r16 after wake: at {rig.pos()}", goals="does the sprite linger")
