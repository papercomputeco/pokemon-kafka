"""League, last two rooms from league_113_stopped.state: REVIVE the fainted from the bag (roster by index), HYPER
POTION them, then the big room's trainer at (6,1) from (6,2), the (5,1)->(5,0) mat to 120, the body at (4,2) from (4,3),
and the (3,1)/(4,1) mats to 118. Banks e4_room4_won, champion_won, hall_of_fame."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/league_113_stopped.state"
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


def close_menus():
    for _ in range(6):
        rig.ctl.press("b")
        rig.ctl.wait(25)


def bodies():
    return {tuple(b[:2]) for b in rig.bodies()}


def party():
    return [(n, lv, hp) for n, lv, hp in rig.party()]


def use_on_member(item, index):
    """USE a bag item on party member `index`: the roster draws after USE; walk the cursor by index, A, then
    read the party. The verdict is the member's HP changing."""
    before = party()[index][2]
    rig.use_item(item)
    rig.ctl.wait(40)
    for _ in range(8):  # cursor to the member: the roster is a non-scrolling list from the lead
        cur = rig.mem[qm.ADDR_MENU_CUR]
        if cur == index:
            break
        rig.ctl.press("down" if cur < index else "up")
        rig.ctl.wait(16)
    rig.ctl.press("a")
    rig.ctl.wait(80)
    for _ in range(4):
        rig.ctl.press("a")
        rig.ctl.wait(40)
    close_menus()
    after = party()[index][2]
    return before, after


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


print("start", rig.pos(), party(), flush=True)
settle()
# 1) revive and heal from the bag
for i, (n, _lv, hp) in enumerate(party()):
    if hp <= 0 and "REVIVE" in dict(rig.bag_named(full=True)):
        print(f"  REVIVE -> {n}: {use_on_member('REVIVE', i)}", flush=True)
for i, (n, _lv, hp) in enumerate(party()):
    if 0 < hp < 200 and "HYPER POTION" in dict(rig.bag_named(full=True)):
        print(f"  HYPER POTION -> {n}: {use_on_member('HYPER POTION', i)}", flush=True)
print(
    "party now",
    party(),
    "| bag",
    {k: v for k, v in rig.bag_named(full=True) if k in ("REVIVE", "HYPER POTION", "FULL HEAL")},
    flush=True,
)
rig.bank("league_113_healed")
# 2) the rooms
ROOMS = [
    (113, (6, 2), "up", {(5, 1)}, "e4_room4_won"),
    (120, (4, 3), "up", {(3, 1), (4, 1)}, "champion_won"),
]
for mp, stand, face, door, bank in ROOMS:
    if rig.pos()[0] != mp:
        print(f"not on map {mp}: at {rig.pos()}; stopping", flush=True)
        break
    r = navigate(mp, {stand})
    print(f"room {mp}: to {stand}: {r} {rig.pos()}", flush=True)
    fought, said, after = talk_and_fight(face)
    p = party()
    won = fought and rig.pos()[0] == mp and any(hp > 0 for _n, _l, hp in p)
    print(f"room {mp}: fought={fought} won={won} said={said} after={after} party={p}", flush=True)
    journal(f"map={mp} League room: said {said}; fought={fought}; after {after}; party after {p}")
    rig.screenshot(f"league_{mp}")
    if not won:
        rig.bank(f"league_{mp}_stopped")
        break
    rig.bank(bank)
    print(f"*** {bank} ***", flush=True)
    r = navigate(mp, door)
    for _ in range(3):
        if rig.pos()[0] != mp:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    print(f"room {mp}: north door: {r} -> {rig.pos()}", flush=True)
if rig.pos()[0] == 118:
    rig.bank("hall_of_fame")
    print("*** HALL OF FAME (118) ***", rig.pos(), flush=True)
    said = []
    for _ in range(60):
        t = rig.textbox()
        if t and (not said or t != said[-1]):
            said.append(t)
        rig.ctl.press("a")
        rig.ctl.wait(50)
    journal(f"map=118 HALL OF FAME: {said[:14]}")
    print("hall:", said[:14], flush=True)
    rig.screenshot("hall_of_fame")
print("final", rig.pos(), party(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
