"""Finish the Secret House hand-over on a full bag: toss, talk, verify HM03 by bag growth, teach SURF.

The --hunt-item leg reached map 222 (3,4) and heard "You're the first person to reach the
SECRET HOUSE!" eleven times without the bag changing -- because the bag held 20 stacks, the
cartridge's limit, after a MAX POTION was swept up on 217. Every verdict here is RAM: slot
count, then HM03 in the bag, then move id 57 (SURF) landing in a party struct.
"""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

STATE = "data/local_runs/roster-bench/surf_strength-222.state"
TOSS = "NUGGET"  # sell-only; nothing on this branch needs it

rig = Rig(STATE, settle_on_boot=False)
names = [n for n, _ in rig.bag_named(full=True)]
print("bag slots:", len(names), "| pos:", rig.pos(), flush=True)
if len(names) >= 20:
    idx = names.index(TOSS)
    item_id = rig.bag()[idx][0]
    ok = rig.toss_stack(item_id)
    print(f"tossed {TOSS} (id {item_id}): {ok}; slots now {len(rig.bag())}", flush=True)

before = len(rig.bag())
for attempt in range(4):
    said = rig.talk("up")  # the NPC is at (3,3), we stand at (3,4)
    print(f"talk {attempt}: {said[:140]!r}", flush=True)
    for _ in range(12):
        rig.ctl.press("a")
        rig.ctl.wait(30)
    if len(rig.bag()) > before or any(n.startswith("HM03") for n, _ in rig.bag_named(full=True)):
        break
have = [n for n, _ in rig.bag_named(full=True) if n.startswith("HM")]
print("HMs in bag:", have, flush=True)
if not any(n.startswith("HM03") for n in have):
    print("HM03 NOT in the bag -- stopping before any teach", flush=True)
    rig.bank("surf_strength-222-nohm03")
    sys.exit(2)
rig.bank("surf_strength_hm03")
who = rig.teach("HM03")
print("teach HM03 ->", who, "| surfer:", rig.knows_move("SURF"), "| strength:", rig.knows_move("STRENGTH"), flush=True)
rig.bank("surf_and_strength")
print("banked surf_and_strength at", rig.pos(), flush=True)
