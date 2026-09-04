#!/usr/bin/env python3
"""Fuchsia's mart: 30 -> 7 -> 152, buy as many REPEL (or MAX REPEL) as the bag can hold.

Every fact here is from this cartridge or the screen:

* ``30 -north edge-> 7`` is a *land* cross — map 30's north row holds walkable cells, the
  land BFS reaches (13,0) from the baton tile, and ``water`` tiles never stand between.
* Map 7's first warp (extracted) is ``[5, 13, 152, 0]``; ``road.counter_stands((0,5))``
  gives the across-the-counter cell (2,5) facing left on the 8x8 tileset-2 room.
* Which REPEL the clerk offers, at what price, is read off the live menu — the bag delta and
  the BCD money delta are the verdict, never a recalled item table.

Usage:  uv run python scripts/buy_repel_leg.py [state-file]
        (defaults to data/local_runs/roster-bench/b8_BATON_island_gyarados_safe.state)
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import quartermaster as qm  # noqa: E402
from expedition_rig import BattleWedge, Rig  # noqa: E402

WORKSPACE = SCRIPT_DIR.parent
BANK_DIR = WORKSPACE / "data" / "local_runs" / "roster-bench"
BATON = BANK_DIR / "b8_BATON_island_gyarados_safe.state"
STACK_CAP = 99  # a bag quantity byte; the game itself enforces it
RESERVE_MONEY = 100  # leave the party able to buy a potion somewhere
# Preference is a policy choice, the stock is read live: MAX first (the crossing wants the
# longer shield), plain REPEL next, SUPER REPEL if nothing else is offered.
CANDIDATES = ("MAX REPEL", "REPEL", "SUPER REPEL")


def log(*args) -> None:
    print(*args, flush=True)


def entry_index(rows: list[tuple[int, str]], hit: int) -> int:
    """Cursor index of the row at ``hit`` — the same block arithmetic the PC roster used
    (entries two rows apart, levels/labels interleaved on the odd rows are not entries)."""
    present = {i for i, _t in rows}
    block = hit
    while block - 2 in present and block - 1 not in present:
        block -= 2
    return (hit - block) // 2


def pick_candidate(rows: list[tuple[int, str]]) -> tuple[str, int, int] | None:
    """(name, row, cursor index) of the best offered repel, matched on the live text."""
    for name in CANDIDATES:
        for i, t in rows:
            tu = t.upper()
            if "REPEL" not in tu:
                continue
            if name in tu and not any(o in tu for o in ("MAX", "SUPER") if o not in name):
                return name, i, entry_index(rows, i)
    return None


def open_stock(rig: Rig) -> list[tuple[int, str]] | None:
    """Stand at (2,5) facing left and bring up the clerk's item list. The menu registers are
    the predicate; the greeting pages are A'd through without looking at anything else."""
    io = rig.io
    io.press("left")
    io.wait(30)
    for _ in range(30):
        if qm.menu_state(io)[1:] == (2, qm.TEXT_SHOP_MENU):
            break
        io.press("a")
        io.wait(25)
    if qm.menu_state(io)[1:] != (2, qm.TEXT_SHOP_MENU):
        rig.emit("repel.refusal", phase="open", state=list(qm.menu_state(io)), rows=rig.menu_rows())
        shot = rig.shot(BANK_DIR / "repel_open_refused.png")
        log("the shop menu will not open:", rig.menu_rows(), "screenshot:", shot)
        return None
    io.press("a")  # BUY is the top row in the clerk's own menu (verified at Cerulean, map 67)
    qm.settle(io, lambda: qm.menu_state(io)[2] == qm.TEXT_ITEM_LIST, lambda: io.press("a"), cap=6, label="item list")
    if qm.menu_state(io)[2] != qm.TEXT_ITEM_LIST:
        rig.emit("repel.refusal", phase="buy", state=list(qm.menu_state(io)), rows=rig.menu_rows())
        shot = rig.shot(BANK_DIR / "repel_buy_refused.png")
        log("the item list will not open:", rig.menu_rows(), "screenshot:", shot)
        return None
    rows = rig.menu_rows()
    rig.shot(BANK_DIR / "repel_stock.png")
    rig.emit("repel.stock", rows=[t for _i, t in rows])
    log("the clerk's stock:", rows)
    return rows


