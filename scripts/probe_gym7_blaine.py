"""Cinnabar gym (166), doors open: talk to Blaine at (3,3) until the battle starts, fight it, read the badge byte."""

import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/gym7_room_8.state"
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
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


b0 = rig.badges()
print("start", rig.pos(), "badges", bin(b0), "party", rig.party(), flush=True)
drain()
stand = None
for cell, face in (((3, 4), "up"), ((4, 3), "left"), ((2, 3), "right")):
    rig.walk(166, {cell}, battle=rig.battle)
    if rig.pos()[1:] == cell:
        stand = (cell, face)
        break
print("stand", stand, rig.pos(), flush=True)
if stand:
    rig.io.press(stand[1], hold=4, release=8)
    rig.ctl.wait(20)
    pages = []
    for i in range(30):
        rig.ctl.press("a")
        rig.ctl.wait(60)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
        if rig.mem[qm.ADDR_IN_BATTLE]:
            print("battle started after", i + 1, "presses:", pages, flush=True)
            break
    if rig.mem[qm.ADDR_IN_BATTLE]:
        rig.battle()
        drain()
    after = []
    for _ in range(12):
        t = rig.textbox()
        if t and (not after or t != after[-1]):
            after.append(t)
        if not t:
            break
        rig.ctl.press("a")
        rig.ctl.wait(50)
    drain()
    print("after the battle:", after, "badges", bin(rig.badges()), "party", rig.party(), flush=True)
    journal(
        f"map=166 BLAINE at (3,3): {pages[-3:]} -> battle -> {after[:4]}; badges {b0:#010b} -> {rig.badges():#010b}"
    )
    rig.screenshot("blaine_after")
if rig.badges() != b0:
    rig.bank("badge7_won")
    print("*** BADGE 7 ***", bin(rig.badges()), rig.pos(), flush=True)
else:
    rig.bank("gym7_blaine_no_badge")
print("final", rig.pos(), "badges", bin(rig.badges()), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
