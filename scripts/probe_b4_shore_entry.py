"""Characterise the B4 (162) shore->water surf entry. Reach each 0x15 shore from the central land, face the water
it borders, arm SURF, and read the exact sentence. This is the mechanic that gates the (6,1) legendary platform.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone

sys.path.insert(0, "scripts")
import quartermaster as qm  # noqa: E402
from expedition_rig import Rig  # noqa: E402
from memory_writer import append_observations  # noqa: E402

TRUTH = json.load(open("references/rom_truth.json"))
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/b4_from_conveyor.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def drain(limit=12):
    for _ in range(limit):
        if rig.mem[qm.ADDR_IN_BATTLE]:
            rig.battle()
            continue
        if not rig.textbox():
            return
        rig.ctl.press("b")
        rig.ctl.wait(24)


def journal(content):
    append_observations(
        "pokedex/memory",
        [
            {
                "referenced_time": datetime.now(timezone.utc).isoformat(),
                "priority": "important",
                "source_session": "extractor",
                "content": content,
            }
        ],
        dedupe=True,
    )


# shore -> (water cell it faces, face key)
SHORES = {(7, 11): ((7, 12), "down"), (7, 3): ((7, 4), "down"), (23, 5): ((23, 6), "down")}
print("start", rig.pos(), flush=True)
results = {}
for shore, (water, face) in SHORES.items():
    drain()
    w = rig.walk(162, {shore}, battle=rig.battle)
    at = rig.pos()
    if at[1:] != shore:
        results[str(shore)] = f"could-not-reach (at {at[1:]})"
        print(f"shore {shore}: could not reach, at {at[1:]}", flush=True)
        continue
    rig.io.press(face, hold=4, release=8)
    rig.ctl.wait(16)
    before = rig.pos()
    armed = rig._arm_surf()
    said = rig.textbox()
    after = rig.pos()
    rig.screenshot(f"b4_shore_{shore[0]}_{shore[1]}")
    moved = after != before
    results[str(shore)] = f"armed={armed} moved={moved} now={after[1:]} said={said!r}"
    print(
        f"shore {shore} face {face} -> {water}: armed={armed} moved={moved} now={after[1:]} said={said!r}", flush=True
    )
    drain()
    if moved and after[0] == 162:
        rig.bank(f"b4_on_water_from_{shore[0]}_{shore[1]}")
journal(f"map=162 B4 shore->water surf entry test (Gyarados party idx 5): {results}")
print("results:", results, flush=True)
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
