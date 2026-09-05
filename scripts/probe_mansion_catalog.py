"""Build the full switch->door catalog for the Cinnabar mansion.

Tests from mansion_catalog_end.state (map 165, door state B):
- (0,0,0): base state B doors on 165
- (1,0,0): press 165 once -> state A, doors on 165
- (0,1,0): press 214 once -> state A, doors on 165
- (0,0,1): press 215 once, fall through hole to 165, test 165 and 214 doors

Also test 216's switches after entering the basement.
"""

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
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)


def journal(content):
    row = {
        "referenced_time": datetime.now(timezone.utc).isoformat(),
        "priority": "important",
        "content": content,
        "source_session": "extractor",
    }
    append_observations("pokedex/memory", [row], dedupe=True)


def drain(rig, limit=10):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def test_door(rig, mp, stand, face):
    drain(rig)
    if rig.walk(mp, {stand}, battle=rig.battle) is not True or rig.pos()[1:] != stand:
        return "unreachable"
    before = rig.pos()
    rig.io.press(face, hold=16, release=16)
    rig.ctl.wait(40)
    drain(rig)
    moved = rig.pos() != before
    if moved:
        rig.walk(mp, {stand}, battle=rig.battle)
    return "open" if moved else "shut"


def test_doors_165(rig):
    return {
        "D16_7": test_door(rig, 165, (16, 6), "down"),
        "D24_13": test_door(rig, 165, (24, 12), "down"),
        "D20_17": test_door(rig, 165, (20, 16), "down"),
        "D21_17": test_door(rig, 165, (21, 16), "down"),
    }


def test_doors_214(rig):
    return {
        "D9_4": test_door(rig, 214, (8, 4), "right"),
        "D9_5": test_door(rig, 214, (8, 5), "right"),
    }


def press_switch(rig, mp, stand, face):
    drain(rig)
    if rig.walk(mp, {stand}, battle=rig.battle) is not True or rig.pos()[1:] != stand:
        return None
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(20)
    drain(rig)
    pages = []
    for _ in range(5):
        rig.ctl.press("a")
        rig.ctl.wait(50)
        t = rig.textbox()
        if t and (not pages or t != pages[-1]):
            pages.append(t)
        if pages and not t:
            break
    drain(rig)
    return pages


def stairs(rig, mp, beside, key, want):
    drain(rig)
    rig.walk(mp, set(beside), battle=rig.battle)
    for _ in range(3):
        if rig.pos()[0] == want:
            return True
        rig.io.press(key, hold=16, release=16)
        rig.ctl.wait(70)
        drain(rig)
    return rig.pos()[0] == want


# --- Test 1: base state B ---
print("=== TEST 1: base state B ===", flush=True)
rig = Rig("data/local_runs/roster-bench/mansion_catalog_end.state", settle_on_boot=True)
print("start", rig.pos(), flush=True)
doors1 = test_doors_165(rig)
print("state B doors:", doors1, flush=True)

# --- Test 2: press 165 once (state A) ---
print("=== TEST 2: press 165 once ===", flush=True)
pages = press_switch(rig, 165, (2, 6), "up")
print("165 switch pages:", pages, flush=True)
doors2 = test_doors_165(rig)
print("state A doors:", doors2, flush=True)

# --- Test 3: press 165 again (back to B) ---
print("=== TEST 3: press 165 again (back to B) ===", flush=True)
pages = press_switch(rig, 165, (2, 6), "up")
print("165 switch pages:", pages, flush=True)
doors3 = test_doors_165(rig)
print("back to B doors:", doors3, flush=True)

# --- Test 4: press 214 once (state A) ---
print("=== TEST 4: press 214 once ===", flush=True)
print("165 -> 214:", stairs(rig, 165, [(5, 11)], "up", 214), rig.pos(), flush=True)
if rig.pos()[0] == 214:
    pages = None
    for stand, face in (((2, 12), "up"), ((3, 11), "left"), ((1, 11), "right")):
        pages = press_switch(rig, 214, stand, face)
        if pages and any("switch" in p.lower() for p in pages):
            break
    print("214 switch pages:", pages, flush=True)
    print("214 -> 165:", stairs(rig, 214, [(5, 11)], "up", 165), rig.pos(), flush=True)
    if rig.pos()[0] == 165:
        doors4 = test_doors_165(rig)
        print("after 214 press doors:", doors4, flush=True)

