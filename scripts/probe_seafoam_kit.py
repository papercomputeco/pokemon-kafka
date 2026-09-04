"""Stage 1 of the legendary run: free two bag slots and buy the kit at Cinnabar's mart (172) -- ULTRA BALL x30 and
MAX REPEL x8 -- on the main baton. Bank seafoam_kit. Stock order measured 2026-09-04: ULTRA BALL, GREAT BALL,
HYPER POTION, MAX REPEL, FULL HEAL, REVIVE (counter (2,5) facing left)."""

import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

ULTRA_BALL, MAX_REPEL = 2, 57
CINNABAR_MART = qm.Shop(8, (15, 11), 172, (2, 5), "left", (ULTRA_BALL, 3, 18, MAX_REPEL, 52, 53), ((3, 7), (4, 7)))
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/cinnabar_mart.state"
BALLS = int(sys.argv[2]) if len(sys.argv) > 2 else 30
REPELS = int(sys.argv[3]) if len(sys.argv) > 3 else 8
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def drain(n=14):
    for _ in range(n):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


print("start", rig.pos(), "money", qm.read_money(rig.io), "bag", len(rig.bag()), flush=True)
drain()
for _ in range(3):
    if len(rig.bag()) <= 18:
        break
    print("make_room:", rig.make_room(), "bag now", len(rig.bag()), flush=True)
    drain()
print("walk to the counter:", rig.walk(172, {(2, 5)}, battle=rig.battle), rig.pos(), flush=True)
drain()
bought = qm.buy(rig.io, CINNABAR_MART, [(ULTRA_BALL, BALLS), (MAX_REPEL, REPELS)])
drain()
print("bought:", bought, "money", qm.read_money(rig.io), flush=True)
print("bag:", rig.bag_named(full=True), flush=True)
names = dict(rig.bag_named(full=True))
if names.get("ULTRA BALL", 0) >= BALLS and names.get("MAX REPEL", 0) >= REPELS:
    rig.bank("seafoam_kit")
    print("*** KIT BANKED ***", flush=True)
else:
    rig.bank("seafoam_kit_partial")
print("final", rig.pos(), flush=True)
