"""On Cycling Road (map 28) every step of a pedestrian was refused (run fwd_l14_28e, (28,1,123)).
Does getting on the BICYCLE restore movement? Boots r16_bike-187.state, presses each direction on
foot, mounts, presses again.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/r16_bike-187.state", live_label="probe — Cycling Road: foot vs bicycle")
io = rig.io
for _ in range(4):
    io.press("b")
    io.wait(20)


def presses(tag):
    for k in ("up", "left", "right", "down"):
        before = rig.pos()
        io.press(k, hold=15, release=15)
        io.wait(70)
        if io.read(ADDR_IN_BATTLE):
            rig.battle()
        print(f"  [{tag}] {k}: {before} -> {rig.pos()} text={rig.textbox()!r}", flush=True)


print("start", rig.pos(), "bag has BICYCLE:", any("BICYCLE" in n for n, _q in rig.bag_named()), flush=True)
presses("on foot")
ok = rig.use_item("BICYCLE")
io.wait(60)
print("use_item BICYCLE ->", ok, "text", repr(rig.textbox()), "pos", rig.pos(), flush=True)
for _ in range(4):
    io.press("b")
    io.wait(25)
presses("on the bicycle")
rig.finish(outcome=f"probe cycling road bike: mounted={ok}", goals="movement on foot vs bike")
