"""Beat 18 recording: the Elite Four and the Champion as one recorded run from indigo_lobby.state. Revives from the
bag first (roster by index), then each room's trainer from the cell below, the north doors, the big room, the last
room, and Oak's Hall of Fame cutscene through the credits. Every press is a frame; rig.finish writes summary.json."""

import json
import subprocess
import sys

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
import rom_truth as rt  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
PAIRS = rt.loaded_pairs(TRUTH)
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/indigo_lobby.state"
LABEL = sys.argv[2] if len(sys.argv) > 2 else "18 · Indigo Plateau — the Elite Four"
ROOMS = [
    (245, (5, 3), {(4, 1), (5, 1)}),
    (246, (5, 3), {(4, 1), (5, 1)}),
    (247, (5, 3), {(4, 1), (5, 1)}),
    (113, (6, 2), {(5, 1)}),
    (120, (4, 3), set()),
]
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True, live_label=LABEL, frame_interval=1)


def settle():
    for _ in range(3):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
        rig.ctl.press("b")
        rig.ctl.wait(20)


def bodies():
    return {tuple(b[:2]) for b in rig.bodies()}


def party():
    return [(n, lv, hp) for n, lv, hp in rig.party()]


def use_on_member(item, index):
    before = party()[index][2]
    rig.use_item(item)
    rig.ctl.wait(40)
    for _ in range(8):
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
    for _ in range(6):
        rig.ctl.press("b")
        rig.ctl.wait(25)
    return before, party()[index][2]


def wait_still(cap=1200):
    """Wait until the position has not changed for 80 frames: the big room (113) auto-walks the player from
    (24,16) to (6,11) over ~620 frames on entry (measured), and a press or a plan during that walk is lost."""
    last, still = rig.pos(), 0
    for _ in range(cap // 10):
        rig.ctl.wait(10)
        p = rig.pos()
        if p == last:
            still += 10
            if still >= 80:
                return p
        else:
            last, still = p, 0
    return rig.pos()


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


def talk_and_fight():
    rig.io.press("up", hold=4, release=8)
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
    for _ in range(30):
        settle()
        if not rig.textbox():
            break
        rig.ctl.press("a")
        rig.ctl.wait(50)
    return fought, pages[:4]


outcome, wins = "started", []
try:
    print("start", rig.pos(), party(), flush=True)
    settle()
    rig.emit("milestone", what="the lobby", party=str(party()))
    r = navigate(174, {(8, 1)})
    for _ in range(3):
        if rig.pos()[0] != 174:
            break
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    for mp, stand, door in ROOMS:
        wait_still()
        settle()
        if rig.pos()[0] != mp:
            raise RuntimeError(f"expected map {mp}, at {rig.pos()}")
        navigate(mp, {stand})
        fought, said = talk_and_fight()
        p = party()
        won = fought and rig.pos()[0] == mp and any(hp > 0 for _n, _l, hp in p)
        print(f"room {mp}: {said[:2]} won={won} party={[(n, hp) for n, _l, hp in p]}", flush=True)
        rig.emit("milestone", what=f"room {mp}: {'won' if won else 'lost'}", said=said[:2], party=str(p))
        if not won:
            raise RuntimeError(f"lost in room {mp}")
        wins.append(mp)
        if door:
            # the winner's speech swallows every direction press until it ends (measured: 25 A's were not
            # enough after Lance); advance with A until a real step registers by position
            first = next(iter(door))
            side = "left" if first[0] < stand[0] else "right"
            for _ in range(120):
                before = rig.pos()
                rig.io.press(side, hold=12, release=8)
                rig.ctl.wait(30)
                if rig.pos() != before:
                    break
                rig.ctl.press("a")
                rig.ctl.wait(40)
            wait_still()
            settle()
            r = navigate(mp, door)
            print(f"room {mp}: door step {r} at {rig.pos()}", flush=True)
            if rig.pos()[0] == mp and rig.pos()[1:] not in door:  # the planner did not take it: walk it by hand
                for key in ("left", "up", "up"):
                    rig.io.press(key, hold=12, release=8)
                    rig.ctl.wait(30)
            for _ in range(3):
                if rig.pos()[0] != mp:
                    break
                rig.io.press("up", hold=16, release=16)
                rig.ctl.wait(90)
                settle()
            print(f"room {mp}: after the door {rig.pos()}", flush=True)
    outcome = "champion"
    # Oak, the Hall of Fame, the credits: A until the game restarts the player at home
    maps = [rig.pos()[0]]
    for i in range(420):
        rig.ctl.press("a")
        rig.ctl.wait(40)
        m = rig.pos()[0]
        if m != maps[-1]:
            maps.append(m)
            rig.emit("milestone", what=f"map {m}", pos=list(rig.pos()))
        if maps[-1] == 0 and i > 300:
            break
    outcome = "hall-of-fame" if 118 in maps else outcome
    print("cutscene maps:", maps, flush=True)
    rig.bank("beat18_end")
except Exception as e:  # noqa: BLE001 - the recording must still be finished
    outcome = f"error: {e}"
    print(outcome, flush=True)
finally:
    print("outcome:", outcome, "wins:", wins, "run_id:", rig.run_id, flush=True)
    rig.finish(outcome=outcome, rooms_won=str(wins), party=str(party()), pos=str(rig.pos()))
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
