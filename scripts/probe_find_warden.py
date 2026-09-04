#!/usr/bin/env python3
"""Find the WARDEN — the staff who takes the GOLD TEETH and grants HM04 (STRENGTH).

The 156 gate building (measured today, transcripts below) gave only first-visit
greetings while HOLDING the teeth — no teeth/STRENGTH/HM04 branch:

  156 (1,4): "Is it your first time here?" / "SAFARI ZONE has 4 zones in it."
  156 (6,2): "you can catch all the POKéMON you want in the park!" /
             "Would you like to join the hunt?"

So the Warden is measured to NOT be in 156. The remaining staff of the whole
safari cluster, every body from the cartridge's object data, untouched in this
project's history:

  221 (8x8): bodies (3,2) (1,4)          door (2,7)/(3,7) <-> 220
  223 (8x8): bodies (4,4) (0,2) (6,2)    door (2,7)/(3,7) <-> 219
  224 (8x8): bodies (1,3) (4,2) (5,2)    door (2,7)/(3,7) <-> 217
  225 (8x8): bodies (6,3) (3,4) (1,5)    door (2,7)/(3,7) <-> 218

All four buildings share one open hall: every body sits in the same pocket as
the doorway (truth pockets), so adjacent-cell talks are all reachable. The 220
hall ball is a NUGGET (object-data item byte) — skipped, because the one free
bag slot is held for the HM04 handoff.

Verdict rule (same as the gold-teeth run): the BAG decides. HM04 in
``bag_named`` = won; everything else is transcript.

Usage:  uv run scripts/find_warden.py [baton.state]
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
DEFAULT_BATON = BANK_DIR / "warden_no_hm04.state"
OUT = BANK_DIR / "find_warden.jsonl"
RIG: Rig | None = None

HM04 = "HM04"
GATE = 156
BUILDINGS = [221, 223, 224, 225]
# Cartridge text quoted by the mission; the handoff must read like this.
WARDEN_RE = re.compile(r"TEETH|STRENGTH|HM0?4|THANK|CAN'?T? UNDERSTAND", re.IGNORECASE)
# A body that ended on a question left a YES/NO we answered A-first; the B branch may hold the rest.
QUESTION_RE = re.compile(r"WOULD YOU LIKE|FIRST TIME\??$|DO YOU WANT", re.IGNORECASE)
# Live door chains, structural from the truth warp table (220 hall rooms measured this run).
MANUAL: dict[int, list[tuple[int, int, int, int]]] = {
    221: [(GATE, 3, 0, 220), (GATE, 4, 0, 220), (220, 17, 19, 221)],
    223: [
        (225, 2, 7, 220),
        (GATE, 3, 0, 220),
        (GATE, 4, 0, 220),
        (220, 29, 10, 217),
        (217, 0, 4, 218),
        (218, 20, 35, 219),
        (219, 11, 11, 223),
    ],
    224: [(GATE, 3, 0, 220), (GATE, 4, 0, 220), (220, 29, 10, 217), (217, 25, 9, 224)],
    225: [(GATE, 3, 0, 220), (GATE, 4, 0, 220), (220, 29, 11, 217), (217, 0, 4, 218), (218, 35, 3, 225)],
}

rows: list[dict] = []
heard: list[str] = []  # every sentence any body has said, in order


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


def read_conversation(max_pages: int = 12, turn: str = "a") -> list[str]:
    """One exchange, page by page, verbatim.

    A page is a buffer that stops changing (the typewriter is done). A turn-button press
    advances it — A by default, B when we want the second choice of a YES/NO box. The end
    is the world accepting movement again, because the buffer stays *stale* after the box
    closes (measured).
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

    RIG.ctl.press("a")  # open the box (the first button is always A)
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
                pages[-1] = text  # typewriter pause: the turn completes the same line
            elif text not in pages:
                pages.append(text)
            baseline = text
            RIG.ctl.press(turn)  # next page / the answer / close on the last one
            RIG.ctl.wait(45)
        else:
            if not RIG.probe_step():
                RIG.ctl.press(turn)
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
    assert RIG is not None
    bag = bag_state()
    has = any(n.upper().startswith(HM04) for n, _q in bag)
    if has:
        bank = RIG.bank("strength_won", directory=BANK_DIR)
        say(f"** HM04 IS IN THE BAG ** at {cur()} — banked {bank}")
        say(f"  the body: {rec.get('body')} on {rec.get('map')}; said: {rec.get('heard')}")
        RIG.finish(outcome="gold_teeth: HM04 won", warden_body=rec.get("body"), said=rec.get("heard"))
        sys.exit(0)


