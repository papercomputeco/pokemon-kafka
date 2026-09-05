"""Verify secret_key.state has SECRET KEY in bag and record position."""

import sys

sys.path.insert(0, "scripts")
from expedition_rig import Rig

rig = Rig("data/local_runs/roster-bench/secret_key.state", settle_on_boot=True)
print("pos:", rig.pos(), flush=True)
names = [n for n, _ in rig.bag_named(full=True)]
print("bag:", names, flush=True)
print("SECRET KEY present:", any("SECRET KEY" in n for n in names), flush=True)
