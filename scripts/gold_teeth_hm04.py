#!/usr/bin/env python3
"""GOLD TEETH -> the Warden -> HM04 STRENGTH (2026-09-03).

Two-step job, both pieces located in the cartridge itself:

  * GOLD TEETH (item id 64) is an item ball on map 219 at (19,7) — ``ball_contents``
    says so from the object data's item byte, and the baton (loop219.state) is in the
    same pocket 3, so the pickup is a walk, not a search.
  * The Warden is one of exactly two staff NPCs on map 156, the Safari Zone building
    (8x6, sprites (6,2) and (1,4)); its north wall doors (3,0)/(4,0) lead to 220.

Corridor, every pair from the extracted truth, each pocket-adjacency verified:

    219 pocket 3 (baton + GOLD TEETH at (19,7))
      (20,0)   -> 218 pocket 1          [door both in pocket 1's door set]
      218 (39,30) -> 217 (0,4)          [proven both ways, leg three]
      217 (0,22)  -> 220 (29,10)        [proven both ways, leg three; lands (17,20)]
      220 (14,25) -> 156 (3,0)          [the building; retried, screenshotted on refusal]

Map 220 is wall-sealed by static collision into rooms: the 156 door sits in the big
room (279 cells) entered from 217 or 221; the 219 west room and the 218 north room
are separate doors into separate rooms. So the only key to 156 is the 217/221 side,
and the leg-3 measured hops give us exactly that side.

Success condition, per the mission and per the cartridge: HM04 (item id 199) is in
the bag after the exchange — measured with ``bag_named``, not trusted from dialogue.

Usage:  uv run scripts/gold_teeth_hm04.py [baton.state]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

ROOT = SCRIPT_DIR.parent
BANK_DIR = ROOT / "data" / "local_runs" / "roster-bench"
DEFAULT_BATON = BANK_DIR / "loop219.state"
OUT = BANK_DIR / "gold_teeth.jsonl"
RIG: Rig | None = None

TEETH = "GOLD TEETH"
HM04 = "HM04"
WARDEN_RE = re.compile(r"STRENGTH|HM04|TEETH|WARDEN|THANK", re.IGNORECASE)

rows: list[dict] = []
heard: list[str] = []  # every sentence a 156 body has said, in order
warden: dict | None = None


def say(line: str) -> None:
    print(line, flush=True)


def cur() -> tuple[int, int, int]:
    assert RIG is not None
    return RIG.pos()


def save() -> None:
    OUT.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def in_battle() -> bool:
    assert RIG is not None
    return bool(RIG.mem[qm.ADDR_IN_BATTLE])


def read_conversation(max_pages: int = 12) -> list[str]:
    """One exchange, page by page, verbatim.

    A page is a buffer that stops changing (the typewriter is done). An A is the turn.
    The end is the world accepting movement again — the only honest signal, because the
    buffer stays *stale* after the box closes (measured), so "no new text" alone cannot
    mean "done".
    """
    assert RIG is not None
    pages: list[str] = []
    baseline = (RIG.dialogue() or "").strip()

    def wait_page() -> str:
        prev, stable, deadline = "", 0, 300
        while deadline:
            RIG.pb.tick()
            deadline -= 1
            if in_battle():
                return "battle"
            t = (RIG.dialogue() or "").strip()
            if t != baseline:
                if t == prev:
                    stable += 1
                else:
                    stable = 0
                    prev = t
                if stable >= 3:
                    return "page"
        return "timeout"

    RIG.ctl.press("a")
    RIG.ctl.wait(50)
    while max_pages > 0:
        max_pages -= 1
        if in_battle():
            RIG.battle()
            baseline = (RIG.dialogue() or "").strip()
            if RIG.probe_step():
                break
            continue
        status = wait_page()
        text = (RIG.dialogue() or "").strip()
        if RIG.probe_step():  # box closed; whatever is on screen is the last page
            if text != baseline and text not in pages:
                pages.append(text)
            break
        if status == "page" or (status == "timeout" and text != baseline):
            if pages and text.startswith(pages[-1]) and len(text) > len(pages[-1]):
                pages[-1] = text  # typewriter pause: the A completes the same line
            elif text not in pages:
                pages.append(text)
            baseline = text
            RIG.ctl.press("a")  # next page, or close on the last one
            RIG.ctl.wait(45)
        else:
            if not RIG.probe_step():
                RIG.ctl.press("a")
                RIG.ctl.wait(45)
                if RIG.probe_step():
                    break
    RIG.settle()
    return pages


def bag_state() -> list[tuple[str, int]]:
    assert RIG is not None
    return RIG.bag_named(full=True)


def check_hm04(rec: dict) -> None:
    """The exchange ran; the BAG is the verdict, not the dialogue."""
    global warden
    bag = bag_state()
    has = any(n.upper().startswith(HM04) for n, _q in bag)
    say(f"  bag after exchange: {bag}")
    if has:
        warden = rec
        bank = RIG.bank("strength_won", directory=BANK_DIR)
        RIG.emit("gold_teeth_done", warden=rec.get("body"), said=rec.get("heard"), bag=str(bag), bank=str(bank))
        say(f"** HM04 IS IN THE BAG ** banked {bank} at {cur()}")
        RIG.finish(outcome="gold_teeth: HM04 won", warden_body=rec.get("body"))
        sys.exit(0)


def engage_156(body: tuple[int, int]) -> dict:
    """Walk beside a 156 staff NPC, face them, read the whole exchange, then weigh the bag."""
    assert RIG is not None
    mp, x, y = cur()
    if mp != 156:
        # A settle probe may have stepped the feet back through the north door (156(4,0) -> 220).
        # The 217 hall door is measured this run to carry straight into the building, so
        # recovery is an engine drive back to 217, then the same door again.
        say(f"  not on 156 at {cur()}; recovering via the measured 217 door")
        RIG.drive(217)
        RIG.settled_pos()
        if cur()[0] != 217:
            rec = {"body": list(body), "reached": False, "note": f"recovery failed, on {cur()}"}
            rows.append(rec)
            save()
            return rec
        if not go_door(217, 0, 22, 156, "recovery: 217 hall door -> the building"):
            rec = {"body": list(body), "reached": False, "note": f"recovery door refused; on {cur()}"}
            rows.append(rec)
            save()
            return rec
        say(f"  back at {cur()}")
    mp, x, y = cur()
    if mp != 156:
        rec = {"body": list(body), "reached": False, "note": f"on {mp}, not 156"}
        say(f"  engage {body}: wrong map ({mp})")
        rows.append(rec)
        save()
        return rec

    m = RIG.truth["maps"]["156"]
    warps = {(w[0], w[1]) for w in m["warps"]}
    bodies = {(s["x"], s["y"]) for s in m.get("sprites", ())}
    bx, by = body
    cells: list[tuple[int, int]] = []
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        cx, cy = bx + dx, by + dy
        if (
            0 <= cx < m["width"]
            and 0 <= cy < m["height"]
            and m["grid"][cy][cx] == "1"
            and (cx, cy) not in warps
            and (cx, cy) not in bodies
        ):
            cells.append((cx, cy))
    tried: list = []
    for cell in cells:
        res = RIG.walk(156, {cell}, cap=240)
        here = cur()
        if here[0] != 156:
            say(f"     drift -> {here}")
            rec = {"body": list(body), "reached": False, "drift": list(here), "res": res}
            rows.append(rec)
            save()
            return rec
        if here[1:] != cell:
            tried.append([list(cell), f"stopped at {here[1:]}"])
            if in_battle():
                RIG.battle()
            continue
        face = "right" if bx > cell[0] else "left" if bx < cell[0] else "down" if by > cell[1] else "up"
        for _ in range(3):  # a parked box is stale: close it before talking
            RIG.ctl.press("b")
            RIG.ctl.wait(30)
        RIG.ctl.press(face)
        RIG.ctl.wait(25)
        pages = read_conversation()
        text = " | ".join(pages)
        rec = {"body": list(body), "reached": True, "cell": list(cell), "face": face, "pages": pages, "heard": text}
        if text:
            heard.append(text)
        say(f"     SAYS: {text}" if pages else "     (no page opened)")
        rows.append(rec)
        save()
        if in_battle():
            RIG.battle()
            RIG.settle()
        if WARDEN_RE.search(text):
            say(f"  ** MARKER on {body}: re-reading the exchange to its end **")
            # The handoff can continue while the box is still open; run it once more from
            # the same body so the exchange that grants STRENGTH finishes naturally.
            pages2 = read_conversation()
            text2 = " | ".join(p for p in pages2 if p not in pages)
            rec["followup"] = pages2
            if text2:
                heard.append(text2)
            say(f"     FOLLOWS: {text2}" if text2 else "     (nothing new)")
            rows.append(rec)
            save()
        check_hm04(rec)
        return rec
    rec = {"body": list(body), "reached": False, "tried": tried, "note": "no page, no adjacency reached"}
    rec["evidence"] = RIG.screenshot(f"evidence_156_{bx}_{by}")
    say(f"     {rec['note']} {rec['evidence']}")
    rows.append(rec)
    save()
    return rec


def go_door(fr: int, wx: int, wy: int, to: int, note: str = "") -> bool:
    assert RIG is not None
    rec = {"type": "door", "fr": fr, "door": [wx, wy], "to": to, "note": note, "at": list(cur())}
    say(f"  door {fr}({wx},{wy}) -> {to} [{note}] ...")
    if cur()[0] != fr:
        rec.update(ok=False, note=(note + f" (on {cur()[0]} not {fr})").strip(" ()"))
        rows.append(rec)
        save()
        return False
    res = RIG.warp(fr, wx, wy)
    RIG.settled_pos()
    here = cur()
    attempts = 1
    # Retrying while the feet are NOT on the source map is a no-op that reads as success
    # (measured this run: the 217 door fired from 156, res=True, and the loop burned three
    # false attempts). Once the world has moved us off the source map, the trip is over.
    while here[0] == fr and attempts < 4:
        attempts += 1
        res = RIG.warp(fr, wx, wy)
        RIG.settled_pos()
        here = cur()
        say(f"  retry {attempts}: {fr}({wx},{wy}) -> {to} res={res}; now on {here}")
    rec.update(ok=here[0] == to, res=res, landed=list(here), attempts=attempts)
    if not rec["ok"] and here[0] == fr:
        rec["evidence"] = RIG.screenshot(f"door_fail_{fr}_{wx}_{wy}_{attempts}")
        say(f"     refused after {attempts} tries: {rec['evidence']}")
    say(f"     -> {here} ok={rec['ok']}")
    rows.append(rec)
    save()
    return rec["ok"]


def main() -> None:
    global RIG
    baton = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BATON)
    say(f"BOOT baton={baton}")
    RIG = Rig(str(baton), settle_on_boot=True)
    say(f"BOOT pos={cur()} badges={RIG.badges()}")
    say(f"party: {RIG.party()}")
    bag = bag_state()
    say(f"bag({len(bag)}/20): {bag}")

    # Step 1: hold GOLD TEETH. Bag is 20/20 at this baton — free a slot first (mission order).
    if RIG.bag_full():
        say("bag full: Rig.make_room() before the pickup")
        if not RIG.make_room():
            say("!! make_room failed — a handoff may not land")
    teeth_ok = False
    before = bag_state()
    for _ in range(2):
        if TEETH in [n.upper() for n, _q in bag_state()]:
            teeth_ok = True
            break
        res = RIG.collect_item(19, 7)
        say(f"  collect 219(19,7): {res}")
        after = bag_state()
        got = [n for n, _q in after if n not in [x[0] for x in before]]
        say(f"  bag grew: {got or '(nothing new)'}")
        before = after
        in_bag = RIG.ball_contents(219)
        say(f"  truth: 219(19,7) = {in_bag.get((19, 7))}")
        RIG.settle()
        if cur()[0] != 219:
            say(f"  drifted to {cur()} on the pickup; returning via baton pocket")
            break
    teeth_ok = TEETH in [n.upper() for n, _q in bag_state()]
    say(f"  GOLD TEETH in bag: {teeth_ok}")
    if not teeth_ok:
        RIG.screenshot("teeth_misfire")
        bank = RIG.bank("teeth_unpicked", directory=BANK_DIR)
        say(f"!! teeth not in the bag after the pickup; banking {bank} at {cur()} and reporting")
        RIG.finish(outcome="gold_teeth: pickup did not land")
        sys.exit(1)
    bank = RIG.bank("teeth_in_bag", directory=BANK_DIR)
    say(f"teeth_in_bag banked {bank}")

    # Step 2: the corridor to the building on map 156. If the feet are already inside
    # (measured this morning: the 217 hall door carries straight through to (156,4,x)),
    # the corridor is done.
    if cur()[0] == 156:
        say(f"ALREADY at the building on 156 at {cur()} (carried through by the last door)")
    else:
        seq = [
            (219, 20, 0, 218, "219 pocket 3 -> field 218; 218(39,30) is in the same pocket"),
            (218, 39, 30, 217, "field 218 -> field 217 (0,4) [proven both ways, leg three]"),
            (217, 0, 22, 156, "217 hall door -> the SAFARI ZONE building [measured live this morning]"),
        ]
        for fr, wx, wy, to, note in seq:
            if cur()[0] != fr:
                # Drifted (a battle or a step may have moved the feet). Every door on this
                # corridor sits in one pocket, so route back with the engine.
                say(f"  on {cur()[0]} before door {fr}({wx},{wy}); driving back to {fr}")
                RIG.drive(fr)
                RIG.settled_pos()
                if cur()[0] != fr:
                    say(f"!! cannot get back to {fr}; at {cur()}")
            if not go_door(fr, wx, wy, to, note):
                say(f"!! corridor broken at {fr}({wx},{wy} -> {to}); reporting with the evidence above")
                RIG.screenshot(f"corridor_blocked_{fr}_{wx}_{wy}")
                bank = RIG.bank("corridor_blocked", directory=BANK_DIR)
                say(f"banked {bank} at {cur()}")
                RIG.finish(outcome="gold_teeth: corridor blocked", teeth=True)
                sys.exit(1)

    say(f"ARRIVED on 156 at {cur()} holding {TEETH}")
    RIG.screenshot("at_156")
    say("  156 staff (truth): (6,2) and (1,4) — talk to both")

    # Step 3: engage every staff body. Order: (1,4) is nearest the door from the hall;
    # (6,2) is by the counter. The Warden is one of the two; the bag decides.
    for body in ((1, 4), (6, 2)):
        if warden is not None:
            break
        engage_156(body)

    if warden is not None:
        return

    # Marker-less fallback: a body may have opened a menu (a handoff through the ITEM
    # submenu) instead of a page. Ask each body again and watch the bag either way.
    say("  no HM04 yet; second pass (the handoff may come through the bag menu)")
    for body in ((1, 4), (6, 2)):
        here = cur()
        if here[0] != 156:
            break
        engage_156(body)
        if warden is not None:
            return

    bank = RIG.bank("warden_no_hm04", directory=BANK_DIR)
    say(f"!! neither body handed over: banked {bank} at {cur()}")
    say(f"  heard on 156: {heard}")
    RIG.screenshot("final_156")
    RIG.finish(outcome="gold_teeth: 156 bodies engaged, no HM04", heard=heard)


if __name__ == "__main__":
    main()