def bodies_of(mp: int) -> list[tuple[int, int]]:
    assert RIG is not None
    m = RIG.truth["maps"][str(mp)]
    return sorted((s["x"], s["y"]) for s in m.get("sprites", ()) if s.get("kind") == "npc")


def adj_cells(mp: int, body: tuple[int, int]) -> list[tuple[int, int]]:
    assert RIG is not None
    m = RIG.truth["maps"][str(mp)]
    warps = {(w[0], w[1]) for w in m.get("warps", ())}
    bodies = {(s["x"], s["y"]) for s in m.get("sprites", ())}
    cells = []
    for dx, dy in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        cx, cy = body[0] + dx, body[1] + dy
        if (
            0 <= cx < m["width"]
            and 0 <= cy < m["height"]
            and m["grid"][cy][cx] == "1"
            and (cx, cy) not in warps
            and (cx, cy) not in bodies
        ):
            cells.append((cx, cy))
    return cells


def face_toward(cell: tuple[int, int], body: tuple[int, int]) -> str:
    if body[1] > cell[1]:
        return "down"
    if body[1] < cell[1]:
        return "up"
    return "right" if body[0] > cell[0] else "left"


def engage(mp: int, body: tuple[int, int], turn: str = "a") -> dict:
    """Stand beside a body, face it, read the whole exchange with the given turn answer."""
    assert RIG is not None
    rec: dict = {"map": mp, "body": list(body), "turn": turn}
    if cur()[0] != mp:
        rec.update(reached=False, note=f"on {cur()[0]}, not {mp}")
        rows.append(rec)
        save()
        return rec
    cells = adj_cells(mp, body)
    tried: list = []
    for cell in cells:
        RIG.walk(mp, {cell}, cap=400)
        here = cur()
        if here[0] != mp:
            say(f"     drift -> {here}; driving back")
            RIG.drive(mp)
            RIG.settled_pos()
            if cur()[0] != mp:
                rec.update(reached=False, note=f"drift {here}, drive failed, now {cur()}")
                rows.append(rec)
                save()
                return rec
            continue
        if (here[1], here[2]) != cell:
            tried.append([list(cell), f"stopped at {(here[1], here[2])}"])
            if in_battle():
                RIG.battle()
            continue
        for _ in range(3):  # stale boxes: close before talking
            RIG.ctl.press("b")
            RIG.ctl.wait(30)
        RIG.ctl.press(face_toward(cell, body))
        RIG.ctl.wait(40)
        pages = read_conversation(turn=turn)
        text = " | ".join(pages)
        rec.update(reached=True, cell=list(cell), face=face_toward(cell, body), pages=pages, heard=text)
        if not pages:
            # No box opened: the body may have walked from its spawn cell (live sprites move).
            # Probe all four facings from the standing cell; a dialogue in front IS the talk.
            say("     no box; trying all four facings from the stand")
            for probe_face in ("up", "down", "left", "right"):
                for _ in range(2):
                    RIG.ctl.press("b")
                    RIG.ctl.wait(25)
                RIG.ctl.press(probe_face)
                RIG.ctl.wait(40)
                RIG.ctl.press("a")
                RIG.ctl.wait(40)
                probe_pages = read_conversation(max_pages=10, turn=turn)
                if probe_pages:
                    pages.extend(p for p in probe_pages if p not in pages)
                    text = " | ".join(pages)
                    rec.update(probe_face=probe_face, pages=pages, heard=text)
                    break
        if text:
            heard.append(text)
            RIG.say(text)
        marker = WARDEN_RE.search(text or "")
        say(f"     {'** MARKER ** ' if marker else ''}{'SAYS: ' + text if pages else '(no page opened)'}")
        check_hm04(rec)
        rows.append(rec)
        save()
        return rec
    rec.update(reached=False, tried=tried, note="no adjacent cell reached")
    rec["evidence"] = RIG.screenshot(f"evidence_{mp}_{body[0]}_{body[1]}")
    rows.append(rec)
    save()
    return rec


