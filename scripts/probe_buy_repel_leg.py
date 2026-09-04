#!/usr/bin/env python3
"""Fuchsia's mart (152), v3 — buy 99 REPEL (or MAX REPEL) into one empty slot.

What v1 and v2 cost us, measured, so this version stops guessing:

* The room's BACKGROUND permanently decodes as 'MONEY / BUY 87400 / SELL / QUIT / Thank you!' —
  it moves with the player (probe moved (2,5)->(2,7), rows unchanged). Row text is
  decoration; the MENU REGISTERS (0xCC26 cur / 0xCC28 max / 0xD125 id) + money + bag are truth.
* Flow, measured by walking it: face clerk + A -> greeting (id 1) -> clerk question (id 1) ->
  shop menu (id 14, max=2, entries BUY/SELL/QUIT, cursor 0 = BUY) -> A -> BUY list (id 13,
  stock rows with prices) -> cursor down (measured per press) -> A -> 'How many?' band ->
  A -> '<item>? That's <n>.' box -> A -> MONEY DROPS (the purchase) -> back at the list.
  B backs one level at a time (band -> list -> menu -> 'Thank you!').
* A 'Thank you!' box parks on boot (register id 1); it swallows A (v2's settle loop fed its A's
  into it and the START menu stayed up). Settles by facing the body away and A'ing (the
  measured settle doctrine, expedition_rig.settle docstring).
* v1's A-spam bought 3x ULTRA BALL and parked in the SELL flow — caught by the bag delta.
  Therefore: every purchase round is gated on money drop AND the bag delta naming the target;
  quantity stays 1 per round (the band's quantity keys are unproven; 98 one-unit rounds at
  40 frames apiece is nothing headless, and every round proves itself).

Usage:  uv run python scripts/buy_repel_leg.py [state-file]   (default b8_mart_counter_map.state)
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
DEFAULT_STATE = BANK_DIR / "b8_mart_counter_map.state"
STACK_CAP = 99
RESERVE_MONEY = 100
# Preference is policy; the stock itself is read off its live window rows (list id 13 only).
CANDIDATES = ("MAX REPEL", "REPEL")

ID_TEXTBOX, ID_SHOP_MENU, ID_ITEM_LIST = 1, 14, 13


def log(*a):
    print(*a, flush=True)


def regs(rig: Rig) -> tuple[int, int, int]:
    return qm.menu_state(rig.io)


def money(rig: Rig) -> int:
    return qm.read_money(rig.io)


def bag_map(rig: Rig) -> dict[int, int]:
    return dict(rig.bag())


def repel_stack(rig: Rig) -> int:
    return sum(q for n, q in rig.bag_named(full=True) if "REPEL" in n.upper() and "S.S." not in n.upper())


def window(rig: Rig) -> list[tuple[int, str]]:
    """Non-empty rows. On the background-only screens these are the room's decorative
    'MONEY BUY 87400 SELL QUIT Thank you!' — so callers pair this WITH the registers."""
    return rig.menu_rows()


def show(rig: Rig, label: str) -> None:
    log(f"-- {label} :: regs={regs(rig)} money={money(rig)} bag_n={len(bag_map(rig))} :: {window(rig)[:8]}")
    rw = [(i, s) for i, s in window(rig)[:10]]
    rig.emit("repel.screen", label=label, regs=list(regs(rig)), money=money(rig), rows=rw)


def key(rig: Rig, k: str, wait: int = 40) -> None:
    rig.ctl.press(k)
    rig.ctl.wait(wait)


def close_parked_box(rig: Rig) -> bool:
    """A parked box (reg id 1) swallows A aimed at menus. Face away from the body, then A —
    the settle doctrine: A facing an NPC re-opens the conversation, so turn away first."""
    for _ in range(4):
        if regs(rig)[2] == 0:
            return True
        rig.ctl.press("down" if rig.pos()[2] == 5 else "right")  # step off the clerk's row if on it
        rig.ctl.wait(40)
        # re-face the body's row from a safe tile is not needed; the point is the A not facing
        key(rig, "a", 50)
    return regs(rig)[2] == 0


def bank_stop(rig: Rig, why: str) -> None:
    show(rig, why)
    rig.shot(BANK_DIR / f"repel_{why}.png")
    rig.emit("repel.stop", why=why, pos=list(rig.pos()), money=money(rig), bag=str(rig.bag_named(full=True)))
    rig.bank(f"repel_{why}", directory=BANK_DIR)
    log(f"== stopped: {why} — banked; money {money(rig)}")


def main() -> int:
    started = sys.argv[1] if len(sys.argv) > 1 else str(DEFAULT_STATE)
    rig = Rig(started)
    log(
        f"== v3 from {rig.pos()} regs={regs(rig)} money={money(rig)} "
        f"bag={len(bag_map(rig))}/20 repel_stack={repel_stack(rig)}"
    )
    rig.emit("repel.open", from_state=str(started), pos=list(rig.pos()), money=money(rig))

    try:
        # ---- 0. a parked 'Thank you!' box (reg id 1) is bootable: the probe walked under it and
        # banked from it. A/B on it are no-ops (measured) — so no settle theatre up front; the
        # engage below just A's past whatever the clerk has to say, register-gated.
        show(rig, "boot_state")

        # ---- 1. room: the baton arrived 20/20 with the v1 ULTRA stack on the line --------
        if rig.bag_full() and repel_stack(rig) == 0:
            log("-- bag full, no repel yet: make_room (loss is the measured toss line)")
            free = rig.make_room()
            log(f"   make_room={free} bag={len(bag_map(rig))}/20 regs={regs(rig)}")
            rig.emit("repel.room", free=free, bag=str(rig.bag_named(full=True)), regs=list(regs(rig)))
            # make_room's settle can wedge a START menu (v2's crash): a menu register is a hard
            # stop; everything else (map, ghost box id 1) is bootable — the probe booted one.
            if regs(rig)[2] in (ID_SHOP_MENU, ID_ITEM_LIST):
                for _ in range(6):
                    if regs(rig)[2] == 0:
                        break
                    key(rig, "b", 50)
                if regs(rig)[2] in (ID_SHOP_MENU, ID_ITEM_LIST):
                    bank_stop(rig, "menu_wedged")
                    return 9
            if rig.bag_full():
                bank_stop(rig, "room_still_full")
                return 9
            show(rig, "after_make_room")

        # ---- 2. engage the clerk: v1's measured path — walk up to him, A, registers decide -
        # (1,5) stands directly in front of the clerk at (0,5); the last step faces him.
        target = (1, 5)
        if rig.pos()[1:] != target:
            ok = rig.walk(152, {target}, cap=200)
            log(f"-- walk {target}: {ok} at {rig.pos()} regs={regs(rig)}")
            rig.emit("repel.walk", ok=ok, pos=list(rig.pos()), regs=list(regs(rig)))
            if rig.pos()[1:] != target:
                bank_stop(rig, "counter_unreachable")
                return 9
        show(rig, "at_clerk")

        # ---- 3. the conversation, register-gated: A until id 14 (menu). 13 is an early slip,
        # one measured B takes it back to the menu path. The ghost 'Thank you!' (id 1) just
        # soaks A presses; the cap makes that cost bounded and logged.
        steps = 0
        while regs(rig)[2] != ID_SHOP_MENU and steps < 12:
            steps += 1
            key(rig, "a", 80)
            show(rig, f"greet_{steps}")
            if regs(rig)[2] == ID_ITEM_LIST:
                key(rig, "b", 60)
        if regs(rig)[2] != ID_SHOP_MENU:
            bank_stop(rig, "shop_menu_not_open")
            return 10
        log(
            f"   shop menu reached after {steps} A (cur={regs(rig)[0]} max={regs(rig)[1]}) "
            "— cursor 0 = BUY (measured in v1's buy)"
        )
        show(rig, "shop_menu")

        # ---- 4. BUY list: id 13; the stock rows are REAL here (background has no REPEL) ---
        m0 = money(rig)
        key(rig, "a", 90)
        show(rig, "buy_list_open")
        if regs(rig)[2] != ID_ITEM_LIST or money(rig) != m0:
            bank_stop(rig, "buy_list_refused")
            return 10
        name: str | None = None
        for p in range(24):
            rows = window(rig)
            for cand in CANDIDATES:
                hit = next(((i, s) for i, s in rows if cand in s.upper()), None)
                if hit is None:
                    continue
                # exclude 'SUPER REPEL' when hunting plain REPEL, and vice versa, by full name
                if cand == "REPEL" and "SUPER" in hit[1].upper():
                    continue
                name = cand
                hitrow = hit[0]
                break
            else:
                prev = "|".join(t for _i, t in window(rig))
                key(rig, "down", 50)
                if "|".join(t for _i, t in window(rig)) == prev:
                    log("   list bottom reached, row set did not move")
                    break
                continue
            break
        if name is None:
            show(rig, "stock_page_final")
            rig.emit("repel.not_stocked", window=[t for _i, t in window(rig)])
            bank_stop(rig, "not_stocked")
            return 11

        # ---- 5. walk the list cursor to the REPEL row by measured downs (cursor = window top)
        top = next(((i, s) for i, s in window(rig) if s.strip()), None)
        moves = 0
        while top is not None and top[0] != hitrow and moves < 20:
            key(rig, "down", 45)
            moves += 1
            top = next(((i, s) for i, s in window(rig) if s.strip()), None)
            if name not in " ".join(t for _i, t in window(rig)).upper():
                log("   the REPEL row scrolled away — overshoot; back up")
                key(rig, "up", 45)
                top = next(((i, s) for i, s in window(rig) if s.strip()), None)
        show(rig, "cursor_at_repel")
        if top is None or top[0] != hitrow:
            bank_stop(rig, "cursor_not_on_repel")
            return 11
        iid = None
        for k, v in (rig.truth.get("items") or {}).items():
            if v == name:
                iid = int(k)
        if iid is None:
            bank_stop(rig, "no_item_id_for_name")
            return 11
        log(f"   buying {name} (cart item id {iid}) — cursor is on its row after a measured {moves} downs")

        # ---- 6. the buy loop: 1 unit per round, gated on money drop + bag delta naming it -
        total = 0
        price = 0
        rounds = 0
        while total < STACK_CAP and rounds < 130:
            rounds += 1
            # wherever the last round left us, get back AT the list by register (id 13), B only
            for _ in range(5):
                if regs(rig)[2] == ID_ITEM_LIST:
                    break
                key(rig, "b", 60)
            if regs(rig)[2] != ID_ITEM_LIST:
                show(rig, f"round{rounds}_lost_the_list")
                break
            m0 = money(rig)
            b0 = bag_map(rig)
            key(rig, "a", 80)  # list -> band
            # band -> '<item>? That's 1.' box (quantity is 1: we never touch the band's quantity keys)
            key(rig, "a", 80)
            for confirm in range(3):
                if money(rig) < m0:
                    break
                key(rig, "a", 80)  # the box's yes
                show(rig, f"round{rounds}_confirm{confirm}")
            now = bag_map(rig)
            dm = m0 - money(rig)
            if dm <= 0:
                show(rig, f"round{rounds}_refused")
                rig.emit("repel.refused", round=rounds, window=[t for _i, t in window(rig)])
                break
            gained = now.get(iid, 0) - b0.get(iid, 0)
            other = {k: v - b0.get(k, 0) for k, v in now.items() if k != iid and v > b0.get(k, 0)}
            if gained <= 0 or other:
                log(
                    f"   !! round {rounds}: money -{dm} but bag delta says {iid}: {gained}, "
                    f"other gains {other} — NOT {name}"
                )
                rig.emit("repel.gate", round=rounds, gain=iid and gained, other=other, dm=dm)
                rig.shot(BANK_DIR / f"repel_bad_round{rounds}.png")
                break
            price = dm // max(1, gained)
            total += gained
            log(
                f"   round {rounds}: +{gained} (stack {total}) price/delta {dm} per {gained} "
                f"=> unit ~{price} money {money(rig)}"
            )
            rig.emit("repel.round", n=rounds, name=name, gained=gained, total=total, dm=dm, money=money(rig))
            if money(rig) <= RESERVE_MONEY + price:
                log("   money floor — the game can no longer take a full unit safely")
                break
        show(rig, "buy_loop_end")
        final = repel_stack(rig)
        log(f"== {name}: stack in bag {final} (loop total {total}), money {money(rig)}, bag {len(bag_map(rig))}/20")
        bagtxt = str(rig.bag_named(full=True))
        rig.emit("repel.done", name=name, rounds=rounds, stack=final, money=money(rig), bag=bagtxt)

        # ---- 7. leave the clerk's screens by measured B's (band -> list -> menu -> goodbye);
        # the goodbye box (id 1) may park — that banked fine as a baton (the probe booted one)
        for n in range(6):
            key(rig, "b", 70)
            show(rig, f"leaving_{n}")
            if regs(rig)[2] == 0 and not any("THANK" in t.upper() for _i, t in window(rig)):
                break
        show(rig, "at_the_map")
        shot = rig.shot(BANK_DIR / "repel_final.png")
        rig.emit("repel.final", pos=list(rig.pos()), shot=str(shot), regs=list(regs(rig)))
        if final == 0 or total == 0:
            bank_stop(rig, "no_repel_landed")
            return 12
        out = rig.bank("b8_REPEL_bought", directory=BANK_DIR)
        log(f"== banked {out.name}; {name} stack = {final}; party={rig.party()}")
        rig.emit("repel.bank", path=str(out), pos=list(rig.pos()), stack=final)
        return 0
    except BattleWedge as e:
        log(f"BATTLE WEDGE: {e}")
        rig.emit("repel.wedge", err=str(e), pos=list(rig.pos()))
        rig.bank("repel_wedged", directory=BANK_DIR)
        return 13


if __name__ == "__main__":
    raise SystemExit(main())
