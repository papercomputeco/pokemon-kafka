"""Activate STRENGTH, then push every B3 boulder from a reachable side, draining text before each press.

Measured first: 'GYARADOS used STRENGTH.' -> 'GYARADOS can move boulders.' A push pressed onto a
post-battle EXP page reads as refused; so every press here follows a drain. Verdict per boulder:
did our position change into its tile, and what did the screen say.
"""

import json
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import road  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

MAP = 161
rig = Rig("data/local_runs/roster-bench/seafoam_loop_stuck_3.state", settle_on_boot=True)
truth = json.load(open("references/rom_truth.json"))
pairs = rt.loaded_pairs(truth)
m = truth["maps"][str(MAP)]
boulders = [(s["x"], s["y"]) for s in m["sprites"] if s.get("pic") == 63]
print("start", rig.pos(), "boulders:", boulders, flush=True)


def drain(limit=16):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


drain()
print("activate:", rig.use_field_move("STRENGTH", species="Gyarados"), repr(rig.textbox()), flush=True)
for _ in range(6):
    rig.ctl.press("a")
    rig.ctl.wait(40)
drain()

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
region = road.reachable(truth, pairs, MAP, rig.pos()[1:], blocked=set(boulders))
results = []
for bx, by in boulders:
    tried = False
    for key, (dx, dy) in DIRS.items():
        stand = (bx - dx, by - dy)  # stand on the far side, facing the boulder
        if stand not in region:
            continue
        tried = True
        drain()
        w = rig.walk(MAP, {stand}, battle=rig.battle)
        drain()
        if rig.pos()[1:] != stand:
            results.append((bx, by, key, f"could not stand at {stand}: {w}"))
            continue
        rig.io.press(key, hold=4, release=8)  # face it
        rig.ctl.wait(20)
        drain()
        before = rig.pos()
        rig.io.press(key, hold=8, release=8)
        rig.ctl.wait(50)
        said = rig.textbox()
        moved = rig.pos() != before
        results.append((bx, by, key, f"moved={moved} now={rig.pos()[1:]} said={said!r}"))
        print(f"boulder {(bx, by)} pushed {key} from {stand}: moved={moved} now={rig.pos()[1:]} {said!r}", flush=True)
        rig.screenshot(f"push_{bx}_{by}_{key}")
        drain()
        if moved:
            rig.bank(f"b3_pushed_{bx}_{by}")
            region = road.reachable(truth, pairs, MAP, rig.pos()[1:], blocked=set(boulders))
        break
    if not tried:
        results.append((bx, by, "-", "no reachable side"))
        print(f"boulder {(bx, by)}: no reachable side from here", flush=True)
print("final", rig.pos(), flush=True)
