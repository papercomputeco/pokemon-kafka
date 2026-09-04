#!/usr/bin/env python3
"""The Warden hunt — every body of the Safari Zone cluster's four rooms (2026-09-03).

Baton: ``loop219.state`` — map 219 (the main Safari Zone field), six badges, Gyarados
fainted (fine: these rooms hold only npcs, and a Safari wild is fleeable — its menu has
no FIGHT). The Seafoam legs measured boulders that say *"This requires STRENGTH"* and
nobody holds it; the cartridge's own HM04 text names its giver **the Warden** and puts
him in the Safari Zone.

The cluster graph below is measured from the extracted truth (warps + sprites), not
recalled:

    219 (field)
      (3,3)  -> 222   SECRET HOUSE      -- already engaged earlier; that one gave HM03
      (11,11)-> 223   room: npcs (4,4) (0,2) (6,2)   door back (2,7)/(3,7) -> 219(11,11)
      (29,22)-> 220   gate (no bodies to talk to; an item ball sits at (14,10))
        220 (14,0) -> 218  field 40x36
          218 (35,3)-> 225   room: npcs (6,3) (3,4) (1,5)  door back (2,7)/(3,7) -> 218(35,3)
        220 (17,19)-> 221  building: npcs (3,2) (1,4)   door back (2,7)/(3,7) -> 220(17,19)
        220 (29,10)-> 217 field 30x26
          217 (25,9)-> 224   room: npcs (1,3) (4,2) (5,2)  door back (2,7)/(3,7) -> 217(25,9)

Discipline:
  * every body is engaged BEFORE leaving its room — what it says is recorded verbatim,
    whole exchange, and read against the mission's markers (HM04 / STRENGTH / lost /
    thanking);
  * the moment a marker hits, the conversation is run to its actual end, the bag is
    measured for HM04, and the state is banked ``strength_won`` — no further walking,
    nothing else to lose;
  * a body the walk cannot reach ends with a screenshot, not a shrug.

Usage:  uv run scripts/probe_warden_safari.py [baton.state]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from expedition_rig import Rig  # noqa: E402

ROOT = SCRIPT_DIR.parent
BANK_DIR = ROOT / "data" / "local_runs" / "roster-bench"
DEFAULT_BATON = BANK_DIR / "loop219.state"
OUT = BANK_DIR / "warden_hunt.jsonl"
RIG: Rig | None = None

# The mission's markers. Anything else a body says is small talk.
WARDEN_RE = re.compile(r"STRENGTH|HM04|\bLOST\b|THANK", re.IGNORECASE)

# The corridor is the executed plan: enter a room, engage its bodies, come home, on to
# the next. Every pair is a door measured from the truth (a door's partner landing is the
# neighbour's own warp list, which is how these were verified to pair).
PLAN: list[tuple] = [
    ("door", 219, 11, 11, 223, "219(11,11) -> room 223"),
    ("engage_map", 223),
    ("door", 223, 2, 7, 219, "223 door -> home on 219(11,11)"),
    ("door", 219, 29, 22, 220, "219(29,22) -> gate 220(0,10)"),
    ("door", 220, 14, 0, 218, "gate 220(14,0) -> field 218(20,35)"),
    ("door", 218, 35, 3, 225, "218(35,3) -> room 225"),
    ("engage_map", 225),
    ("door", 225, 2, 7, 218, "225 door -> home on 218(35,3)"),
    ("door", 218, 20, 35, 220, "218(20,35) -> gate 220(14,0)"),
    ("door", 220, 17, 19, 221, "gate 220(17,19) -> building 221"),
    ("engage_map", 221),
    ("door", 221, 2, 7, 220, "221 door -> home on gate 220(17,19)"),
    ("door", 220, 29, 10, 217, "gate 220(29,10) -> field 217(0,22)"),
    ("door", 217, 25, 9, 224, "217(25,9) -> room 224"),
    ("engage_map", 224),
    ("door", 224, 2, 7, 217, "224 door -> home on 217(25,9)"),
    ("door", 217, 0, 22, 220, "217(0,22) -> home on gate 220(29,10)"),
]

rows: list[dict] = []
visited: dict[int, list[dict]] = {}
warden: dict | None = None


def say(line: str) -> None:
    print(line, flush=True)


def cur() -> tuple[int, int, int]:
    assert RIG is not None
    return RIG.pos()


def save() -> None:
    OUT.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


def end_conversation(cap_pages: int = 80) -> list[str]:
    """Run a dialogue to its actual end. A page is new text; the end is the world
    accepting movement again (probe_step True) with no further text arriving."""
    assert RIG is not None
    pages: list[str] = []
    idle = 0
    for _ in range(cap_pages * 2):
        RIG.pb.tick()
        t = (RIG.dialogue() or RIG.textbox() or "").strip()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
            idle = 0
            if RIG.probe_step():
                break  # last page: the world moves again, nothing more is said
            continue
        if RIG.probe_step():
            idle += 1
            if idle >= 2:
                break
        else:
            RIG.ctl.press("a")
            RIG.ctl.wait(35)
    RIG.settle()
    return pages


def clear_box() -> None:
    assert RIG is not None
    for _ in range(3):
        RIG.ctl.press("a")
        RIG.ctl.wait(35)
    for _ in range(3):
        RIG.ctl.press("b")
        RIG.ctl.wait(25)


def ensure_map(mp: int) -> bool:
    if cur()[0] == mp:
        return True
    say(f"    ensure_map: on {cur()[0]}, driving back to {mp} ...")
    for _ in range(2):
        if cur()[0] == mp:
            return True
        try:
            RIG.drive(mp)
        except Exception as e:  # a wedged driver is a finding, not a crash
            say(f"    drive failed: {e!r}")
        RIG.settled_pos()
    return cur()[0] == mp


def room_bodies(mp: int) -> list[tuple[int, int]]:
    assert RIG is not None
    return [
        (s["x"], s["y"])
        for s in RIG.truth["maps"].get(str(mp), {}).get("sprites", [])
        if s["kind"] in ("trainer", "npc")
    ]


def engage_body(mp: int, body: tuple[int, int], tag: str) -> dict:
    """Walk to a plain neighbour of ``body``, face it, and read the exchange."""
    assert RIG is not None
    bx, by = body
    rec: dict = {"map": mp, "body": [bx, by], "tag": tag}
    say(f"  engage {mp}({bx},{by}) {tag} ...")
    if cur()[0] != mp and not ensure_map(mp):
        rec.update(reached=False, note=f"wrong map: on {cur()[0]}")
        say(f"     UNREACHED -- on map {cur()[0]}")
        rows.append(rec)
        save()
        return rec

    m = RIG.truth["maps"][str(mp)]
    warps = {(w[0], w[1]) for w in m["warps"]}
    bodies = {(s["x"], s["y"]) for s in m.get("sprites", ())}
    cells: list[tuple[int, int]] = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        x, y = body[0] + dx, body[1] + dy
        if (
            0 <= x < m["width"]
            and 0 <= y < m["height"]
            and m["grid"][y][x] == "1"
            and (x, y) not in warps
            and (x, y) not in bodies
        ):
            cells.append((x, y))
    tried: list = []
    for cell in cells[:4]:
        RIG.walk(mp, {cell}, cap=240)
        here = cur()
        if here[0] != mp:
            say(f"     drift -> {here}")
            ensure_map(mp)
            rec.update(reached=False, drift=list(here))
            if cur()[0] == mp:
                rec["evidence"] = RIG.screenshot(f"evidence_{mp}_{bx}_{by}_drift")
            say(f"     DRIFT (screenshot: {rec.get('evidence')})")
            return rec
        if here[1:] != tuple(cell):
            tried.append([list(cell), f"stopped at {here[1:]}"])
            continue
        face = "right" if bx > cell[0] else "left" if bx < cell[0] else "down" if by > cell[1] else "up"
        clear_box()
        RIG.ctl.press(face)
        RIG.ctl.wait(25)
        RIG.ctl.press("a")
        pages: list[str] = []
        for _ in range(60):
            RIG.pb.tick()
            t = (RIG.dialogue() or RIG.textbox() or "").strip()
            if t and (not pages or t != pages[-1]):
                pages.append(t)
        text = " | ".join(pages)
        rec.update(reached=True, cell=list(cell), face=face, heard=text)
        if text and "EXP." not in text:
            say(f"     SAYS: {text}")
            # Marker check BEFORE any settle: a warden exchange must be run through its
            # own reader (which settles once at the end), and a settle's A/B presses
            # would walk the dialogue past pages we never heard.
            if WARDEN_RE.search(text):
                rows.append(rec)
                save()
                warden_found(rec, text)
            else:
                RIG.settle()
            return rec
        tried.append([list(cell), f"no-talk: {text!r}"])
        clear_box()
    else:
        rec.update(reached=False, tried=tried)
        if cur()[0] == mp:
            rec["evidence"] = RIG.screenshot(f"evidence_{mp}_{bx}_{by}")
        say(f"     UNREACHED (tried {len(tried)} adjacencies): {rec.get('evidence')}")
        return rec

    rows.append(rec)
    save()
    return rec


def warden_found(rec: dict, first_text: str) -> None:
    """The markers hit. Run the exchange to the end, take what is offered, verify, bank."""
    global warden
    assert RIG is not None
    say(f"  *** MARKER HIT on {rec['tag']}: {first_text[:140]} ***")
    rest = end_conversation()
    first_pages = [p.strip() for p in first_text.split(" | ")]
    rest = [p for p in rest if p not in first_pages]
    transcript = first_text + (" | " + " | ".join(rest) if rest else "")
    bag = RIG.bag_named(full=True)
    has = any(n.upper().startswith("HM04") for n, _q in bag)
    say(f"     full transcript: {transcript}")
    say(f"     bag after exchange: {bag}")
    warden = {
        "map": rec["map"],
        "body": rec["body"],
        "tag": rec["tag"],
        "transcript": transcript,
        "hm04_in_bag": has,
    }
    RIG.emit("warden_found", map=rec["map"], body=rec["body"], hm04_in_bag=has, transcript=transcript)
    if has:
        bank = RIG.bank("strength_won", directory=BANK_DIR)
        say(f"BANKED {bank} at {cur()} -- STRENGTH is ours")
        RIG.finish(outcome="warden_hunt: HM04 won", warden_map=rec["map"], warden_body=rec["body"])
        sys.exit(0)
    RIG.bank("warden_met_no_item", directory=BANK_DIR)
    say("the Warden spoke but the item did not land; the record stands")


def go_door(fr: int, wx: int, wy: int, to: int, note: str = "") -> bool:
    rec: dict = {"type": "door", "fr": fr, "door": [wx, wy], "to": to, "note": note, "at": list(cur())}
    say(f"  door {fr}({wx},{wy}) -> {to} [{note}] ...")
    if cur()[0] != fr and not ensure_map(fr):
        rec.update(ok=False, note=(note + f" (on {cur()[0]} not {fr})").strip(" ()"))
        rows.append(rec)
        save()
        return False
    r = RIG.warp(fr, wx, wy)
    RIG.settled_pos()
    here = cur()
    rec.update(ok=here[0] == to, landed=list(here), result=r)
    say(f"     -> {here} ok={rec['ok']}")
    rows.append(rec)
    save()
    return rec["ok"]


def main() -> None:
    global RIG
    baton = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BATON)
    RIG = Rig(str(baton), settle_on_boot=True)
    say(f"BOOT pos={cur()} badges={RIG.badges()}")
    say(f"party: {RIG.party()}")
    say(f"bag:   {RIG.bag_named(full=True)}")

    # The bag is full and the handoff needs a slot. make_room gives one back at the
    # cheapest measured price (the biggest stack: ten POKe BALLs). It happens BEFORE the
    # Warden speaks: a bag that is full at the offer moment is where items go to die.
    if RIG.bag_full():
        before = RIG.bag_named(full=True)
        if RIG.make_room():
            say(f"     room freed: {before} -> {RIG.bag_named(full=True)}")
        else:
            say("     !! make_room failed; a full bag may refuse the handoff")

    for step in PLAN:
        if warden is not None:
            break
        if step[0] == "door":
            go_door(step[1], step[2], step[3], step[4], step[5] if len(step) > 5 else "")
        else:
            mp = step[1]
            if mp in visited:
                continue
            bodies = room_bodies(mp)
            say(f"  ROOM {mp}: bodies {bodies}")
            recs = []
            for b in bodies:
                r = engage_body(mp, b, f"room{mp}")
                recs.append(r)
                if warden is not None:
                    break
            visited[mp] = recs

    RIG.emit("warden_hunt_done", rows=len(rows), visited={str(k): len(v) for k, v in visited.items()}, warden=warden)
    if warden is not None:
        say(f"WARDEN: {warden['transcript']}")
        return
    bank = RIG.bank("warden_hunt_end", directory=BANK_DIR)
    say(f"NO MARKER IN ANY ROOM. banked {bank} at {cur()}")
    RIG.finish(outcome="warden_hunt: no marker", rows=len(rows))


if __name__ == "__main__":
    main()
