"""Beat 17 recording: the Articuno acquisition as one recorded run. From seafoam_b3_main.state (B3, clean boulders):
the twelve STRENGTH pushes that fill both holes, the fall through (6,16), the quiet current at (7,11), the left
channel to the platform, 'Gyaoo!', and the catch (Dugtrio SCRATCH + SAND-ATTACK, Hypno POISON GAS, ULTRA BALLs).
Every press is a frame (live_label, frame_interval=1); rig.finish writes summary.json for the viewer."""

import json
import subprocess
import sys
from collections import deque

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
K = {(1, 0): "right", (-1, 0): "left", (0, 1): "down", (0, -1): "up"}
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/seafoam_b3_main.state"
LABEL = sys.argv[2] if len(sys.argv) > 2 else "17 · Seafoam Islands — Articuno"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True, live_label=LABEL, frame_interval=1)
ag, mr = rig.ag, rig.ag.memory
CHAIN = [
    ((9, 15), "up", (9, 14), (9, 13)),
    ((6, 14), "left", (5, 14), (4, 14)),
    ((5, 14), "left", (4, 14), (3, 14)),
    ((4, 14), "left", (3, 14), (2, 14)),
    ((3, 14), "left", (2, 14), (1, 14)),
    ((2, 14), "left", (1, 14), (0, 14)),
    ((3, 14), "down", (3, 15), (3, 16)),
    ((9, 14), "up", (9, 13), (9, 12)),
    ((8, 13), "down", (8, 14), (8, 15)),
    ((9, 15), "left", (8, 15), (7, 15)),
    ((8, 15), "left", (7, 15), (6, 15)),
    ((6, 14), "down", (6, 15), (6, 16)),
]


def tile(mp, x, y):
    return int(TRUTH["maps"][str(mp)]["tiles"][y][2 * x : 2 * x + 2], 16)


def enterable(mp, x, y, water):
    m = TRUTH["maps"][str(mp)]
    if not (0 <= x < m["width"] and 0 <= y < m["height"]) or tile(mp, x, y) == 0x22:
        return False
    return m["grid"][y][x] == "1" or (water and tile(mp, x, y) in (0x14, 0x15))


def drain(n=16):
    for _ in range(n):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def boulders():
    return sorted(tuple(b[:2]) for b in rig.bodies())


def navigate(mp, goals, water=True, cap=400, solid=()):
    goals, blocked, stuck = set(goals), set(solid), 0
    for _ in range(cap):
        drain()
        m, x, y = rig.pos()
        if m != mp:
            return ("left-map", (m, x, y))
        if (x, y) in goals:
            return ("reached", (x, y))
        prev, q, path = {(x, y): None}, deque([(x, y)]), None
        while q:
            c = q.popleft()
            if c in goals:
                path = [c]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                path = path[::-1]
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c[0] + dx, c[1] + dy)
                if n not in prev and n not in blocked and enterable(mp, *n, water):
                    prev[n] = c
                    q.append(n)
        if not path or len(path) < 2:
            return ("no-path", (x, y))
        nx, ny = path[1]
        if tile(mp, nx, ny) == 0x14 and tile(mp, x, y) != 0x14:
            rig.io.press(K[(nx - x, ny - y)], hold=4, release=8)
            rig.ctl.wait(12)
            before = rig.pos()
            rig.use_field_move("SURF", species="Gyarados")
            drain()
            rig.ctl.wait(30)
            if rig.pos() == before:
                blocked.add((nx, ny))
                continue
        else:
            rig.io.press(K[(nx - x, ny - y)], hold=12, release=8)
            rig.ctl.wait(24)
            drain()
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


def in_battle():
    return bool(rig.mem[qm.ADDR_IN_BATTLE])


def pages_until_menu(cap=60):
    out = []
    for _ in range(cap):
        if not in_battle() or mr.battle_menu_visible():
            return out
        t = rig.textbox()
        if t and (not out or t != out[-1]):
            out.append(t)
        rig.ctl.press("b")
        rig.ctl.wait(24)
    return out


