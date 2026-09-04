"""Secret House on the Fly branch: free a slot with the bag engine, take HM03, teach SURF, bank."""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig  # noqa: E402

rig = Rig("data/local_runs/roster-bench/fuchsia_hm03-222.state", settle_on_boot=True)
print("start", rig.pos(), "| stacks:", len(rig.bag()), flush=True)
if rig.bag_full():
    print("make_room ->", rig.make_room(), "| stacks:", len(rig.bag()), flush=True)
before = len(rig.bag())
for attempt in range(3):
    said = rig.talk("up")  # NPC at (3,3); we stand at (3,4)
    for _ in range(12):
        rig.ctl.press("a")
        rig.ctl.wait(30)
    hms = [n for n, _ in rig.bag_named(full=True) if n.startswith("HM")]
    print(f"talk {attempt}: {said[:100]!r} | bag {before}->{len(rig.bag())} | HMs {hms}", flush=True)
    if any(n.startswith("HM03") for n in hms):
        break
if not any(n.startswith("HM03") for n, _ in rig.bag_named(full=True)):
    rig.screenshot("secret_house_no_hm03")
    rig.bank("fly_branch_no_hm03")
    sys.exit(2)
rig.bank("fly_branch_hm03")
who = rig.teach("HM03")
print("teach HM03 ->", who, "| surfer:", rig.knows_move("SURF"), "| flyer:", rig.knows_move("FLY"), flush=True)
if rig.knows_move("SURF") is not None:
    rig.bank("surf_and_fly")
    print("*** SURF + FLY on one baton:", rig.pos(), "***", flush=True)
