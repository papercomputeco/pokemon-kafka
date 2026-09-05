"""Watch surf_cross work the 31 -> 30 crossing step by step from probe_r20-31.state (afloat at
(31,0,14)): every phase (routed water cross, hop to the island, boarding, arm) logs its position
and what the screen says, so a failure is a sentence and a cell, not a code.
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
import road  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/probe_r20-31.state", live_label="probe — 31->30 island hop, logged")
io, truth = rig.io, rig.truth
for _ in range(4):
    io.press("b")
    io.wait(20)
if io.read(ADDR_IN_BATTLE):
    rig.battle()
print("start", rig.pos(), "text", repr(rig.textbox()), flush=True)


def wrap(name):
    fn = getattr(road, name)

    def inner(*a, **k):
        print(f"  > {name} at {rig.pos()} text={rig.textbox()!r}", flush=True)
        r = fn(*a, **k)
        print(f"  < {name} -> {r!r} at {rig.pos()} text={rig.textbox()!r}", flush=True)
        return r

    setattr(road, name, inner)


for n in ("_water_cross", "_hop_to_far_shore", "_board_water", "shore_stand", "walk"):
    wrap(n)
_surf_route = road.surf_route
road.surf_route = lambda *a, **k: _surf_route(*a, **{**k, "log": lambda m: print(m, flush=True)})


def arm():
    print(f"  ARM at {rig.pos()} battle={io.read(ADDR_IN_BATTLE)} text={rig.textbox()!r}", flush=True)
    r = rig._arm_surf()
    print(f"  ARM -> {r} at {rig.pos()} text={rig.textbox()!r}", flush=True)
    return r


r = road.surf_cross(io, truth, rig.pairs, 31, 30, arm_surf=arm, battle=rig.battle)
print("surf_cross ->", r, "at", rig.pos(), "text", repr(rig.textbox()), flush=True)
rig.finish(outcome=f"probe island hop: {r}", goals="31->30")
