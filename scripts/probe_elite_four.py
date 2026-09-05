"""The League: lobby (174) north door -> rooms 245, 246, 247 (trainer at (5,2), talked to from (5,3)), the big room
113 (trainer (6,1) from (6,2)), the last room 120 (body (4,2) from (4,3)), then 118. Each fight is the agent's; a win
is the battle ending with the party standing on the same map. Bank after every win. What each says is the record."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/indigo_lobby.state"
ROOMS = [  # (map, stand beside the body, face, north-door step cells, bank)
    (245, (5, 3), "up", {(4, 1), (5, 1)}, "e4_room1_won"),
    (246, (5, 3), "up", {(4, 1), (5, 1)}, "e4_room2_won"),
    (247, (5, 3), "up", {(4, 1), (5, 1)}, "e4_room3_won"),
    (113, (6, 2), "up", {(5, 1), (6, 1)}, "e4_room4_won"),
    (120, (4, 3), "up", {(3, 1), (4, 1)}, "champion_won"),
]
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
        rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
        rig.ctl.wait(24)
        if rig.pos()[0] != mp:
            return ("left-map", rig.pos())
        if rig.pos()[1:] == (x, y):
            stuck += 1
            if stuck >= 3:
                blocked.add((nx, ny))
                stuck = 0
                print(f"  refused {(x, y)}->{(nx, ny)}", flush=True)
        else:
            stuck = 0
    return ("cap", rig.pos()[1:])


def talk_and_fight(face):
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(16)
    pages = []
    for _ in range(40):
        rig.ctl.press("a")
        rig.ctl.wait(60)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
        if rig.mem[qm.ADDR_IN_BATTLE]:
            break
    fought = bool(rig.mem[qm.ADDR_IN_BATTLE])
    if fought:
        rig.battle()
    after = []
    for _ in range(30):
        settle()
        t = rig.textbox()
        if t and (not after or t != after[-1]):
            after.append(t)
        if not t:
            break
        rig.ctl.press("a")
        rig.ctl.wait(50)
    return fought, pages[:6], after[:6]


def through_door(mp, cells):
    r = navigate(mp, cells)
    for _ in range(3):
        if rig.pos()[0] != mp:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    return r


print("start", rig.pos(), [(n, lv, hp) for n, lv, hp in rig.party()], flush=True)
settle()
if rig.pos()[0] == 174:
    r = through_door(174, {(8, 1)})
    print("lobby north door:", r, rig.pos(), flush=True)
    if rig.pos()[0] == 174:
        # a body may guard the door: talk to whoever stands nearest and try again
        for b in sorted(bodies(), key=lambda b: abs(b[0] - 8) + abs(b[1] - 1)):
            if abs(b[0] - 8) + abs(b[1] - 1) <= 3:
                navigate(174, {(b[0], b[1] + 1)})
                print("  guard", b, "says:", rig.talk("up")[:120], flush=True)
                break
        r = through_door(174, {(8, 1)})
        print("lobby north door (again):", r, rig.pos(), flush=True)
for mp, stand, face, door, bank in ROOMS:
    if rig.pos()[0] != mp:
        print(f"not on map {mp}: at {rig.pos()}; stopping", flush=True)
        break
    r = navigate(mp, {stand})
    print(f"room {mp}: to {stand}: {r}", flush=True)
    hp0 = [(n, hp) for n, _l, hp in rig.party()]
    fought, said, after = talk_and_fight(face)
    party = [(n, hp) for n, _l, hp in rig.party()]
    standing = any(hp > 0 for _n, hp in party)
    won = fought and rig.pos()[0] == mp and standing
    print(f"room {mp}: fought={fought} won={won} said={said} after={after} party={party}", flush=True)
    journal(f"map={mp} League room: said {said}; fought={fought}; after {after}; party after {party}")
    rig.screenshot(f"league_{mp}")
    if not won:
        rig.bank(f"league_{mp}_stopped")
        break
    rig.bank(bank)
    print(f"*** {bank} ***", flush=True)
    r = through_door(mp, door)
    print(f"room {mp}: north door: {r} -> {rig.pos()}", flush=True)
if rig.pos()[0] == 118:
    rig.bank("hall_of_fame")
    print("*** HALL OF FAME (118) ***", rig.pos(), flush=True)
    said = []
    for _ in range(40):
        t = rig.textbox()
        if t and (not said or t != said[-1]):
            said.append(t)
        rig.ctl.press("a")
        rig.ctl.wait(50)
    journal(f"map=118 HALL OF FAME: {said[:12]}")
    print("hall:", said[:12], flush=True)
print("final", rig.pos(), [(n, lv, hp) for n, lv, hp in rig.party()], flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
