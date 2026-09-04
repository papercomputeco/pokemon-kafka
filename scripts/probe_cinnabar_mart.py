"""Cinnabar mart (map 8 door (15,11) -> 172): read the shop's stock rows so MAX REPEL / ULTRA BALL can be bought
by index, and read which status moves the party knows for a no-damage catch. Main baton: healed_cinnabar.state."""

import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/healed_cinnabar.state"
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


print("start", rig.pos(), "money", qm.read_money(rig.io), flush=True)
from expedition_rig import ADDR_PARTY_STRUCTS, MOVE_SLOTS, PARTY_STRUCT_SIZE  # noqa: E402

names = {v: k for k, v in rig._move_ids().items()}
for i, (nm, lvl, hp) in enumerate(rig.party()):
    base = ADDR_PARTY_STRUCTS + PARTY_STRUCT_SIZE * i
    print(
        f"  {i} {nm} L{lvl} hp{hp}: {[names.get(rig.mem[base + o], hex(rig.mem[base + o])) for o in MOVE_SLOTS]}",
        flush=True,
    )
for mv in (
    "HYPNOSIS",
    "SING",
    "SLEEP POWDER",
    "SPORE",
    "THUNDER WAVE",
    "STUN SPORE",
    "GLARE",
    "LEER",
    "GROWL",
    "TACKLE",
    "BITE",
    "SPLASH",
    "CONFUSION",
    "PSYCHIC",
    "HEADBUTT",
    "DISABLE",
    "SUPERSONIC",
    "SAND-ATTACK",
    "SCREECH",
):
    i = rig.knows_move(mv)
    if i is not None:
        print(f"  knows {mv}: party index {i} ({rig.party()[i][0]})", flush=True)
drain()
# out of the Center (mats (3,7)/(4,7)) then to the mart door (15,11), then in
if rig.pos()[0] == 171:
    rig.walk(171, {(3, 6), (4, 6)}, battle=rig.battle)
    for _ in range(4):  # onto the mat, then through it: interior doors warp on the second step
        if rig.pos()[0] != 171:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
print("outside:", rig.pos(), flush=True)
if rig.pos()[0] == 8:
    print("below the mart door (15,12):", rig.walk(8, {(15, 12)}, battle=rig.battle), rig.pos(), flush=True)
    for _ in range(3):
        if rig.pos()[0] != 8:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
print("inside?", rig.pos(), flush=True)
if rig.pos()[0] == 172:
    rig.bank("cinnabar_mart")
    print("sprites:", sorted(tuple(b[:2]) for b in rig.bodies()), flush=True)
    w = rig.walk(172, {(2, 5)}, battle=rig.battle)
    print("counter (2,5):", w, rig.pos(), flush=True)
    rig.io.press("left", hold=4, release=8)
    rig.ctl.wait(12)
    pages = []
    for _ in range(6):
        rig.ctl.press("a")
        rig.ctl.wait(40)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
        if qm.menu_state(rig.io)[1:] == (2, qm.TEXT_SHOP_MENU):
            break
    print("clerk:", pages, "menu", qm.menu_state(rig.io), flush=True)
    rig.ctl.press("a")  # BUY
    rig.ctl.wait(40)
    for _ in range(4):
        if qm.menu_state(rig.io)[2] == qm.TEXT_ITEM_LIST:
            break
        rig.ctl.press("a")
        rig.ctl.wait(40)
    rig.screenshot("cinnabar_mart_list")
    rows = rig.menu_rows(0, 18)
    print("STOCK ROWS:", rows, flush=True)
    # scroll the list to see everything
    seen = [r for r in rows]
    for _ in range(8):
        rig.ctl.press("down")
        rig.ctl.wait(12)
        more = rig.menu_rows(0, 18)
        if more != rows:
            rows = more
            seen.append(more)
    print("AFTER SCROLL:", rows, flush=True)
    for _ in range(6):
        rig.ctl.press("b")
        rig.ctl.wait(20)
print("final", rig.pos(), flush=True)
