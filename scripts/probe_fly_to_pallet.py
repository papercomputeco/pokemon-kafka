"""Teach FLY, leave the Route 16 house, fly to PALLET TOWN, bank. The Cinnabar leg starts there."""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/all_hms.state"
rig = Rig(STATE, settle_on_boot=True)
print("start", rig.pos(), flush=True)
if rig.knows_move("FLY") is None:
    print("teach HM02 ->", rig.teach("HM02"), "| flyer:", rig.knows_move("FLY"), flush=True)
if rig.knows_move("FLY") is None:
    sys.exit(2)
print("walk to (2,6):", rig.walk(188, {(2, 6)}, battle=rig.battle), rig.pos(), flush=True)
for _ in range(3):
    if rig.pos()[0] != 188:
        break
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(60)
print("outside:", rig.pos(), flush=True)
ok = rig.fly_to("PALLET TOWN")
print("fly_to Pallet:", ok, rig.pos(), flush=True)
rig.screenshot("pallet_arrival")
if ok:
    rig.bank("all_hms_pallet")
    print("*** PALLET TOWN ***", rig.pos(), "| surfer:", rig.knows_move("SURF"), flush=True)
