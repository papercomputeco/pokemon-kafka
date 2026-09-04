"""Cinnabar gym (166): answer each room's quiz machine (tile 0x4c), fight the trainer when wrong, step through the door,
and engage the body in the last room. Machines: (1,13) from (1,14); (1,7) from (1,8). Doors: (4,12)/(5,12), (4,6)/(5,6).
"""

import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/badge7.state"
ANSWER = sys.argv[2] if len(sys.argv) > 2 else "yes"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def journal(content):
    row = {
        "referenced_time": datetime.now(timezone.utc).isoformat(),
        "priority": "important",
        "content": content,
        "source_session": "extractor",
    }
    append_observations("pokedex/memory", [row], dedupe=True)


def drain(limit=12):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            print("  battle ->", flush=True)
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def quiz(stand, face, answer):
    drain()
    rig.walk(166, {stand}, battle=rig.battle)
    if rig.pos()[1:] != stand:
        return None
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(20)
    drain()
    pages, menu = [], None
    for i in range(16):
        rig.ctl.press("a")
        rig.ctl.wait(60)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
        cur, mx, tid = qm.menu_state(rig.io)
        if mx == 1 and tid != 0:  # a two-entry menu: YES/NO
            menu = (cur, mx, tid)
            break
        if rig.mem[qm.ADDR_IN_BATTLE]:
            break
    print(f"  quiz at {stand}: pages={pages} menu={menu}", flush=True)
    rig.screenshot(f"gym7_quiz_{stand[0]}_{stand[1]}")
    if menu:
        want = 0 if answer == "yes" else 1
        for _ in range(3):
            cur = rig.mem[qm.ADDR_MENU_CUR]
            if cur == want:
                break
            rig.ctl.press("down" if cur < want else "up")
            rig.ctl.wait(20)
        rig.ctl.press("a")
        rig.ctl.wait(60)
        after = []
        for _ in range(8):
            t = rig.textbox()
            if t and (not after or t != after[-1]):
                after.append(t)
            if rig.mem[qm.ADDR_IN_BATTLE] or not t:
                break
            rig.ctl.press("a")
            rig.ctl.wait(50)
        print(f"  answered {answer}: {after} battle={rig.mem[qm.ADDR_IN_BATTLE]}", flush=True)
        drain()
        return pages, after
    drain()
    return pages, []


def door(stands):
    for stand, face in stands:
        drain()
        rig.walk(166, {stand}, battle=rig.battle)
        if rig.pos()[1:] != stand:
            continue
        before = rig.pos()
        rig.io.press(face, hold=16, release=16)
        rig.ctl.wait(40)
        drain()
        if rig.pos() != before:
            return True
    return False


def engage(body):
    bx, by = body
    for stand, face in (((bx, by + 1), "up"), ((bx + 1, by), "left"), ((bx - 1, by), "right"), ((bx, by - 1), "down")):
        drain()
        rig.walk(166, {stand}, battle=rig.battle)
        if rig.pos()[1:] == stand:
            said = rig.talk(face)
            drain()
            return said
    return None


print("start", rig.pos(), "badges", bin(rig.badges()), flush=True)
b0 = rig.badges()
ROOMS = [
    ((1, 14), "up", [((4, 13), "up"), ((5, 13), "up")], (3, 14)),
    ((1, 8), "up", [((4, 7), "up"), ((5, 7), "up")], (3, 8)),
]
for stand, face, doors, body in ROOMS:
    q = quiz(stand, face, ANSWER)
    opened = door(doors)
    print(f"door after the quiz: {opened} at {rig.pos()}", flush=True)
    if not opened:
        said = engage(body)
        print(f"  engaged {body}: {said!r}", flush=True)
        opened = door(doors)
        print(f"door after the trainer: {opened} at {rig.pos()}", flush=True)
    journal(f"map=166 gym quiz at {stand} ({ANSWER}): {q}; door {doors[0][0]} opened={opened}; body {body}")
    if not opened:
        break
    rig.bank(f"gym7_room_{stand[1]}")
if rig.pos()[1:][1] <= 6:
    for body in ((3, 3),):
        said = engage(body)
        print(f"engaged {body}: {said!r} badges {bin(rig.badges())}", flush=True)
        journal(f"map=166 body {body} said {said!r}; badges {b0:#010b} -> {rig.badges():#010b}")
if rig.badges() != b0:
    rig.bank("badge7_won")
    print("*** BADGE 7 ***", bin(rig.badges()), flush=True)
print("final", rig.pos(), "badges", bin(rig.badges()), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
