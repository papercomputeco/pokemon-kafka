"""After the credits: FLY to Pewter, heal at its Center (58), enter the two-floor building (52 -> 53) by the front
door at (14,7), talk to every body on both floors, then try the second door at (19,5) from outside. Everything the
bodies say is the record. Banks: pewter_post, pewter_museum."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/hall_of_fame.state"
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


def navigate(mp, goals, cap=300):
    goals, blocked, stuck = set(goals), set(), 0
    for _ in range(cap):
        settle()
        m, x, y = rig.pos()
        if m != mp:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        path = rt.path_on_map(TRUTH, PAIRS, mp, (x, y), goals, blocked=(bodies() - goals) | blocked)
        if not path or len(path) < 2:
            return ("no-path", (x, y))
        nx, ny = path[1]
        dx, dy = nx - x, ny - y
        rig.io.press(K[(dx // abs(dx) if dx else 0, dy // abs(dy) if dy else 0)], hold=12, release=8)
        rig.ctl.wait(40 if abs(dx) + abs(dy) == 2 else 24)
        if rig.pos()[0] != mp:
            return ("left-map", rig.pos())
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


def door(mp, stand, key, want):
    navigate(mp, {stand})
    for _ in range(3):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    return rig.pos()[0] == want


def talk_all(mp):
    said = {}
    for b in sorted(bodies()):
        for stand, face in (
            ((b[0], b[1] + 1), "up"),
            ((b[0] - 1, b[1]), "right"),
            ((b[0] + 1, b[1]), "left"),
            ((b[0], b[1] - 1), "down"),
        ):
            navigate(mp, {stand})
            if rig.pos()[1:] == stand:
                said[b] = rig.talk(face)
                settle()
                print(f"  {mp} body {b}: {said[b][:110]!r}", flush=True)
                break
        else:
            said[b] = None
            print(f"  {mp} body {b}: unreachable", flush=True)
    return said


print("start", rig.pos(), flush=True)
settle()
print("fly:", rig.fly_to("PEWTER CITY"), rig.pos(), flush=True)
settle()
if rig.pos()[0] == 2:
    rig.bank("pewter_post")
    if door(2, (13, 26), "up", 58):
        print("heal:", rig.heal_at_center(), [(n, lv, hp) for n, lv, hp in rig.party()], flush=True)
        settle()
        navigate(58, {(3, 5)})
        navigate(58, {(3, 6)})
        for _ in range(3):
            if rig.pos()[0] != 58:
                break
            rig.io.press("down", hold=16, release=16)
            rig.ctl.wait(90)
            settle()
    print("front door (14,7):", door(2, (14, 8), "up", 52), rig.pos(), flush=True)
if rig.pos()[0] == 52:
    rig.bank("pewter_museum")
    said1 = talk_all(52)
    journal(f"map=52 Pewter two-floor building 1F (from (14,7)): bodies said {said1}")
    print(
        "stairs (7,7):",
        door(52, (7, 6), "down", 53) or door(52, (8, 7), "left", 53) or door(52, (6, 7), "right", 53),
        rig.pos(),
        flush=True,
    )
    if rig.pos()[0] == 53:
        rig.bank("pewter_museum_2f")
        said2 = talk_all(53)
        journal(f"map=53 Pewter building 2F: bodies said {said2}")
        # back down and out the front
        door(53, (7, 6), "down", 52) or door(53, (8, 7), "left", 52) or door(53, (6, 7), "right", 52)
    if rig.pos()[0] == 52:
        navigate(52, {(10, 6), (11, 6)})
        for _ in range(3):
            if rig.pos()[0] != 52:
                break
            rig.io.press("down", hold=16, release=16)
            rig.ctl.wait(90)
            settle()
if rig.pos()[0] == 2:
    r = navigate(2, {(19, 6)})
    print("to the second door's step (19,6):", r, rig.pos(), flush=True)
    rig.screenshot("pewter_back_door")
    if rig.pos()[1:] == (19, 6):
        before = rig.pos()
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
        print(
            "second door (19,5):",
            "entered" if rig.pos()[0] == 52 else f"refused, said {rig.textbox()[:60]!r}",
            rig.pos(),
            flush=True,
        )
        journal(f"map=2 Pewter second door (19,5): nav {r}; step -> {rig.pos()}")
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
