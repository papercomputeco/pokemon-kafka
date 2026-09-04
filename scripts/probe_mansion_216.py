"""Mansion B1F (216): press the switch at (18,25), retest the doors the survey found, and take the SECRET KEY at (5,13).

Survey (survey_216.json): 347 live cells; doors (26,17)/(27,17) from (26,18)/(27,18) UP and (13,22)/(13,23) from
(14,22)/(14,23) LEFT and (12,22)/(12,23) RIGHT. The key room (x 1-8, rows 9-16) is only reached through the top
corridor, which is behind (26,17)/(27,17). The switch (18,25) is inside the live region; (20,3) is not.
"""

import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/mansion_216.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
DOORS = [((26, 18), "up"), ((27, 18), "up"), ((14, 22), "left"), ((12, 22), "right")]


def journal(content):
    row = {
        "referenced_time": datetime.now(timezone.utc).isoformat(),
        "priority": "important",
        "content": content,
        "source_session": "extractor",
    }
    append_observations("pokedex/memory", [row], dedupe=True)


def drain(limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def test_door(stand, face):
    drain()
    for _ in range(4):
        rig.walk(216, {stand}, battle=rig.battle)
        if rig.pos()[1:] == stand:
            break
        rig.ctl.wait(60)
    if rig.pos()[1:] != stand:
        return None
    before = rig.pos()
    rig.io.press(face, hold=16, release=16)
    rig.ctl.wait(40)
    drain()
    moved = rig.pos() != before
    if moved:  # step back so the next test starts from a known cell
        rig.walk(216, {stand}, battle=rig.battle)
    return moved


def press_switch(stands):
    for stand, face in stands:
        drain()
        rig.walk(216, {stand}, battle=rig.battle)
        if rig.pos()[1:] != stand:
            continue
        rig.io.press(face, hold=4, release=8)
        rig.ctl.wait(20)
        drain()
        pages = []
        for _ in range(5):
            rig.ctl.press("a")
            rig.ctl.wait(50)
            t = rig.textbox()
            if t and (not pages or t != pages[-1]):
                pages.append(t)
        drain()
        if any("switch" in p.lower() for p in pages):
            return stand, pages
    return None


def take_key():
    if rig.bag_full():
        print("make_room:", rig.make_room(), flush=True)
    names = [n for n, _ in rig.bag_named(full=True)]
    w = rig.walk(216, {(5, 12), (4, 13), (6, 13), (5, 14)}, battle=rig.battle)
    print("walk beside the ball:", w, rig.pos(), flush=True)
    print("collect (5,13):", rig.collect_item(5, 13), flush=True)
    names2 = [n for n, _ in rig.bag_named(full=True)]
    new = [n for n in names2 if n not in names]
    print("new items:", new, flush=True)
    rig.screenshot("secret_key")
    if any("SECRET KEY" in n for n in names2):
        rig.bank("secret_key")
        print("*** SECRET KEY IN THE BAG ***", rig.pos(), flush=True)
        return True
    print("said:", repr(rig.textbox()), flush=True)
    return False


print("start", rig.pos(), flush=True)
before = {f"{s}{f}": test_door(s, f) for s, f in DOORS}
print("doors before the press:", before, flush=True)
r = press_switch((((18, 26), "up"), ((18, 24), "down"), ((17, 25), "right"), ((19, 25), "left")))
print("216 switch (18,25):", r, flush=True)
if r:
    rig.bank("mansion_216_pressed")
after = {f"{s}{f}": test_door(s, f) for s, f in DOORS}
print("doors after the press:", after, flush=True)
journal(
    f"map=216 mansion B1F: entered by dropping through map=215's tile 0x11 at (16,14) (stood on from (16,13) DOWN) "
    f"-> map=165 (16,14), inside the stairs pocket, then (21,22) DOWN -> 216 (23,22). Survey: 347 live cells; doors "
    f"(26,17)/(27,17) [from (26,18)/(27,18) UP] and (13,22)/(13,23) [from (14,22) LEFT / (12,22) RIGHT]. "
    f"Switch (18,25) pressed from {r[0] if r else None}: doors before {before} -> after {after}."
)
if after.get("(26, 18)up") or after.get("(27, 18)up"):
    print("top corridor open; going for the ball", flush=True)
    got = take_key()
    journal(f"map=216 SECRET KEY at (5,13): collected={got} after 216's (18,25) switch; pos {rig.pos()}")
else:
    print("top corridor still shut; catalog what is reachable now", flush=True)
    for stand, face in ((20, 4), "up"), ((21, 3), "left"), ((20, 2), "down"):
        w = rig.walk(216, {stand}, battle=rig.battle)
        print("  reach", stand, ":", w, rig.pos(), flush=True)
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
