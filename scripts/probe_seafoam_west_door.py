"""Bank a baton inside Seafoam at its west door, with Surf and Strength on a standing member.

Route 20 arrival water -> row 4 west -> island (61,4) -> the island's middle land at (48,6) ->
step UP onto the door tile (48,5) -> map 192 at warp 0. Every step is a measured tile fact.
"""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/merged_on_31.state", settle_on_boot=True)


def drain(limit=14):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def step(key):
    drain()
    before = rig.pos()
    rig.io.press(key, hold=8, release=8)
    rig.ctl.wait(30)
    drain()
    return rig.pos() != before


refusals = 0
while rig.pos()[1] > 61 and refusals < 3:
    refusals = 0 if step("left") else refusals + 1
print("island:", rig.pos(), flush=True)
assert rig.pos()[1] <= 61
print("walk to (48,6):", rig.walk(31, {(48, 6)}, battle=rig.battle), rig.pos(), flush=True)
rig.bank("island_north")
for _ in range(3):
    step("up")
    if rig.pos()[0] == 192:
        break
print("after the door:", rig.pos(), flush=True)
rig.screenshot("seafoam_west_door")
if rig.pos()[0] == 192:
    rig.bank("seafoam_west_door")
    print("banked seafoam_west_door | surf:", rig.knows_move("SURF"), "str:", rig.knows_move("STRENGTH"), flush=True)