def do_fight(slot):
    bs = mr.read_battle_state()
    if not ag._select_battle_menu("fight"):
        return []
    ag._select_move_slot(slot)
    ag._await_turn_resolved(bs.enemy_hp, bs.player_hp, list(bs.move_pp))
    return pages_until_menu()


def do_switch(i):
    if not ag._select_battle_menu("pkmn"):
        return []
    rig.ctl.wait(20)
    rig.ctl.navigate_menu(i)
    rig.ctl.wait(120)
    rig.ctl.mash_a(5, delay=30)
    rig.ctl.wait(60)
    return pages_until_menu()


def do_ball():
    idx = next((i for i, (n, _q) in enumerate(rig.bag_named(full=True)) if n == "ULTRA BALL"), None)
    if idx is None or not ag._select_battle_menu("item"):
        return [], False
    rig.ctl.wait(20)
    for _ in range(24):
        pos = mr._read(0xCC36) + mr._read(0xCC26)
        if pos == idx:
            break
        rig.ctl.press("down" if pos < idx else "up")
        rig.ctl.wait(12)
    rig.ctl.press("a")
    rig.ctl.wait(120)
    rig.ctl.mash_a(3, delay=30)
    pages = pages_until_menu(cap=80)
    caught = any("caught" in p.lower() for p in pages) or (not in_battle() and mr.read_enemy_hp() > 0)
    return pages, caught


