#!/usr/bin/env python3
"""Probe the Cinnabar mart clerk flow, one measured step at a time. NO purchases: the probe
walks greet -> menu -> list -> band and decodes the whole screen (all 18 rows, 32 chars) at
every state, reading the menu registers and money at each step. It stops at the quantity
band and B's back out. The decode is the map of the flow; the next leg drives from it."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

BANK_DIR = SCRIPT_DIR.parent / "data" / "local_runs" / "roster-bench"
CLEAN = BANK_DIR / "b8_mart_counter_clean.state"


def log(*a):
    print(*a, flush=True)


def state(rig) -> str:
    cur, mx, tid = qm.menu_state(rig.io)
    return f"cur={cur} max={mx} id={tid} money={qm.read_money(rig.io)}"


def main() -> int:
    rig = Rig(str(CLEAN))
    log(f"== at {rig.pos()} bag={len(rig.bag())}/20")
    rig.emit("shopprobe.open", pos=list(rig.pos()), state=state(rig))

    def show(label: str):
        log(f"---- {label} :: {state(rig)}")
        log(f"     rows: {rig.menu_rows()}")
        try:
            rig.shot(BANK_DIR / f"probe_{Path(label).name}.png")
        except Exception:
            pass
        rig.emit("shopprobe.screen", label=label, state=state(rig), rows=[(i, s) for i, s in rig.menu_rows()])

    show("00_parked")
    # A advances the clerk box / pages until the shop menu or the list shows. Never blind:
    # each A is read back with the full register+row state.
    for n in range(1, 7):
        tid = qm.menu_state(rig.io)[2]
        if tid in (qm.TEXT_SHOP_MENU, qm.TEXT_ITEM_LIST):
            show(f"0n_flow_{tid}")
            break
        rig.ctl.press("a")
        rig.ctl.wait(60)
        show(f"0n_a{n}")
    tid = qm.menu_state(rig.io)[2]
    if tid == qm.TEXT_SHOP_MENU:
        # walk the menu cursor over every entry and read it, so BUY/SELL/QUIT are measured,
        # not assumed; the cursor register is the position, not the rows
        seen = []
        for key in ("down", "down", "down", "up"):
            rig.ctl.press(key)
            rig.ctl.wait(40)
            cur, mx, tid = qm.menu_state(rig.io)
            seen.append((key, cur, mx))
            log(f"-- menu {key} -> cur={cur} max={mx} id={tid}")
            rig.emit("shopprobe.menu_cursor", trail=seen)
        while qm.menu_state(rig.io)[0] != 0:
            rig.ctl.press("up")
            rig.ctl.wait(30)
        rig.ctl.press("a")  # cursor 0 = BUY (top entry, measured above); A here cannot buy
        rig.ctl.wait(80)
    # the list: scroll page by page with measured downs until the page stops moving
    show("list_0")
    prev = None
    for s in range(14):
        rowtxt = "|".join(t for _i, t in rig.menu_rows())
        if rowtxt == prev:
            log("== list stopped scrolling — bottom reached")
            break
        prev = rowtxt
        rig.ctl.press("down")
        rig.ctl.wait(40)
        show(f"list_{s + 1}")
    # the quantity band: A on the list. Do NOT press A on the band (v1 proved it buys).
    rig.ctl.press("a")
    rig.ctl.wait(80)
    show("band_open")
    log(f"== band state: money={qm.read_money(rig.io)} bag={rig.bag_named(full=True)}")
    # back out: B at every level (each one measured); then a clean baton for the buying leg.
    for n in range(6):
        tid = qm.menu_state(rig.io)[2]
        if (
            tid not in (qm.TEXT_SHOP_MENU, qm.TEXT_ITEM_LIST)
            and "HOW MANY" not in " ".join(t for _i, t in rig.menu_rows()).upper()
        ):
            break
        rig.ctl.press("b")
        rig.ctl.wait(60)
        show(f"back_out_{n}")
    log("== probe complete")
    rig.bank("b8_mart_counter_map", directory=BANK_DIR)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
