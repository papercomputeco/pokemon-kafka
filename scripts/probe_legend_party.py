"""Cinnabar Center (171): deposit one party member into Bill's PC, WITHDRAW the caught legendary, and try to teach
it HM02 FLY -- the roster's ABLE / NOT ABLE caption (rig.teach) is the cartridge's verdict. Bank legend_party."""

import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/legend_cinnabar.state"
DEPOSIT_INDEX = int(sys.argv[2]) if len(sys.argv) > 2 else 2  # Primeape: the member with no HM
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


def names():
    return [n for n, _l, _h in rig.party()]


def pc_withdraw_first() -> str | None:
    """Mirror of pc_deposit: BILL -> WITHDRAW -> first box entry -> confirm; the party growing is the proof."""
    spot = rig.center_pc(rig.pos()[0])
    if spot is None or not rig.approach({spot[0]}):
        print("  no PC spot / could not approach", flush=True)
        return None
    before = names()
    rig.ctl.press(spot[1])
    rig.ctl.wait(25)
    for _ in range(4):
        rig.ctl.press("a")
        rig.ctl.wait(55)
        if rig.menu_rows():
            break
    if not rig.menu_choose("BILL"):
        print("  no BILL entry:", rig.menu_rows(), flush=True)
        return None
    if not rig.advance_text("WITHDRAW"):
        print("  box submenu never showed WITHDRAW:", rig.menu_rows(), flush=True)
        return None
    if not rig.menu_choose("WITHDRAW"):
        return None
    rig.ctl.wait(40)
    print("  box list:", rig.menu_rows(), flush=True)
    rig.menu_cursor_to(0)
    rig.ctl.press("a")
    rig.ctl.wait(50)
    print("  confirm menu:", rig.menu_rows(), flush=True)
    for candidate in range(3):
        if not rig.menu_cursor_to(candidate, presses=6):
            continue
        rig.ctl.press("a")
        rig.ctl.wait(55)
        for _ in range(4):
            if len(names()) > len(before):
                break
            rig.ctl.press("a")
            rig.ctl.wait(45)
        if len(names()) > len(before):
            break
        rows = rig.menu_rows()
        if any("ATTACK" in t.upper() or "EXP POINTS" in t.upper() for _i, t in rows):
            for _ in range(3):
                rig.ctl.press("b")
                rig.ctl.wait(30)
    for _ in range(8):
        rig.ctl.press("b")
        rig.ctl.wait(25)
    after = names()
    new = [n for n in after if n not in before or after.count(n) > before.count(n)]
    print(f"  withdrew {new}; party now {after}", flush=True)
    return new[0] if new else None


print("start", rig.pos(), "party", names(), flush=True)
drain()
if rig.pos()[0] == 8:
    print("to the Center door (11,12):", rig.walk(8, {(11, 12)}, battle=rig.battle), rig.pos(), flush=True)
    for _ in range(3):
        if rig.pos()[0] != 8:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
print("inside:", rig.pos(), flush=True)
if rig.pos()[0] == 171:
    drain()
    dep = rig.pc_deposit(DEPOSIT_INDEX)
    print("deposit:", dep, names(), flush=True)
    drain()
    got = pc_withdraw_first()
    print("withdraw:", got, names(), flush=True)
    drain()
    if got:
        rig.bank("legend_party")
        idx = rig.teach("HM02 FLY", species=got)
        drain()
        print(
            f"teach HM02 FLY to {got}: {idx} (party index or None) | knows FLY now:",
            rig.knows_move("FLY", species=got),
            flush=True,
        )
        rig.screenshot("legend_teach_fly")
        if rig.knows_move("FLY", species=got) is not None:
            rig.bank("legend_flies")
            print("*** the legendary knows FLY -- banked legend_flies ***", flush=True)
print("final", rig.pos(), names(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
