"""The fossil doctor in Cinnabar lab room 170 says 'Oh! That is OLD AMBER!' and the bag does not change
(probe_lab_room, 2026-09-05). This talks to him one press at a time, printing every page and the menu registers,
answers a YES/NO with YES, and watches the bag and the party. Leaves and comes back for whatever he hands over.
Banks lab_amber_given (amber left the bag) and lab_revived (something came back)."""

import json
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
PAIRS = rt.loaded_pairs(TRUTH)
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/lab_pc_stored.state"
ROOM, DOOR, LAB_DOOR, CENTER = 170, (16, 4), (6, 9), 171
WALK = int(sys.argv[2]) if len(sys.argv) > 2 else 3
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def journal(c):
    append_observations(
        "pokedex/memory",
        [
            {
                "referenced_time": datetime.now(timezone.utc).isoformat(),
                "priority": "important",
                "source_session": "extractor",
                "content": c,
            }
        ],
        dedupe=True,
    )


def settle():
    for _ in range(3):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
        rig.ctl.press("b")
        rig.ctl.wait(20)


def bag():
    return [n for n, _ in rig.bag_named(full=True)]


def party():
    return [(n, lv) for n, lv, _h in rig.party()]


def navigate(mp, goals, cap=200):
    goals, blocked, stuck = set(goals), set(), 0
    for _ in range(cap):
        settle()
        m, x, y = rig.pos()
        if m != mp:
            return f"left:{rig.pos()}"
        if (x, y) in goals:
            return "reached"
        avoid = {tuple(b[:2]) for b in rig.bodies()} | blocked
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), goals, blocked=avoid - goals)
        if not path:
            return f"no path from {(x, y)} blocked={sorted(blocked)}"
        nx, ny = path[1] if len(path) > 1 else path[0]
        rig.io.press(K[(nx - x, ny - y)], hold=16, release=16)
        rig.ctl.wait(40)
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 2:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return f"cap at {rig.pos()}"


def door(mp, stand, key, want):
    print("  navigate", navigate(mp, {stand}), flush=True)
    for _ in range(4):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    return rig.pos()[0] == want


def leave_room(building=False):
    """Out of the room; with ``building`` also out of the lab onto Cinnabar and back in. Measured
    2026-09-05: four room re-entries after the hand-over all got "You go for walk a little while!"."""
    print("  leave:", navigate(ROOM, {(2, 6), (3, 6)}), flush=True)
    for _ in range(4):
        if rig.pos()[0] != ROOM:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    if building and rig.pos()[0] == 167:
        print("  out of the lab:", navigate(167, {(2, 7), (3, 7)}), flush=True)
        for _ in range(4):
            if rig.pos()[0] != 167:
                break
            rig.io.press("down", hold=16, release=16)
            rig.ctl.wait(90)
            settle()
        print("  outside at", rig.pos(), flush=True)
        if rig.pos()[0] == 8:
            for _ in range(WALK):  # a walk: south and back
                rig.io.press("down", hold=16, release=16)
                rig.ctl.wait(40)
            for _ in range(WALK):
                rig.io.press("up", hold=16, release=16)
                rig.ctl.wait(40)
            settle()
            print("  lab door:", door(8, (LAB_DOOR[0], LAB_DOOR[1] + 1), "up", 167), rig.pos(), flush=True)
    return rig.pos()[0] == 167


def doctor():
    """The body nearest (5,2) -- he wanders."""
    bs = sorted({tuple(b[:2]) for b in rig.bodies()}, key=lambda b: abs(b[0] - 5) + abs(b[1] - 2))
    return bs[0] if bs else None


def talk_doctor(presses=40):
    face = None
    for _attempt in range(8):  # he wanders while we walk: re-read him every attempt
        b = doctor()
        if b is None:
            break
        for stand, f in (
            ((b[0], b[1] + 1), "up"),
            ((b[0] - 1, b[1]), "right"),
            ((b[0] + 1, b[1]), "left"),
            ((b[0], b[1] - 1), "down"),
        ):
            if navigate(ROOM, {stand}, cap=40) == "reached" and doctor() == b:
                face = f
                break
        if face:
            break
    if not face:
        print("  doctor unreachable at", doctor(), "from", rig.pos(), flush=True)
        return [], [], [], party()
    b0, p0 = bag(), party()
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(16)
    pages = []
    for i in range(presses):
        rig.ctl.press("a")
        rig.ctl.wait(60)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
        cur, mx, tid = qm.menu_state(rig.io)
        rows = rig.menu_rows()
        if mx == 1 and tid != 0:
            print(f"    press {i}: YES/NO menu cur={cur} rows={rows} pages so far={pages}", flush=True)
            rig.screenshot("lab_doctor_prompt")
            # YES to everything except a nickname (measured 2026-09-05: YES there opens the naming
            # keyboard and blind A presses name the new member by whatever the cursor sits on)
            want = 1 if any("nickname" in r.lower() for _i, r in rows) else 0
            for _ in range(3):
                if rig.mem[qm.ADDR_MENU_CUR] == want:
                    break
                rig.ctl.press("down" if rig.mem[qm.ADDR_MENU_CUR] < want else "up")
                rig.ctl.wait(20)
            rig.ctl.press("a")
            rig.ctl.wait(60)
            pages.append("<YES>" if want == 0 else "<NO>")
            continue
        if bag() != b0 or party() != p0:
            print(f"    press {i}: bag/party changed; pages={pages}", flush=True)
    for _ in range(6):  # let the tail of the speech finish
        rig.ctl.press("a")
        rig.ctl.wait(60)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
    settle()
    gone = [n for n in b0 if n not in bag()]
    got = [n for n in bag() if n not in b0]
    print(f"  doctor {b}: pages={pages}", flush=True)
    print(f"  bag gone={gone} got={got}; party {p0} -> {party()}", flush=True)
    journal(f"map={ROOM} fossil doctor {b}: {pages}; bag lost {gone} gained {got}; party {p0} -> {party()}")
    return pages, gone, got, p0


print("start", rig.pos(), "bag", len(rig.bag()), bag(), flush=True)
if rig.pos()[0] == CENTER:
    print("  leave:", navigate(CENTER, {(3, 7), (4, 7)}), flush=True)
    for _ in range(4):
        if rig.pos()[0] != CENTER:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
if rig.pos()[0] == 8:
    print("lab door:", door(8, (LAB_DOOR[0], LAB_DOOR[1] + 1), "up", 167), rig.pos(), flush=True)
if rig.pos()[0] == 167:
    print("room door:", door(167, (DOOR[0], DOOR[1] + 1), "up", ROOM), rig.pos(), flush=True)
if rig.pos()[0] == ROOM:
    pages, gone, got, p0 = talk_doctor()
    if gone:
        rig.bank("lab_amber_given")
    for visit in range(6):
        if not gone and visit == 0 and STATE.endswith("lab_pc_stored.state"):
            break
        if not leave_room(building=visit > 0) or not door(167, (DOOR[0], DOOR[1] + 1), "up", ROOM):
            print("  could not come back", rig.pos(), flush=True)
            break
        pages, _g, got, _p = talk_doctor()
        print(f"  visit {visit + 2}: party {party()} bag {bag()}", flush=True)
        if got or party() != p0 or any("got " in p for p in pages):
            rig.bank("lab_revived")
            rig.screenshot("lab_revived")
            print("  REVIVED:", [p for p in pages if "got " in p or "room" in p.lower() or "BOX" in p], flush=True)
            journal(f"map={ROOM} the fossil doctor after one walk out of the lab: {pages}; party {party()}")
            break
print("final", rig.pos(), "party", party(), "bag", bag(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
