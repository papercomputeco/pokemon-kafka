"""Prep for badge 8: heal at Cinnabar's Center, buy Hyper Potions, FLY to Viridian, walk to the gym door and read it.
Banks: viridian_main (outside), gym8_inside (if the door opens)."""

import json
import subprocess
import sys

sys.path.insert(0, "scripts")
from datetime import datetime, timezone  # noqa: E402

import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/gyarados_L100.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)
HYPER_POTION = 18
MART = qm.Shop(8, (15, 11), 172, (2, 5), "left", (2, 3, HYPER_POTION, 57, 52, 53), ((3, 7), (4, 7)))


def drain(n=14):
    for _ in range(n):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


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


def door(mp, stand, key, want, tries=3):
    rig.walk(mp, {stand}, battle=rig.battle)
    for _ in range(tries):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(90)
        drain()
    return rig.pos()[0] == want


print("start", rig.pos(), [(n, lv, hp) for n, lv, hp in rig.party()], flush=True)
drain()
# mansion -> Cinnabar -> Center heal -> mart -> fly
door(165, (5, 26), "down", 8)
print("Cinnabar:", rig.pos(), flush=True)
if door(8, (11, 12), "up", 171):
    print("heal:", rig.heal_at_center(), [(n, lv, hp) for n, lv, hp in rig.party()], flush=True)
    drain()
    rig.walk(171, {(3, 5)}, battle=rig.battle)
    rig.walk(171, {(3, 6)}, battle=rig.battle)
    for _ in range(3):
        if rig.pos()[0] != 171:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
if rig.pos()[0] == 8 and len(rig.bag()) < 20 and door(8, (15, 12), "up", 172):
    rig.walk(172, {(2, 5)}, battle=rig.battle)
    drain()
    print("bought:", qm.buy(rig.io, MART, [(HYPER_POTION, 5)]), "money", qm.read_money(rig.io), flush=True)
    drain()
    rig.walk(172, {(3, 5)}, battle=rig.battle)
    rig.walk(172, {(3, 6)}, battle=rig.battle)
    for _ in range(3):
        if rig.pos()[0] != 172:
            break
        rig.io.press("down", hold=16, release=16)
        rig.ctl.wait(90)
        drain()
print("before the flight:", rig.pos(), [n for n, _ in rig.bag_named(full=True)][-4:], flush=True)
if rig.pos()[0] == 8:
    print("fly:", rig.fly_to("VIRIDIAN CITY"), rig.pos(), flush=True)
    drain()
if rig.pos()[0] == 1:
    rig.bank("viridian_main")
    gym = [(wx, wy, dst) for wx, wy, dst, _ in TRUTH["maps"]["1"]["warps"] if dst not in (255,)]
    print("Viridian warps:", gym, flush=True)
    # the gym door: try each interior warp's cell from below; report what the game says
    for wx, wy, dst in gym:
        m = TRUTH["maps"][str(dst)]
        if not (m["width"], m["height"]) == (20, 18):  # gyms measured so far are 20x18 interiors
            continue
        w = rig.walk(1, {(wx, wy + 1)}, battle=rig.battle)
        if rig.pos()[1:] != (wx, wy + 1):
            print(f"  cannot stand below ({wx},{wy}) -> {dst}: {w} at {rig.pos()}", flush=True)
            continue
        before = rig.pos()
        rig.io.press("up", hold=16, release=16)
        rig.ctl.wait(90)
        said = rig.textbox()
        print(f"  door ({wx},{wy}) -> map {dst}: now {rig.pos()} said {said!r}", flush=True)
        rig.screenshot(f"viridian_door_{dst}")
        journal(f"map=1 Viridian door ({wx},{wy}) -> map {dst} with 7 badges: {before}->{rig.pos()}, said {said!r}")
        drain()
        if rig.pos()[0] == dst:
            rig.bank("gym8_inside")
            print("*** INSIDE map", dst, "***", sorted(tuple(b[:2]) for b in rig.bodies()), flush=True)
            break
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
