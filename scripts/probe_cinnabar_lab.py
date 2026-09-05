"""With the OLD AMBER: FLY to Cinnabar, into the lab (167) and each back room (168, 169, 170), talk to every body,
watch the bag (the amber leaving) and the party/box for what comes back; if a body asks for a return, leave the
room and come back and talk again. What they say is the record. Banks lab_amber_given, lab_revived."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/pewter_amber.state"
ROOMS = {168: (8, 4), 169: (12, 4), 170: (16, 4)}
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


def bodies():
    return {tuple(b[:2]) for b in rig.bodies()}


def bag():
    return [n for n, _ in rig.bag_named(full=True)]


def navigate(mp, goals, cap=200):
    goals, blocked, stuck = set(goals), set(), 0
    for _ in range(cap):
        settle()
        m, x, y = rig.pos()
        if m != mp:
            return "left-map"
        if (x, y) in goals:
            return "reached"
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), goals, blocked=(bodies() - goals) | blocked)
        if not path or len(path) < 2:
            return "no-path"
        nx, ny = path[1]
        dx, dy = nx - x, ny - y
        rig.io.press(K[(dx // abs(dx) if dx else 0, dy // abs(dy) if dy else 0)], hold=12, release=8)
        rig.ctl.wait(40 if abs(dx) + abs(dy) == 2 else 24)
        if rig.pos()[0] != mp:
            return "left-map"
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return "cap"


def door(mp, stand, key, want):
    navigate(mp, {stand})
    for _ in range(4):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    return rig.pos()[0] == want


def talk(face, n=30):
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(16)
    pages = []
    for _ in range(n):
        rig.ctl.press("a")
        rig.ctl.wait(55)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
    settle()
    return pages


def talk_all(mp):
    out = {}
    for b in sorted(bodies()):
        for stand, face in (
            ((b[0], b[1] + 1), "up"),
            ((b[0] - 1, b[1]), "right"),
            ((b[0] + 1, b[1]), "left"),
            ((b[0], b[1] - 1), "down"),
        ):
            if navigate(mp, {stand}) == "reached":
                b0 = bag()
                out[b] = talk(face)
                gone = [n for n in b0 if n not in bag()]
                got = [n for n in bag() if n not in b0]
                print(f"  {mp} body {b}: {out[b][:6]} | amber gone={gone} got={got}", flush=True)
                if gone or got:
                    rig.bank("lab_amber_given")
                    journal(f"map={mp} lab body {b}: {out[b][:8]}; bag lost {gone} gained {got}")
                break
        else:
            print(f"  {mp} body {b}: unreachable", flush=True)
    return out


print("start", rig.pos(), "bag has OLD AMBER:", "OLD AMBER" in bag(), flush=True)
settle()
if rig.pos()[0] == 52:  # out of the museum by the back mats
    navigate(52, {(16, 6), (17, 6)})
    for _ in range(4):
        if rig.pos()[0] != 52:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
print("outside:", rig.pos(), flush=True)
if rig.pos()[0] == 2:
    print("fly:", rig.fly_to("CINNABAR ISLAND"), rig.pos(), flush=True)
    settle()
if rig.pos()[0] == 8:
    print("lab door (6,9):", door(8, (6, 10), "up", 167), rig.pos(), flush=True)
if rig.pos()[0] == 167:
    rig.bank("lab_front")
    print("167 lobby:", talk_all(167), flush=True)
    for room, (wx, wy) in ROOMS.items():
        print(f"== room {room} via ({wx},{wy})", flush=True)
        if not door(167, (wx, wy + 1), "up", room):
            print("  could not enter", room, rig.pos(), flush=True)
            continue
        said = talk_all(room)
        journal(f"map={room} Cinnabar lab room: bodies said {said}")
        # a room that took the amber: leave and come back, talk again for the result
        if "OLD AMBER" not in bag():
            navigate(room, {(2, 6), (3, 6)})
            for _ in range(4):
                if rig.pos()[0] != room:
                    break
                rig.io.press("down", hold=16, release=16)
                rig.ctl.wait(90)
                settle()
            door(167, (wx, wy + 1), "up", room)
            p0 = [(n, lv) for n, lv, _h in rig.party()]
            again = talk_all(room)
            journal(f"map={room} lab, second visit: {again}; party {p0} -> {[(n, lv) for n, lv, _h in rig.party()]}")
            rig.bank("lab_revived")
            print("*** second visit done; party", [(n, lv) for n, lv, _h in rig.party()], flush=True)
            break
        navigate(room, {(2, 6), (3, 6)})
        for _ in range(4):
            if rig.pos()[0] != room:
                break
            rig.io.press("down", hold=16, release=16)
            rig.ctl.wait(90)
            settle()
print("final", rig.pos(), "bag", bag()[-4:], flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
