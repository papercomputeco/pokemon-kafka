#!/usr/bin/env python3
"""The Warden hunt — every body of the Safari Zone cluster's four rooms (2026-09-03).

Baton: ``warden_hunt_final.state`` — banked by the third leg in the gate's
EAST room at (220,17,20), one pocket from every door this corridor needs.
Bag 19/20: ten POKe BALLs already tossed. Six badges; Dugtrio 254/259.
``warden_hunt_end.state`` (156, the outside) and ``loop219.state`` (the
original baton, 219 pocket 3) remain as earlier positions.

What the earlier legs measured (this leg does not re-guess any of it):

  * The baton's original spot, 219(20,0), is 219 pocket 3. The doors to room
    223 and to the gate sit in pocket 1. Pockets are wall-separations inside
    one map; walking between them is `no-path` and is not a bug. Every hop of
    this corridor was verified pocket-adjacent from the extracted grid before
    it was written down.
  * The gate (220) is three rooms. West room ((0,10)-(3,11)): only door back
    to 219 pocket 1 — dead end. North room: door (14,0) to 218, door
    (14,25)/(15,25) to the outside — both sides of it have refused once
    already (`warp-dead` / `refused`) and work the other way; they are tried
    with retries, not assumed. East room: the building door (17,19) and the
    217 door (29,10); one pocket, proven walkable in both directions.
  * The old reader recorded typewriter partials — "I caught a CHANSE". This
    reader waits for the buffer to SETTLE, advances on A, and ends on the
    world accepting movement again. And because the typewriter pauses mid-line,
    a "page" that only extends the last one is merged, not duplicated.
  * 221(3,2) is SARA: "SARA: Where did my | my boy friend, ERIK, go?" — whole
    line, no marker. 224(4,2): "I caught a CHANSEY!" + 224(5,2): "tired from
    all the fun!" — no marker.
  * Bodies 221(1,4), 224(1,3) and (by sprite, 225(6,3), 223(4,4)) are sprite
    32 and opened NO page at all across every leg, from many adjacencies —
    leg three included B-clear + face + A at 221(1,4) that still opened
    nothing. They will be tried from all four sides each time; if they stay
    silent, the record says so. Whatever they are, they are not the Warden.

  * The 220 north-room door (14,0) refused every attempt in three legs, both
    directions; the walk inside the north room also refuses to move. It is
    treated as a locked-door of this ROM and the corridor avoids it and the
    outside (156) entirely.

Discipline:
  * every body engaged BEFORE leaving its room; its words recorded verbatim
    page by page and read against the mission's markers (HM04 / STRENGTH /
    lost / thanking);
  * a marker match runs the exchange to its actual end, then the BAG is
    measured: HM04 in it banks ``strength_won`` and ends the hunt — that is
    the mission's success condition. A match without the item is logged as a
    near miss and the hunt continues;
  * a body no walk can reach ends with a screenshot, not a shrug.

The corridor (every pair the truth's own warp list; the route the legs
actually walk — it avoids the north room and the outside entirely):

    220 east room (baton at (17,20))
      (29,10)  -> 217 (0,22)           [proven both ways]
      217 (0,4)  -> 218 (39,30)        [proven both ways]
      218 (9,35) -> 219 pocket 1 (27,0)  (untested; the only key to 223)
      219 (11,11) -> 223 room, door back (2,7)    (untested)
      219 (27,0) -> 218 (9,35)
      218 (35,3) -> 225 room, door back (2,7)     [worked once]
      218 (39,30) -> 217 (0,4)
      217 (25,9) -> 224 room, door back (2,7)     [proven both ways]
      217 (0,22) -> 220 east room (29,10)
      220 (17,19) -> 221 room, door back (2,7)    [proven both ways]

  219 pocket 1's other door, (29,22), goes to the gate's west room — the dead
  end measured above. Room 222 (SECRET HOUSE) was already engaged by an
  earlier leg and gave HM03; it is not on this corridor.

Usage:  uv run scripts/probe_warden_safari.py [baton.state]
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
DEFAULT_BATON = BANK_DIR / "warden_hunt_final.state"
OUT = BANK_DIR / "warden_hunt.jsonl"
RIG: Rig | None = None

# The mission's markers. Anything else a body says is small talk.
WARDEN_RE = re.compile(r"STRENGTH|HM04|\bLOST\b|THANK", re.IGNORECASE)

PLAN: list[tuple] = [
    ("door", 220, 29, 10, 217, "gate east room -> field 217 (0,22)"),
    ("door", 217, 0, 4, 218, "field 217 -> field 218 (39,30)"),
    ("door", 218, 9, 35, 219, "field 218 -> field 219 pocket 1 (27,0)"),
    ("door", 219, 11, 11, 223, "field 219 pocket 1 -> room 223"),
    ("engage_map", 223),
    ("door", 223, 2, 7, 219, "room 223 door -> field 219 (11,11)"),
    ("door", 219, 27, 0, 218, "field 219 pocket 1 -> field 218 (9,35)"),
    ("door", 218, 35, 3, 225, "field 218 -> room 225"),
    ("engage_map", 225),
    ("door", 225, 2, 7, 218, "room 225 door -> field 218 (35,3)"),
    ("door", 218, 39, 30, 217, "field 218 -> field 217 (0,4)"),
    ("door", 217, 25, 9, 224, "field 217 -> room 224"),
    ("engage_map", 224),
    ("door", 224, 2, 7, 217, "room 224 door -> field 217 (25,9)"),
    ("door", 217, 0, 22, 220, "field 217 -> gate east room (29,10)"),
    ("door", 220, 17, 19, 221, "gate east room -> building 221"),
    ("engage_map", 221),
    ("door", 221, 2, 7, 220, "building door -> gate (17,19)"),
]

rows: list[dict] = []
visited: dict[int, list[dict]] = {}
marker_hits: list[dict] = []
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

    A page is a buffer that stops changing (the typewriter is done). An A is
    the turn. The end is the world accepting movement again — the only honest
    signal, because the buffer stays *stale* after the box closes (measured),
    so "no new text" alone cannot mean "done".
    """
    assert RIG is not None
    pages: list[str] = []
    baseline = (RIG.dialogue() or "").strip()

    def wait_page() -> str:
        """Block frames until the buffer holds NEW text that has stopped growing."""
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
            # The typewriter pauses mid-line, so a "page" caught at the pause
            # ("That makes this all") is extended by the A that completes the
            # line. When the new text only extends the last, it IS the last.
            if pages and text.startswith(pages[-1]) and len(text) > len(pages[-1]):
                pages[-1] = text
            elif text not in pages:
                pages.append(text)
            baseline = text
            RIG.ctl.press("a")  # next page, or close on the last one
            RIG.ctl.wait(45)
        else:
            # Box still open, no new text: the end-of-page pause after a slow
            # line. This was the ghost the first leg read as "Got away safely!".
            if not RIG.probe_step():
                RIG.ctl.press("a")
                RIG.ctl.wait(45)
                if RIG.probe_step():
                    break
    RIG.settle()
    return pages


