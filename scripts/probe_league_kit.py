"""League kit on the main baton: from the mansion, Cinnabar's mart with the scroll-aware buy (MAX REPEL x8,
FULL HEAL x5, REVIVE x5), then FLY to Viridian and bank viridian_league. Bag slots are freed with make_room."""

import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/grind_hypno.state"
PLAN = [(qm.MAX_REPEL, 8), (qm.FULL_HEAL, 5), (qm.REVIVE, 5)]
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
SHOP = qm.SHOPS[8]


def drain(n=14):
    for _ in range(n):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def door(mp, stand, key, want):
    rig.walk(mp, {stand}, battle=rig.battle)
    for _ in range(3):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(90)
        drain()
    return rig.pos()[0] == want


print("start", rig.pos(), "money", qm.read_money(rig.io), "bag", len(rig.bag()), flush=True)
drain()
if rig.pos()[0] == 165:
    door(165, (5, 26), "down", 8)
if rig.pos()[0] == 8:
    need = len(PLAN) - (20 - len(rig.bag()))
    for _ in range(max(0, need)):
        print("make_room:", rig.make_room(), flush=True)
        drain()
    if door(8, (15, 12), "up", 172):
        rig.walk(172, {(2, 5)}, battle=rig.battle)
        drain()
        bought = qm.buy(rig.io, SHOP, PLAN)
        drain()
        print("bought:", bought, "money", qm.read_money(rig.io), flush=True)
        print("bag:", rig.bag_named(full=True), flush=True)
        rig.walk(172, {(3, 5)}, battle=rig.battle)
        rig.walk(172, {(3, 6)}, battle=rig.battle)
        for _ in range(3):
            if rig.pos()[0] != 172:
                break
            rig.io.press("down", hold=16, release=16)
            rig.ctl.wait(90)
            drain()
if rig.pos()[0] == 8:
    rig.bank("league_kit_cinnabar")
    print("fly:", rig.fly_to("VIRIDIAN CITY"), rig.pos(), flush=True)
    drain()
if rig.pos()[0] == 1:
    rig.bank("viridian_league")
    print("*** banked viridian_league ***", rig.pos(), flush=True)
print("final", rig.pos(), [(n, lv, hp) for n, lv, hp in rig.party()], flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