def enter(mp: int) -> bool:
    assert RIG is not None
    if cur()[0] == mp:
        return True
    here = cur()
    say(f"  on {here}; driving to {mp}")
    RIG.drive(mp)
    RIG.settled_pos()
    if cur()[0] == mp:
        return True
    say(f"  drive didn't land ({cur()}); live door chain from the truth")
    for fr, wx, wy, to in MANUAL.get(mp, []):
        if in_battle():
            RIG.battle()
        if cur()[0] != fr:
            continue
        say(f"  door {fr}({wx},{wy}) -> {to}")
        RIG.warp(fr, wx, wy)
        RIG.settled_pos()
        if cur()[0] == mp:
            return True
        if cur()[0] not in (fr, to):
            say(f"     crossed but to {cur()} — continuing")
    return False


def main() -> None:
    global RIG
    baton = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BATON)
    say(f"BOOT baton={baton}")
    RIG = Rig(str(baton), settle_on_boot=True)
    say(f"BOOT pos={cur()} badges={RIG.badges()}")
    say(f"party: {RIG.party()}")
    bag = bag_state()
    say(f"bag({len(bag)}/20): {bag}")
    teeth = any(n.upper() == "GOLD TEETH" for n, _q in bag)
    say(f"  GOLD TEETH in bag: {teeth}")
    if not teeth:
        say("!! the teeth are not in the bag — bank and report before the hunt")
        RIG.screenshot("teeth_missing_at_boot")
        bank = RIG.bank("teeth_missing", directory=BANK_DIR)
        RIG.finish(outcome="gold_teeth: teeth missing at boot", bag=str(bag))
        return
    if any(n.upper().startswith(HM04) for n, _q in bag):
        say("HM04 is ALREADY in the bag — nothing left to do")
        bank = RIG.bank("strength_won", directory=BANK_DIR)
        RIG.finish(outcome="gold_teeth: HM04 already in bag", bank=str(bank))
        return

    # The 220 hall ball, for the record — not picked (the free slot is for the handoff).
    say(f"  220 hall ball (truth): {RIG.ball_contents(220)} — skipping")

    for mp in BUILDINGS:
        if not enter(mp):
            say(f"!! could not reach {mp}; at {cur()} — moving on with the evidence")
            RIG.screenshot(f"cannot_reach_{mp}")
            rows.append({"map": mp, "entered": False, "at": list(cur())})
            save()
            continue
        RIG.settled_pos()
        bodies = bodies_of(mp)
        say(f"  on {mp} at {cur()}; staff: {bodies}")
        for body in bodies:
            rec = engage(mp, body)
            if WARDEN_RE.search(rec.get("heard") or ""):
                say(f"  ** {mp}{body} mentions the Warden's business — pressing the talk to its end **")
                rec2 = engage(mp, body)
                if WARDEN_RE.search(rec2.get("heard") or "") and not any(
                    n.upper().startswith(HM04) for n, _q in bag_state()
                ):
                    rec2 = engage(mp, body)  # one more read: the grant can sit behind the last page
                check_hm04(rec2 if rec2 else rec)

    # Second pass: the B branch, only for bodies that ended on a question (the A branch
    # already answered it). Data-directed, no blind sweeps.
    said_bodies = {(r["map"], tuple(r["body"])) for r in rows if r.get("reached")}
    askers = sorted(
        {
            (r["map"], tuple(r["body"]))
            for r in rows
            if r.get("reached") and QUESTION_RE.search((r.get("heard") or "").strip())
        }
    )
    if askers:
        say(f"  second pass (the B branch of a question), for: {askers}")
        for mp, body in askers:
            if enter(mp):
                rec = engage(mp, body, turn="b")
                check_hm04(rec)
    elif said_bodies:
        say("  second pass skipped: no body ended on a question")

    bank = RIG.bank("warden_unfound", directory=BANK_DIR)
    say(f"!! no Warden found in the safari cluster: banked {bank} at {cur()}")
    say("  heard, in order:")
    for t in heard:
        say(f"    - {t}")
    RIG.screenshot("final_hunt")
    RIG.finish(
        outcome="gold_teeth: teeth in bag, 156 gate + 11 safari staff engaged, no HM04",
        heard=heard,
        teeth=True,
    )


if __name__ == "__main__":
    main()
