"""Push B3's boulders toward the 0x12 tiles (the holes), with long holds, watching the sprite table.

ROM tiles (map 161): boulders (5,14) (3,15) (8,14) (9,14); 0x12 at (7,14) (4,15) (4,16) (9,16); the
row above (5,14) is solid 0x10. Plan: (3,15) RIGHT from (2,15) -> (4,15); (9,14) DOWN from (9,13)
-> (9,15) -> (9,16); (8,14) LEFT from (9,14)'s cell once it is vacated -> (7,14).
"""

import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_loop_stuck_3.state", settle_on_boot=True)
PUSHES = [((9, 13), "down", 2), ((2, 15), "right", 1), ((9, 15), "up", 1), ((9, 14), "left", 1)]


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def sprites():
    return sorted(tuple(b[:3]) if isinstance(b, (tuple, list)) else b for b in rig.bodies())[:8]


drain()
print("activate:", rig.use_field_move("STRENGTH", species="Gyarados"), flush=True)
for _ in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(40)
drain()
print("sprites:", sprites(), flush=True)
for stand, key, times in PUSHES:
    drain()
    w = rig.walk(161, {stand}, battle=rig.battle)
    drain()
    if rig.pos()[1:] != stand:
        print(f"stand {stand}: unreachable ({w}), at {rig.pos()[1:]}", flush=True)
        continue
    rig.io.press(key, hold=4, release=8)
    rig.ctl.wait(20)
    for n in range(times):
        for hold in (16, 40):
            drain()
            before, sb = rig.pos(), sprites()
            rig.io.press(key, hold=hold, release=16)
            rig.ctl.wait(70)
            moved = rig.pos() != before or sprites() != sb
            print(f"{stand} {key} #{n} hold {hold}: {before[1:]}->{rig.pos()[1:]} {sb}->{sprites()}", flush=True)
            rig.screenshot(f"push_{stand[0]}_{stand[1]}_{key}_{hold}")
            if moved:
                rig.bank(f"b3_push_{stand[0]}_{stand[1]}_{key}")
                print("*** MOVED ***", flush=True)
                break
print("final", rig.pos(), "sprites:", sprites(), flush=True)
