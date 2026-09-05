"""The lab said 'Your pack is crammed full!' with the OLD AMBER still in the bag (probe_cinnabar_lab, 2026-09-04).
From lab_front.state (the boot's settle steps off the lab mat onto Cinnabar, map 8): into the Center (door (11,11) ->
171), leave items in the PC's storage along storage_plan -- the game's own answer to a full bag, never a toss --
heal, back to the lab, into room 170, hand the amber to the (5,2) body, leave and come back for what it gives
back. The bag and the party are the verdict. Banks lab_pc_stored, lab_amber_given, lab_revived."""

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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/lab_front.state"
ROOM, DOOR, BODY = 170, (16, 4), (5, 2)
CENTER, CENTER_DOOR, LAB_DOOR = 171, (11, 11), (6, 9)
STORE = int(sys.argv[2]) if len(sys.argv) > 2 else 4
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


def talk(face, n=40):
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


def leave_and_return():
    print("  leave:", navigate(ROOM, {(2, 6), (3, 6)}), flush=True)
    for _ in range(4):
        if rig.pos()[0] != ROOM:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    print("  outside at", rig.pos(), flush=True)
    return door(167, (DOOR[0], DOOR[1] + 1), "up", ROOM)


def party():
    return [(n, lv) for n, lv, _h in rig.party()]


def talk_bodies(mp):
    """Every body on this map, from a cell next to where it stands NOW (the (5,2) scientist wanders:
    the first pass walked onto his empty tile and said nothing)."""
    out = {}
    for b in sorted({tuple(s[:2]) for s in rig.bodies()}):
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
                print(f"  {mp} body {b}: {out[b][:8]} | gone={gone} got={got}", flush=True)
                if gone or got:
                    journal(f"map={mp} lab body {b}: {out[b][:8]}; bag lost {gone} gained {got}")
                    return out, gone, got
                break
        else:
            print(f"  {mp} body {b}: unreachable", flush=True)
    return out, [], []


print("start", rig.pos(), "stacks", len(rig.bag()), "full", rig.bag_full(), flush=True)
print("bag:", rig.bag_named(full=True), flush=True)
if rig.pos()[0] == 167:  # still on the lab mat: step out
    rig.io.press("down", hold=16, release=16)
    rig.ctl.wait(90)
    settle()
if rig.pos()[0] == 8 and len(rig.bag()) > 20 - 2:  # room for the amber's return and the TM giver
    print("center door:", door(8, (CENTER_DOOR[0], CENTER_DOOR[1] + 1), "up", CENTER), rig.pos(), flush=True)
if rig.pos()[0] == CENTER:
    n = rig.store_at_pc(STORE, keep=("OLD AMBER", "POKe FLUTE"))
    print(f"stored {n} item(s) in the PC; bag now {len(rig.bag())}/20:", bag(), flush=True)
    journal(f"map={CENTER} Cinnabar Center PC: stored {n} items along storage_plan; bag {bag()}")
    print("heal:", rig.heal_at_center(), flush=True)
    rig.bank("lab_pc_stored")
    print("  leave:", navigate(CENTER, {(3, 7), (4, 7)}), flush=True)
    for _ in range(4):
        if rig.pos()[0] != CENTER:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        settle()
    print("outside", rig.pos(), flush=True)
if rig.pos()[0] == 8:
    print("lab door:", door(8, (LAB_DOOR[0], LAB_DOOR[1] + 1), "up", 167), rig.pos(), flush=True)
if rig.pos()[0] == 167 and door(167, (DOOR[0], DOOR[1] + 1), "up", ROOM):
    print("in room", rig.pos(), flush=True)
    p0 = party()
    said, gone, got = talk_bodies(ROOM)
    if gone:
        rig.bank("lab_amber_given")
        for visit in range(3):
            if not leave_and_return():
                print("  could not re-enter", rig.pos(), flush=True)
                break
            again, _g, got2 = talk_bodies(ROOM)
            print(f"  visit {visit + 2}: {again} | party {party()} | bag {bag()}", flush=True)
            journal(f"map={ROOM} lab, visit {visit + 2}: {again}; party {p0} -> {party()}; bag {bag()}")
            if party() != p0 or got2:
                rig.bank("lab_revived")
                break
print("final", rig.pos(), "party", party(), "bag", bag(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
