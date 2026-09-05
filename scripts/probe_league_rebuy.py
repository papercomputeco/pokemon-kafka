"""Re-buy the League balls and medicine at Cinnabar (the room plan tossed them): read the shop rows one scroll at a
time first (the measurement), then buy ULTRA BALL x20, HYPER POTION x5, REVIVE x5; fly back to Viridian."""

import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/viridian_league.state"
PLAN = [(qm.ULTRA_BALL, 20), (qm.HYPER_POTION, 5), (qm.REVIVE, 5)]
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
if rig.pos()[0] == 1:
    print("fly:", rig.fly_to("CINNABAR ISLAND"), rig.pos(), flush=True)
    drain()
if rig.pos()[0] == 8:
    need = len(PLAN) - (20 - len(rig.bag()))
    for _ in range(max(0, need)):
        print("make_room:", rig.make_room(), flush=True)
        drain()
    if door(8, (15, 12), "up", 172):
        rig.walk(172, {(2, 5)}, battle=rig.battle)
        drain()
        # the measurement: every row, one scroll step at a time
        rig.io.press("left", hold=4, release=8)
        rig.ctl.wait(12)
        for _ in range(6):
            rig.ctl.press("a")
            rig.ctl.wait(40)
            if qm.menu_state(rig.io)[1:] == (2, qm.TEXT_SHOP_MENU):
                break
        rig.ctl.press("a")
        rig.ctl.wait(40)
        for _ in range(4):
            if qm.menu_state(rig.io)[2] == qm.TEXT_ITEM_LIST:
                break
            rig.ctl.press("a")
            rig.ctl.wait(40)
        seen = []
        for _ in range(10):
            rows = [t for _i, t in rig.menu_rows(3, 12)]
            for t in rows:
                if t and t not in seen and not t[0].isdigit() and "MONEY" not in t and "BUY" not in t:
                    seen.append(t)
            rig.ctl.press("down")
            rig.ctl.wait(14)
        print("STOCK IN ORDER:", seen, flush=True)
        for _ in range(8):
            rig.ctl.press("b")
            rig.ctl.wait(20)
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
    print("fly:", rig.fly_to("VIRIDIAN CITY"), rig.pos(), flush=True)
    drain()
if rig.pos()[0] == 1:
    d = dict(rig.bag_named(full=True))
    if d.get("ULTRA BALL", 0) >= 15 and d.get("REVIVE", 0) >= 3:
        rig.bank("viridian_kit")
        print("*** banked viridian_kit ***", flush=True)
    else:
        rig.bank("viridian_kit_partial")
print("final", rig.pos(), flush=True)