def engage_body(mp: int, body: tuple[int, int], tag: str) -> dict:
    """Walk to a plain neighbour of ``body``, face it, and read the exchange."""
    assert RIG is not None
    bx, by = body
    rec: dict = {"map": mp, "body": [bx, by], "tag": tag}
    say(f"  engage {mp}({bx},{by}) {tag} ...")
    if cur()[0] != mp:
        say(f"     wrong map: on {cur()[0]}")
        rec.update(reached=False, note=f"wrong map: on {cur()[0]}")
        rows.append(rec)
        save()
        return rec

    m = RIG.truth["maps"][str(mp)]
    warps = {(w[0], w[1]) for w in m["warps"]}
    bodies = {(s["x"], s["y"]) for s in m.get("sprites", ())}
    cells: list[tuple[int, int]] = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        x, y = bx + dx, by + dy
        if (
            0 <= x < m["width"]
            and 0 <= y < m["height"]
            and m["grid"][y][x] == "1"
            and (x, y) not in warps
            and (x, y) not in bodies
        ):
            cells.append((x, y))
    tried: list = []
    for cell in cells:
        RIG.walk(mp, {cell}, cap=240)
        here = cur()
        if here[0] != mp:
            say(f"     drift -> {here}")
            rec.update(reached=False, drift=list(here))
            rows.append(rec)
            save()
            return rec
        if here[1:] != cell:
            tried.append([list(cell), f"stopped at {here[1:]}"])
            if in_battle():
                RIG.battle()
            continue
        face = "right" if bx > cell[0] else "left" if bx < cell[0] else "down" if by > cell[1] else "up"
        for _ in range(3):  # whatever box is parked is stale: close it before talking
            RIG.ctl.press("b")
            RIG.ctl.wait(30)
        RIG.ctl.press(face)
        RIG.ctl.wait(25)
        pages = read_conversation()
        text = " | ".join(pages)
        rec.update(reached=True, cell=list(cell), face=face, pages=pages, heard=text)
        say(f"     SAYS: {text}" if pages else "     (no page opened)")
        rows.append(rec)
        save()
        if text and WARDEN_RE.search(text):
            warden_found(rec)
            return rec
        return rec
    rec.update(reached=False, tried=tried, note=f"no page from {len(tried)} adjacencies — silent, measured")
    if cur()[0] == mp:
        rec["evidence"] = RIG.screenshot(f"evidence_{mp}_{bx}_{by}")
    say(f"     {rec['note']} {rec.get('evidence', '')}")
    rows.append(rec)
    save()
    return rec


