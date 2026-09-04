#!/usr/bin/env python3
"""Fuchsia's mart (152): buy as many REPEL (or MAX REPEL) as the bag can hold.

v2, after the v1 incident: the clerk's UI does NOT behave like Cerulean's. v1 assumed
(shop extent 2, A-advances-everything) and an A-spam loop bought 3x ULTRA BALL by accident
— caught by the bag delta, which is why every purchase here is gated on BOTH the money
delta and the bag delta, and every keypress is bracketed by a state+rows read. Measured so
far (this cartridge, these screens):

* the item list shows a "How many? <n>" quantity band; A-presses inside that band can
  change the quantity rather than buy (v1 parked at "How many? 3" with the 3x ULTRA only
  in the bag after a settle-A)
* the money is 3 BCD bytes at 0xD347 (hex-digit read); the bag delta is the verdict
* which REPEL is offered and its price are read off the live screen and the deltas — never
  recalled.

Resume: starts from the parked state if given (B's out of any open shop screen, banks a
clean snapshot), then drives: greet -> list -> find REPEL row -> buy cycles verified by
deltas until the 99-stack is full or the game refuses.

Usage:  uv run python scripts/buy_repel_leg.py [state-file]
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
BANKED = BANK_DIR / "repel_stopped.state"  # parked at the counter, "How many? 3" band open
STACK_CAP = 99
RESERVE_MONEY = 100
# Preference is policy, not a claim about the stock; the stock is read live.
CANDIDATES = ("MAX REPEL", "REPEL", "SUPER REPEL")


def log(*args) -> None:
    print(*args, flush=True)


def rows(rig: Rig) -> list[tuple[int, str]]:
    return rig.menu_rows()


def tx(rig: Rig) -> str:
    return " ".join(t for _i, t in rows(rig)).upper()


def state(rig: Rig) -> tuple[int, int, int]:
    return qm.menu_state(rig.io)


def in_shop_tx(rig: Rig) -> bool:
    t = tx(rig)
    return any(tok in t for tok in ("HOW MANY", "BUY", "SELL", "QUIT", "THAT'LL", "THAT WILL"))


def advance(rig: Rig, key: str, wait: int = 40) -> None:
    """One keypress bracketed by before/after reads — the screen is the instruction stream."""
    before = (state(rig), tx(rig)[:70])
    rig.ctl.press(key)
    rig.ctl.wait(wait)
    after = (state(rig), tx(rig)[:70])
    log(f"  [{key}] {before[0]} {before[1]!r}\n        -> {after[0]} {after[1]!r}")
    rig.emit("repel.key", key=key, before=list(before[0]), after=list(after[0]), tx=after[1])


def money(rig: Rig) -> int:
    return qm.read_money(rig.io)


def bag_map(rig: Rig) -> dict[int, int]:
    return dict(rig.bag())


def repel_stack(rig: Rig) -> int:
    return sum(q for n, q in rig.bag_named(full=True) if "REPEL" in n.upper())


def escapeshop(rig: Rig, cap: int = 6) -> None:
    """B is the universal back here (band -> list -> menu -> map); A is NOT (it can buy).
    A money-guard records the screen state honestly if B were to commit a purchase instead."""
    m0 = money(rig)
    for _ in range(cap):
        if not in_shop_tx(rig) and state(rig)[2] not in (qm.TEXT_SHOP_MENU, qm.TEXT_ITEM_LIST):
            break
        advance(rig, "b")
    if money(rig) != m0:
        rig.emit("repel.gate", escapeshop_money_delta=m0 - money(rig), bag=str(rig.bag_named(full=True)))
        log("!! money moved during escape (delta", m0 - money(rig), ") — bag:", rig.bag_named(full=True))
    if in_shop_tx(rig):
        shot = rig.shot(BANK_DIR / "repel_escape_fail.png")
        log("!! could not B out of the shop screens; screenshot:", shot)


def find_repel_row(rig: Rig) -> tuple[str, int] | None:
    """(name, row) of the offered repel in the current window, preference per CANDIDATES."""
    for name in CANDIDATES:
        r, t = next(
            (
                (i, s)
                for i, s in rows(rig)
                if name in s.upper() and not any(o in s.upper() for o in ("MAX", "SUPER") if o not in name)
            ),
            None,
        )
        if r is not None:
            return name, r
    return None


def top_row(rig: Rig) -> tuple[int, str] | None:
    return next(((i, s) for i, s in rows(rig) if s.strip()), None)


def buy_one_verified(rig: Rig) -> tuple[int, int]:
    """Buy exactly ONE of the cursor's item, with the money delta + bag delta as the gate.
    Returns (bought, unit_price). 0/0 if the game refused. The confirmation presses are
    bounded: each A is immediately followed by a money read; a money drop closes the cycle."""
    m0, b0 = money(rig), bag_map(rig)
    # confirm the band is ours (a quantity band is on screen)
    if "HOW MANY" not in tx(rig):
        advance(rig, "a")  # list -> band
    bought, price = 0, 0
    for strike in range(4):
        if money(rig) < m0:
            now = bag_map(rig)
            delta_bag = {k: now[k] - b0.get(k, 0) for k in now if now[k] != b0.get(k, 0)}
            bought = sum(v for v in delta_bag.values() if v > 0)
            price = max(1, (m0 - money(rig)) // max(1, bought))
            if bought != 1:
                log(f"  !! gate: expected a 1x buy, deltas say bag {delta_bag} money {bought and (m0 - money(rig))}")
                rig.emit("repel.gate", bought=bought, delta=delta_bag)
            return bought, price
        # no money movement: A may just be nudging the band; check what's on screen, then A again
        advance(rig, "a")
        if "HOW MANY" not in tx(rig) and "REPEL" not in tx(rig) and not in_shop_tx(rig):
            rig.emit("repel.refusal", phase="confirm", tx=tx(rig)[:120])
            log("!! confirmation left the shop entirely; rows:", rows(rig))
            return 0, 0
    shot = rig.shot(BANK_DIR / "repel_confirm_stuck.png")
    rig.emit("repel.refusal", phase="confirm_stuck", tx=tx(rig)[:120], shot=str(shot))
    log("!! 4 bounded confirm presses moved no money; screenshot:", shot)
    if bag_map(rig) != b0:
        now2 = bag_map(rig)
        delta = {k: now2[k] - b0.get(k, 0) for k in now2 if now2[k] != b0.get(k, 0)}
        bought = sum(v for v in delta.values() if v > 0)
        price = max(1, (m0 - money(rig)) // max(1, bought))
    return bought, price


def main() -> int:
    started = sys.argv[1] if len(sys.argv) > 1 else str(BANKED)
    rig = Rig(started)
    log(f"== buy-repel from {rig.pos()} bag={len(rig.bag())}/20 money={money(rig)} stack_now={repel_stack(rig)}")
    rig.emit("repel.open", from_state=str(started), pos=list(rig.pos()), bag=str(rig.bag_named()), money=money(rig))

    try:
        # ---- recovery: B any open shop screen closed, then a clean snapshot --------------
        escapeshop(rig)
        rig.settle()
        rig.shot(BANK_DIR / "repel_clean.png")
        log("clean screen rows:", rows(rig), "pos:", rig.pos())
        rig.emit("repel.clean", pos=list(rig.pos()), tx=tx(rig)[:80])
        clean = rig.bank("b8_mart_counter_clean", directory=BANK_DIR)
        log(f"clean snapshot banked: {clean.name}")

        # ---- room (the bag is 20/20 with the accidental ULTRA stack on the line) ---------
        if rig.bag_full() and repel_stack(rig) == 0:
            log("bag full with no repel on board — make_room (the loss is the measured log line)")
            rig.make_room()
            log(f"bag now {len(rig.bag())}/20: {rig.bag_named(full=True)}")
            rig.emit("repel.room", bag=str(rig.bag_named()))

        # ---- the clerk: greet -> buy menu -> item list, every press measured --------------
        rig.ctl.press("left")
        rig.ctl.wait(40)
        for i in range(12):
            if state(rig)[2] == qm.TEXT_ITEM_LIST:
                break
            if state(rig)[2] == qm.TEXT_SHOP_MENU:
                advance(rig, "a")
                continue
            advance(rig, "a")
        if state(rig)[2] != qm.TEXT_ITEM_LIST:
            shot = rig.shot(BANK_DIR / "repel_list_refused.png")
            rig.emit("repel.refusal", phase="list", tx=tx(rig)[:120], shot=str(shot))
            log("!! never reached the item list:", rows(rig), "screenshot:", shot)
            escapeshop(rig)
            rig.bank("repel_stopped", directory=BANK_DIR)
            return 4

        rig.shot(BANK_DIR / "repel_stock.png")
        rig.emit("repel.stock", tx=tx(rig)[:200])
        log("stock window:", rows(rig))

        # ---- find the repel row; move the cursor by measured downs (cursor = window top) --
        name, hitrow = find_repel_row(rig)
        tops = 0
        while name is None and tops < 25:
            advance(rig, "down")
            name, hitrow = find_repel_row(rig)
            if name is None and top_row(rig) is None:
                break
            tops += 1
        if name is None:
            rig.emit("repel.not_stocked", tx=tx(rig)[:200])
            log("!! no REPEL-grade item found in 25 rows of scroll; stock window:", rows(rig))
            escapeshop(rig)
            rig.bank("repel_not_stocked", directory=BANK_DIR)
            return 5
        # cursor sits on the window's top entry (measured in v1's screen); walk it to the row
        moves = 0
        while top_row(rig) is not None and top_row(rig)[0] != hitrow and moves < 12:
            advance(rig, "down")
            moves += 1
            if find_repel_row(rig) is None and moves >= 2:
                log("  the repel row scrolled away — overshoot, stop")
                break
        if top_row(rig) is None or top_row(rig)[0] != hitrow:
            shot = rig.shot(BANK_DIR / "repel_cursor_refused.png")
            rig.emit("repel.refusal", phase="cursor", row=hitrow, top=top_row(rig), shot=str(shot))
            log("!! could not bring the cursor's row to", hitrow, "screenshot:", shot)
            escapeshop(rig)
            rig.bank("repel_stopped", directory=BANK_DIR)
            return 6
        log(f"cursor on {name!r} (row {hitrow}) after {moves} measured downs")
        rig.emit("repel.cursor", name=name, row=hitrow, moves=moves)

        # ---- the buy loop: verified one-units until the stack is full or it refuses --------
        total = 0
        price = 0
        rounds = 0
        while total < STACK_CAP and rounds < 120:
            rounds += 1
            m0 = money(rig)
            if m0 <= RESERVE_MONEY + 100:
                log("money floor reached, stopping the buy loop")
                break
            # (re)open the band on the cursor's entry: from the list, A opens "How many?"
            if "HOW MANY" not in tx(rig):
                if state(rig)[2] != qm.TEXT_ITEM_LIST:
                    # back at the list, verified by the register
                    advance(rig, "b")
                advance(rig, "a")
            bought, p = buy_one_verified(rig)
            total += bought
            price = p or price
            log(f"round {rounds}: +{bought} of {name} (total {total}) unit price {p or price} money {money(rig)}")
            rig.emit("repel.round", n=rounds, name=name, bought=bought, total=total, price=price, money=money(rig))
            if bought == 0:
                break
        final_stack = repel_stack(rig)
        log(f"== {name} stack in bag now: {final_stack}; money {money(rig)}; bag {len(rig.bag())}/20")
        rig.emit("repel.done", name=name, rounds=rounds, stack=final_stack, money=money(rig), bag=str(rig.bag_named()))

        escapeshop(rig)
        rig.settle()
        rig.shot(BANK_DIR / "repel_final.png")
        rig.emit("repel.final_screen", pos=list(rig.pos()), tx=tx(rig)[:80])
        bag_named = rig.bag_named(full=True)
        log(f"bag at end: {bag_named}")
        if final_stack == 0:
            rig.bank("repel_stopped", directory=BANK_DIR)
            return 7
        out = rig.bank("repel_bought", directory=BANK_DIR)
        log(f"== banked {out.name}")
        rig.emit("repel.bank", path=str(out), pos=list(rig.pos()))
        return 0
    except BattleWedge as e:
        log(f"BATTLE WEDGE: {e}")
        rig.emit("repel.wedge", err=str(e), pos=list(rig.pos()))
        rig.bank("repel_wedged", directory=BANK_DIR)
        return 8


if __name__ == "__main__":
    raise SystemExit(main())
