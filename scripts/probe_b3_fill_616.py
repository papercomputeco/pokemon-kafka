"""Fill B3's (6,16) hole via boulder (8,14): DOWN to (8,15), LEFT to (7,15), LEFT to (6,15), DOWN into (6,16).
Then check where the boulder landed on B4 and whether it stopped the (7,11) 'too fast' current -- the gate to the
(6,1) legendary platform. Each push is STRENGTH (16-frame hold), judged by the sprite table.
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
STATE = sys.argv[1] if len(sys.argv) > 1 else "data/local_runs/roster-bench/seafoam_loop_stuck_3.state"
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
rig = Rig(STATE, settle_on_boot=True)


def drain(n=16):
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


def boulders():
    return sorted(tuple(b[:3]) for b in rig.bodies())


def push(stand, face, boulder):
    """Stand beside `boulder`, face it, STRENGTH-push. Return (ok, boulders_after)."""
    drain()
    w = rig.walk(161, {stand}, battle=rig.battle)
    if rig.pos()[1:] != stand:
        return (f"cannot-stand {stand} at {rig.pos()[1:]} ({w})", boulders())
    before = boulders()
    if not rig.use_field_move("STRENGTH", face=face, species="Gyarados"):
        # already active or menu path; press A through any prompt
        pass
    for _ in range(4):
        rig.ctl.press("a")
        rig.ctl.wait(50)
    drain()
    rig.io.press(face, hold=16, release=16)
    rig.ctl.wait(70)
    drain()
    after = boulders()
    moved = after != before
    return (f"moved={moved} boulder {boulder} -> {[b for b in after if b not in before]}", after)


print("start", rig.pos(), "boulders", boulders(), flush=True)
drain()
# STRENGTH once
rig.use_field_move("STRENGTH", species="Gyarados")
drain()
steps = [
    ((8, 13), "down", (8, 14)),  # (8,14) -> (8,15)
    ((9, 15), "left", (8, 15)),  # (8,15) -> (7,15)
    ((8, 15), "left", (7, 15)),  # (7,15) -> (6,15)
    ((6, 14), "down", (6, 15)),  # (6,15) -> (6,16) hole
]
log = []
for stand, face, boulder in steps:
    r, after = push(stand, face, boulder)
    print(f"push {boulder} {face} from {stand}: {r}", flush=True)
    rig.screenshot(f"fill616_{boulder[0]}_{boulder[1]}_{face}")
    log.append(f"{boulder}{face}:{r}")
    if r.startswith("cannot"):
        break
after = boulders()
print("boulders after the sequence:", after, flush=True)
filled = not any(b[:2] == (6, 15) for b in [tuple(x) for x in after]) and (6, 16) in [b[:2] for b in after]
journal(f"map=161 (6,16) fill attempt via (8,14): {log}; boulders now {after}")
rig.bank("b3_616_attempt")
# now drop to B4 and test the current
if (6, 16) in [b[:2] for b in after]:
    print("(6,16) shows a boulder sprite -> the fill dropped it to B4; testing the current", flush=True)
    for stand, face in (((6, 15), "down"), ((5, 16), "right"), ((7, 16), "left")):
        if rig.walk(161, {stand}, battle=rig.battle) and rig.pos()[1:] == stand:
            rig.io.press(face, hold=16, release=16)
            rig.ctl.wait(70)
            drain()
        if rig.pos()[0] == 162:
            break
    print("on B4?", rig.pos(), "boulders", boulders(), flush=True)
    if rig.pos()[0] == 162:
        rig.bank("b4_after_616_fill")
        rig.screenshot("b4_after_616_fill")
        journal(f"map=162 after filling B3 (6,16): B4 boulder sprites {boulders()}; player at {rig.pos()[1:]}")
        # test (7,11) current
        if rig.walk(162, {(7, 11)}, battle=rig.battle) and rig.pos()[1:] == (7, 11):
            rig.io.press("down", hold=6, release=8)
            rig.ctl.wait(16)
            before = rig.pos()
            rig.use_field_move("SURF", species="Gyarados")
            said = rig.textbox()
            moved = rig.pos() != before
            print(
                f"*** (7,11) current after (6,16) fill: moved={moved} now={rig.pos()[1:]} said={said!r} ***", flush=True
            )
            journal(f"map=162 (7,11) current AFTER (6,16) fill: moved={moved} said={said!r}")
            rig.screenshot("b4_711_after_fill")
            if moved:
                rig.bank("b4_current_cleared")
print("final", rig.pos(), flush=True)
print(subprocess.run(["date"], capture_output=True, text=True).stdout.strip(), flush=True)
