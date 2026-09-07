"""Which sprite byte marks Route 16's sleeper as gone? Dump the 16-byte state and data blocks of
the sprite standing at (26,10) before the flute and after "SNORLAX returned to the mountains!".
Boots fly_won-27.state (27,27,10).
"""

from __future__ import annotations

import sys

sys.path.insert(0, "scripts")
import road  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from quartermaster import ADDR_IN_BATTLE  # noqa: E402

rig = Rig("data/local_runs/roster-bench/fly_won-27.state", live_label="probe — sprite bytes of the sleeper")
io = rig.io


def dump(tag):
    for slot in range(16):
        st = [io.read(road.SPRITE_STATE_BASE + 0x10 * slot + i) for i in range(16)]
        da = [io.read(road.SPRITE_DATA_BASE + 0x10 * slot + i) for i in range(16)]
        if da[5] - 4 == 26 and da[4] - 4 == 10:
            print(f"  [{tag}] slot {slot}: state {[hex(b) for b in st]} data {[hex(b) for b in da]}", flush=True)
            return slot
    print(f"  [{tag}] no sprite at (26,10)", flush=True)


print("bodies before:", sorted(rig.bodies()), flush=True)
slot = dump("before")
io.press("left")
io.wait(25)
rig.talk("left")
ok = rig.use_item("POKe FLUTE", face="left")
for _ in range(20):
    if io.read(ADDR_IN_BATTLE):
        rig.battle()
        break
    io.press("a")
    io.wait(40)
rig.settle()
print("text:", repr(rig.textbox()), "bodies after:", sorted(rig.bodies()), flush=True)
dump("after")
if slot is not None:
    st = [io.read(road.SPRITE_STATE_BASE + 0x10 * slot + i) for i in range(16)]
    da = [io.read(road.SPRITE_DATA_BASE + 0x10 * slot + i) for i in range(16)]
    print(f"  [after, same slot {slot}] state {[hex(b) for b in st]} data {[hex(b) for b in da]}", flush=True)
# a trainer that is still there, for contrast
for s in range(16):
    da = [io.read(road.SPRITE_DATA_BASE + 0x10 * s + i) for i in range(16)]
    st = [io.read(road.SPRITE_STATE_BASE + 0x10 * s + i) for i in range(16)]
    if (da[5] - 4, da[4] - 4) == (17, 12):
        print(f"  [trainer (17,12)] slot {s}: state {[hex(b) for b in st]} data {[hex(b) for b in da]}", flush=True)
rig.finish(outcome="probe sprite bytes", goals="hidden marker")
