import sys

sys.path.insert(0, "scripts")
import road
from expedition_rig import Rig

STATE = "data/local_runs/roster-bench/seafoam_loop_stuck_3.state"

rig = Rig(STATE, settle_on_boot=True)
mp, x, y = rig.pos()
print("pos:", mp, x, y)
print("bodies:", rig.bodies())

truth = rig.truth
pairs = rig.pairs
reachable = road.walkable(truth, pairs, mp, (x, y), bodies=rig.bodies())
print("reachable cells count:", len(reachable))

boulders = [(3, 15), (5, 14), (8, 14), (9, 14), (18, 6), (19, 6)]
for bx, by in boulders:
    adj = {(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)}
    can = adj & reachable
    print(f"boulder ({bx},{by}) adjacent reachable: {can}")