outcome, throws, caught = "started", 0, False
try:
    print("start", rig.pos(), "boulders", boulders(), flush=True)
    drain()
    rig.use_field_move("STRENGTH", species="Gyarados")
    drain()
    for i, (stand, face, boulder, expect) in enumerate(CHAIN):
        navigate(161, {stand}, water=False, solid=set(boulders()))
        if rig.pos()[1:] != stand:
            raise RuntimeError(f"push {i}: cannot stand {stand}")
        rig.io.press(face, hold=4, release=8)
        rig.ctl.wait(16)
        drain()
        rig.io.press(face, hold=16, release=16)
        rig.ctl.wait(80)
        drain()
        if expect not in boulders():
            raise RuntimeError(f"push {i} {boulder} {face} did not land at {expect}: {boulders()}")
        rig.emit("milestone", what=f"boulder {boulder} pushed {face}", boulders=boulders())
    rig.emit("milestone", what="both B3 holes filled")
    for stand, face in (((6, 15), "down"), ((5, 16), "right"), ((7, 16), "left")):
        navigate(161, {stand}, water=False, solid=set(boulders()))
        if rig.pos()[1:] == stand:
            rig.io.press(face, hold=16, release=16)
            rig.ctl.wait(80)
            drain()
        if rig.pos()[0] == 162:
            break
    if rig.pos()[0] != 162:
        raise RuntimeError("did not fall to B4")
    rig.emit("milestone", what="fell through (6,16) to B4", pos=list(rig.pos()))
    navigate(162, {(7, 11)})
    rig.io.press("down", hold=6, release=8)
    rig.ctl.wait(16)
    drain()
    rig.use_field_move("SURF", species="Gyarados")
    drain()
    rig.ctl.wait(30)
    if rig.pos()[1:] != (7, 12):
        raise RuntimeError(f"the current still blocks (7,11): {rig.pos()}")
    rig.emit("milestone", what="the current is stopped: SURF accepted at (7,11)")
    navigate(162, {(7, 2)})
    if rig.pos()[1:] != (7, 2):
        raise RuntimeError(f"platform not reached: {rig.pos()}")
    rig.emit("milestone", what="the platform", pos=list(rig.pos()))
    legend = None
    for attempt in range(4):  # a wild can jump in on the platform; fight it and talk again
        drain()
        rig.walk(162, {(6, 2)}, battle=rig.battle)
        drain()
        rig.io.press("up", hold=4, release=8)
        rig.ctl.wait(16)
        for _ in range(12):
            if in_battle():
                break
            rig.ctl.press("a")
            rig.ctl.wait(50)
        rig.ctl.wait(120)
        bs = mr.read_battle_state()
        if in_battle() and bs.enemy_level >= 45:
            legend = bs.enemy_species_name
            break
        print(f"  attempt {attempt}: a wild {bs.enemy_species_name} L{bs.enemy_level}; fighting it off", flush=True)
        rig.battle()
        drain()
    if legend is None:
        raise RuntimeError("the platform sprite never came to battle")
    rig.emit("milestone", what=f"engaged {bs.enemy_species_name} L{bs.enemy_level} {bs.enemy_hp}/{bs.enemy_max_hp}")
    print("engaged:", bs.enemy_species_name, bs.enemy_level, bs.enemy_hp, flush=True)
    for _ in range(40):  # the intro plays before the first menu; do not read the flag during the fade
        if mr.battle_menu_visible():
            break
        if rig.textbox():
            rig.ctl.press("b")
        rig.ctl.wait(20)
    print(
        "battle menu up:",
        mr.battle_menu_visible(),
        "in_battle:",
        in_battle(),
        "text:",
        repr(rig.textbox()[:40]),
        flush=True,
    )
    phase = ["switch_dug", "sand", "sand", "switch_hyp", "gas"]  # no SCRATCH: poison is a race
    gas_tries = 0
    quiet = 0
    for turn in range(90):
        if not in_battle():
            quiet += 1
            if quiet > 3:
                print("battle flag stayed clear; leaving the loop", flush=True)
                break
            rig.ctl.wait(30)
            continue
        quiet = 0
        bs = mr.read_battle_state()
        if bs.enemy_hp == 0 and bs.enemy_max_hp:
            outcome = "enemy-fainted"
            break
        frac = (bs.player_hp / bs.player_max_hp) if bs.player_max_hp else 1.0
        if frac < 0.35:
            party = rig.party()
            pick = max((i for i in (0, 2, 3, 4, 1) if party[i][2] > 0), key=lambda i: party[i][2], default=None)
            if pick is not None:
                do_switch(pick)
                continue
        if phase:
            step = phase.pop(0)
            p = {
                "switch_dug": lambda: do_switch(1),
                "scratch": lambda: do_fight(0),
                "sand": lambda: do_fight(3),
                "switch_hyp": lambda: do_switch(4),
                "gas": lambda: do_fight(1),
            }[step]()
            if step == "gas":
                gas_tries += 1
                if not any("poison" in x.lower() for x in p) and gas_tries < 6:
                    phase.insert(0, "gas")
            continue
        p, caught = do_ball()
        throws += 1
        bs2 = mr.read_battle_state()
        print(f"ULTRA BALL #{throws}: caught={caught} enemy {bs2.enemy_hp}/{bs2.enemy_max_hp}", flush=True)
        rig.emit("milestone", what=f"ULTRA BALL #{throws}", caught=caught, enemy_hp=bs2.enemy_hp)
        if caught:
            outcome = "caught"
            break
        if dict(rig.bag_named(full=True)).get("ULTRA BALL", 0) == 0:
            outcome = "out-of-balls"
            break
    if caught:
        for _ in range(12):
            rig.ctl.press("b")
            rig.ctl.wait(30)
        rig.bank("beat17_articuno_caught")
except Exception as e:  # noqa: BLE001 - the recording must still be finished
    outcome = f"error: {e}"
    print(outcome, flush=True)
finally:
    print("outcome:", outcome, "throws:", throws, "pos:", rig.pos(), "run_id:", rig.run_id, flush=True)
    rig.finish(outcome=outcome, throws=throws, caught=caught, party=str(rig.party()), pos=str(rig.pos()))
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