# --- Test 5: press 215 once ---
print("=== TEST 5: press 215 once ===", flush=True)
# reload fresh to be in known state B
rig2 = Rig("data/local_runs/roster-bench/mansion_catalog_end.state", settle_on_boot=True)
print("reloaded", rig2.pos(), flush=True)
print("165 -> 214:", stairs(rig2, 165, [(5, 11)], "up", 214), rig2.pos(), flush=True)
if rig2.pos()[0] == 214:
    print("214 -> 215:", stairs(rig2, 214, [(6, 2), (7, 1)], "up", 215), rig2.pos(), flush=True)
if rig2.pos()[0] == 215:
    pages = None
    for stand, face in (((10, 6), "up"), ((11, 5), "left"), ((9, 5), "right"), ((10, 4), "down")):
        pages = press_switch(rig2, 215, stand, face)
        if pages and any("switch" in p.lower() for p in pages):
            break
    print("215 switch pages:", pages, flush=True)
    # test 214 doors from 215(6,1) or similar? We can't reach main 214, but we can test from the pocket
    if rig2.pos()[0] == 214:
        doors_214_after_215 = test_doors_214(rig2)
        print("214 doors after 215 press:", doors_214_after_215, flush=True)
    # fall through the hole
    if rig2.pos()[0] == 215:
        print("215 walk to (16,13):", rig2.walk(215, {(16, 13)}, battle=rig2.battle), rig2.pos(), flush=True)
        if rig2.pos()[1:] == (16, 13):
            rig2.screenshot("mansion_hole_before")
            before = rig2.pos()
            rig2.io.press("down", hold=16, release=16)
            rig2.ctl.wait(90)
            drain(rig2)
            rig2.screenshot("mansion_hole_after")
            print(f"hole fall: {before} -> {rig2.pos()}", flush=True)
if rig2.pos()[0] == 165:
    doors5 = test_doors_165(rig2)
    print("165 doors after 215 press + hole fall:", doors5, flush=True)
    # also test from inside the pocket
    pocket = {}
    for stand in ((20, 18), (21, 18)):
        drain(rig2)
        rig2.walk(165, {stand}, battle=rig2.battle)
        if rig2.pos()[1:] != stand:
            pocket[stand] = "unreachable"
            continue
        b = rig2.pos()
        rig2.io.press("up", hold=16, release=16)
        rig2.ctl.wait(40)
        drain(rig2)
        pocket[stand] = "open" if rig2.pos() != b else "shut"
        if rig2.pos() != b:
            rig2.walk(165, {stand}, battle=rig2.battle)
    print("pocket doors from inside:", pocket, flush=True)
    # walk out of pocket and test 165 main area doors
    drain(rig2)
    rig2.walk(165, {(20, 16)}, battle=rig2.battle)
    if rig2.pos()[1:] == (20, 16):
        b = rig2.pos()
        rig2.io.press("down", hold=16, release=16)
        rig2.ctl.wait(40)
        drain(rig2)
        print("outside pocket door test:", rig2.pos() != b, rig2.pos(), flush=True)

# --- Write journal ---
obs = []
obs.append(
    {
        "referenced_time": datetime.now(timezone.utc).isoformat(),
        "priority": "important",
        "source_session": "extractor",
        "content": (
            f"map=165 mansion catalog: base state B doors {doors1}; "
            f"after 165 press (state A) doors {doors2}; "
            f"after 165 second press (back to B) doors {doors3}; "
            f"after 214 press doors {doors4 if 'doors4' in dir() else 'N/A'}; "
            f"after 215 press + hole fall doors {doors5 if 'doors5' in dir() else 'N/A'}; "
            f"pocket from inside {pocket if 'pocket' in dir() else 'N/A'}"
        ),
    }
)
if obs:
    append_observations("pokedex/memory", obs, dedupe=True)

print("=== CATALOG COMPLETE ===", flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