def buy_n(rig: Rig, name: str, index: int, count: int, iid: int) -> tuple[int, int]:
    """Buy ``count`` of the item at ``index``. Returns (actually bought, measured unit price)
    — both from the money/bag deltas, never from assumption."""
    io = rig.io
    if not rig.menu_cursor_to(index, presses=16):
        rig.emit("repel.refusal", phase="cursor", name=name, index=index)
        log(f"the cursor would not land on index {index} for {name}")
        return 0, 0
    money0 = qm.read_money(io)
    had = dict(rig.bag()).get(iid, 0)
    rig.ctl.press("a")  # item -> quantity selector
    rig.ctl.wait(40)
    for _ in range(max(0, count - 1)):  # the selector starts at 1 and WRAPS (measured in the
        rig.ctl.press("up")  # Hideout toss flow) — count-1 is the exact whole count, <= 98
        rig.ctl.wait(20)
    rig.ctl.press("a")  # -> "that'll be N. ok?"
    for strike in range(8):
        if qm.read_money(io) < money0:
            bought = max(0, dict(rig.bag()).get(iid, 0) - had)
            price = max(1, (money0 - qm.read_money(io)) // max(1, bought))
            return bought, price
        log(f"  strike {strike + 1}/8 — money has not moved; the game is refusing")
        rig.emit("repel.refusal", phase="confirm", name=name, count=count, money=money0)
        rig.ctl.press("a")
        rig.ctl.wait(40)
    return 0, 0


def main() -> int:
    started = sys.argv[1] if len(sys.argv) > 1 else str(BATON)
    rig = Rig(started)
    run_id = rig.run_id
    mp, x, y = rig.pos()
    money = qm.read_money(rig.io)
    log(f"== buy-repel leg from ({mp},{x},{y}) party={rig.party()} badges={rig.badges()} money={money}")
    log(f"bag {len(rig.bag())}/20: {rig.bag_named(full=True)}")
    rig.emit(
        "repel.open",
        from_state=str(started),
        pos=list(rig.pos()),
        bag=str(rig.bag_named()),
        money=money,
    )

    try:
        # ---- room, before anything else (the bag is 20/20) -------------------------------
        if rig.bag_full():
            log("bag is full — make_room frees one slot (the loss is measured, logged, and committed as a toss)")
            if not rig.make_room():
                log("!! no room could be freed; a purchase slot may still land but a pickup cannot")
            log(f"bag now {len(rig.bag())}/20: {rig.bag_named(full=True)}")
            rig.emit("repel.room", bag=str(rig.bag_named()))

        # ---- 30 -> 7 ----------------------------------------------------------------------
        if rig.pos()[0] == 30:
            log("-- hop 30 -> 7 (north edge, land)")
            res = rig.cross(30, 7)
            log("-- cross:", res, "now", rig.pos())
            rig.emit("repel.hop", a=30, b=7, result=str(res), pos=list(rig.pos()))
            if rig.pos()[0] != 7:
                shot = rig.shot(BANK_DIR / "repel_cross_refused.png")
                rig.emit("repel.refusal", phase="cross", res=str(res), shot=str(shot))
                log("!! the 30->7 hop refused:", res, "screenshot:", shot)
                return 2

        # ---- 7 -> 152, the mart -----------------------------------------------------------
        if rig.pos()[0] == 7:
            log("-- warp (5,13) into the mart")
            res = rig.warp(7, 5, 13)
            log("-- warp:", res, "now", rig.pos())
            rig.emit("repel.hop", a=7, b=152, result=str(res), pos=list(rig.pos()))
            if rig.pos()[0] != 152:
                shot = rig.shot(BANK_DIR / "repel_mart_door_refused.png")
                rig.emit("repel.refusal", phase="door", res=str(res), shot=str(shot))
                log("!! the door refused:", res, "screenshot:", shot)
                return 2
            ok = rig.walk(152, {(2, 5)}, cap=300)
            log("-- walk to counter stand (2,5):", ok, "at", rig.pos())
            rig.emit("repel.counter", walk=str(ok), pos=list(rig.pos()))
            if rig.pos() != (152, 2, 5):
                shot = rig.shot(BANK_DIR / "repel_counter_unreached.png")
                log("!! the counter stand is unreachable:", ok, "screenshot:", shot)
                rig.emit("repel.refusal", phase="counter", res=str(ok), shot=str(shot))
                return 2

        # ---- the counter ------------------------------------------------------------------
        if rig.pos()[0] != 152:
            log(f"== on map {rig.pos()[0]}, not the mart — bank and stop")
            rig.bank("repel_stopped", directory=BANK_DIR)
            return 3

        rows = open_stock(rig)
        if rows is None:
            rig.bank("repel_stopped", directory=BANK_DIR)
            return 4
        pick = pick_candidate(rows)
        if pick is None:
            rig.emit("repel.now_offer", rows=[t for _i, t in rows])
            log("!! no REPEL-grade item is offered today; stock was:", rows)
            for _ in range(6):
                if qm.menu_state(rig.io)[2] not in (qm.TEXT_SHOP_MENU, qm.TEXT_ITEM_LIST):
                    break
                rig.ctl.press("b")
                rig.ctl.wait(20)
            rig.settle()
            rig.bank("repel_not_stocked", directory=BANK_DIR)
            return 5
        name, row, index = pick
        log(f"buying {name} (row {row}, cursor index {index})")

        def item_id(nm: str) -> int:
            for k, v in rig.truth.get("items", {}).items():
                if v == nm:
                    return int(k)
            raise SystemExit(f"the cart has no item named {nm!r}")

        iid = item_id(name)
        price = 0
        total = 0
        # Stage 1: one unit — the game then tells us the price by taking exactly that much.
        bought, price = buy_n(rig, name, index, 1, iid)
        total += bought
        log(f"stage 1: bought {bought} @ measured unit price {price}")
        rig.emit("repel.bought1", item=name, qty=bought, price=price, money=qm.read_money(rig.io))
        if bought == 0:
            rig.bank("repel_unaffordable", directory=BANK_DIR)
            return 6
        money = qm.read_money(rig.io)
        headroom = min(STACK_CAP - total, (money - RESERVE_MONEY) // max(1, price))
        log(f"stage 2: {headroom} more fit (cap {STACK_CAP - total}, money {money}, price {price})")
        if headroom >= 2:
            if qm.menu_state(rig.io)[2] != qm.TEXT_ITEM_LIST:
                # back at the item list, confirmed by the register; A through anything else
                for _ in range(6):
                    if qm.menu_state(rig.io)[2] == qm.TEXT_ITEM_LIST:
                        break
                    rig.ctl.press("a")
                    rig.ctl.wait(30)
            bought, price2 = buy_n(rig, name, index, headroom, iid)
            if price2:
                price = price2
            total += bought
            log(f"stage 2: bought {bought}")
            rig.emit("repel.bought2", item=name, qty=bought, money=qm.read_money(rig.io))

        # out of the menus, verified by the register
        for _ in range(8):
            if qm.menu_state(rig.io)[2] not in (qm.TEXT_SHOP_MENU, qm.TEXT_ITEM_LIST):
                break
            rig.ctl.press("b")
            rig.ctl.wait(20)
        rig.settle()
        bag_named = rig.bag_named(full=True)
        repel_now = [n for n in bag_named if name in n[0]]
        log(f"== {name} in bag now: {repel_now}; money {qm.read_money(rig.io)}; bag {len(rig.bag())}/20: {bag_named}")
        rig.emit(
            "repel.done",
            item=name,
            total=total,
            price=price,
            money=qm.read_money(rig.io),
            bag=str(bag_named),
            pos=list(rig.pos()),
        )
        if total == 0:
            rig.bank("repel_stopped", directory=BANK_DIR)
            return 7
        out = rig.bank("repel_bought", directory=BANK_DIR)
        log(f"== banked {out.name}; run {run_id}")
        rig.emit("repel.bank", path=str(out), pos=list(rig.pos()))
        return 0
    except BattleWedge as e:
        log(f"BATTLE WEDGE: {e}")
        rig.emit("repel.wedge", err=str(e), pos=list(rig.pos()))
        rig.bank("repel_wedged", directory=BANK_DIR)
        return 8


if __name__ == "__main__":
    raise SystemExit(main())
