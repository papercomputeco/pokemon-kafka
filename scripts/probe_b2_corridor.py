"""B2 (160): which column lets you step from row 9 to row 10 toward the (25,11) stair? Read each refusal."""

import json
import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/seafoam_loop_stuck_6.state", settle_on_boot=True)
truth = json.load(open("references/rom_truth.json"))
m = truth["maps"]["160"]
print("start", rig.pos(), flush=True)
for x in (23, 24, 25, 26):
    t9, t10 = m["tiles"][9][2 * x : 2 * x + 2], m["tiles"][10][2 * x : 2 * x + 2]
    w = rig.walk(160, {(x, 9)}, battle=rig.battle)
    if rig.pos()[1:] != (x, 9):
        print(f"x={x}: could not stand at ({x},9) ({w}); at {rig.pos()[1:]}", flush=True)
        continue
    before = rig.pos()
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(40)
    moved = rig.pos() != before
    print(f"x={x}: {t9}->{t10}: DOWN from ({x},9) -> {rig.pos()[1:]} moved={moved}", repr(rig.textbox()), flush=True)
    if rig.pos() != before:
        rig.bank("b2_row10")
        print("*** through at column", x, "***", flush=True)
        break