def warden_found(rec: dict) -> None:
    """A marker matched. The exchange is already run to its end; the BAG decides."""
    global warden
    assert RIG is not None
    matched = re.findall(r".*?(?:STRENGTH|HM04|\bLOST\b|THANK).*?", rec["heard"], re.IGNORECASE)
    bag = RIG.bag_named(full=True)
    has = any(n.upper().startswith("HM04") for n, _q in bag)
    say(f"  ** MARKER on {rec['tag']} {rec['body']}: {matched} **")
    say(f"     bag after exchange: {bag}")
    hit = {"map": rec["map"], "body": rec["body"], "transcript": rec["heard"], "hm04_in_bag": has}
    marker_hits.append(hit)
    RIG.emit("marker_hit", **hit)
    if has:
        warden = hit
        bank = RIG.bank("strength_won", directory=BANK_DIR)
        say(f"BANKED {bank} at {cur()} — HM04 is in the bag")
        RIG.finish(outcome="warden_hunt: HM04 won", warden_map=rec["map"], warden_body=rec["body"])
        sys.exit(0)
    say("     no HM04 in the bag — near miss, logged; the hunt continues")


def room_bodies(mp: int) -> list[tuple[int, int]]:
    assert RIG is not None
    sprites = RIG.truth["maps"].get(str(mp), {}).get("sprites", [])
    return [(s["x"], s["y"]) for s in sprites if s["kind"] in ("trainer", "npc")]


def go_door(fr: int, wx: int, wy: int, to: int, note: str = "") -> bool:
    assert RIG is not None
    rec: dict = {"type": "door", "fr": fr, "door": [wx, wy], "to": to, "note": note, "at": list(cur())}
    say(f"  door {fr}({wx},{wy}) -> {to} [{note}] ...")
    if cur()[0] != fr:
        rec.update(ok=False, note=(note + f" (on {cur()[0]} not {fr})").strip(" ()"))
        rows.append(rec)
        save()
        return False
    RIG.warp(fr, wx, wy)
    RIG.settled_pos()
    here = cur()
    attempts = 1
    while here[0] != to and attempts < 3:
        attempts += 1
        say(f"  retry {attempts} for {fr}({wx},{wy}) -> {to}; on {here}")
        if here[0] not in (fr, to):
            # Drifted elsewhere. The room itself is one door away from most
            # neighbours; the home field may need the very doors that refused.
            if in_battle():
                RIG.battle()
            RIG.drive(to)
            RIG.settled_pos()
            here = cur()
            if here[0] not in (fr, to):
                RIG.drive(fr)
                RIG.settled_pos()
                here = cur()
        if here[0] in (fr, to):
            RIG.warp(fr, wx, wy)
            RIG.settled_pos()
            here = cur()
    rec.update(ok=here[0] == to, landed=list(here), attempts=attempts)
    say(f"     -> {here} ok={rec['ok']}")
    rows.append(rec)
    save()
    return rec["ok"]


def main() -> None:
    global RIG
    baton = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BATON)
    say(f"BOOT baton={baton.name}")
    RIG = Rig(str(baton), settle_on_boot=True)
    say(f"BOOT pos={cur()} badges={RIG.badges()}")
    say(f"party: {RIG.party()}")
    bag = RIG.bag_named(full=True)
    say(f"bag({len(bag)}/20): {bag}")
    if RIG.bag_full():
        say("     !! bag full — a gift may silently refuse; freeing a slot")
        if not RIG.make_room():
            say("     !! make_room failed: the handoff may not land")

    for step in PLAN:
        if warden is not None:
            break
        if step[0] == "door":
            go_door(step[1], step[2], step[3], step[4], step[5] if len(step) > 5 else "")
        else:
            mp = step[1]
            if warden is not None or mp in visited:
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

    RIG.emit(
        "warden_hunt_done",
        rows=len(rows),
        visited={str(k): len(v) for k, v in visited.items()},
        marker_hits=marker_hits,
        warden=warden,
    )
    if warden is not None:
        say(f"WARDEN {warden['map']}{warden['body']}: {warden['transcript']}")
        return
    for h in marker_hits:
        say(f"NEAR MISS {h['map']}{h['body']}: {h['transcript']}")
    if not marker_hits:
        say("NO MARKER IN ANY ROOM")
    bank = RIG.bank("warden_hunt_final", directory=BANK_DIR)
    say(f"banked {bank} at {cur()}")
    RIG.finish(outcome="warden_hunt: complete", rows=len(rows), marker_hits=len(marker_hits))


if __name__ == "__main__":
    main()
