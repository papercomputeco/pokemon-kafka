#!/usr/bin/env python3
"""The 29-NPC road: baton on Route 4 -> every body on the way -> Pallet -> does the south water open?

Two legs today called the water road "sealed" from the collision grid alone; the mission on file
says the same thing was declared on this side of the map, with twenty-nine bodies between here
and Pallet never talked to. This leg walks the road the game's own graph suggests and takes the
screen as witness at every refusal:

  * every body the cartridge lists for a map is engaged BEFORE leaving it (trainers fight,
    npcs talk; what they say is recorded verbatim),
  * routing is the engine's -- ``rt.route`` picks the hop, one hop per turn, failures are
    measured (screenshot + the sentence on screen) and only then banned, never assumed,
  * in Pallet the south crossing (map 0 -> the long water route, the "Route 21 to Cinnabar"
    the legs called sealed) is judged by the step itself, not by the grid,
  * the one body the mission names -- (9,8) on Route 4, in the pocket called sealed -- is
    approached from whatever side the world actually leaves open.

Usage:  uv run scripts/walk_toward_pallet.py [baton.state]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import rom_truth as rt  # noqa: E402
from expedition_rig import BattleWedge, Rig  # noqa: E402
from supervisor import LegRunner  # noqa: E402

BANK_DIR = SCRIPT_DIR.parent / "data" / "local_runs" / "roster-bench"
DEFAULT_BATON = str(BANK_DIR / "v8m10-15.state")
RUN_ID = "talk01"
PALETTOWN = 0
ROUTE4 = 15
SOUTH_WATER = 32  # the long route south of Pallet; the south side of "sealed"
WALL_BUDGET_S = 45 * 60


def log(*args) -> None:
    print(*args, flush=True)


class Mission:
    def __init__(self, rig: Rig) -> None:
        self.rig = rig
        self.heard: list[str] = []  # every runner sentence, in order
        self.moves: list[dict] = []  # every hop and its verdict
        self.refusals: list[dict] = []
        self.deadline = time.monotonic() + WALL_BUDGET_S

    def runner(self) -> LegRunner:
        collected = self.heard

        def sink(*args) -> None:
            line = " ".join(str(a) for a in args)
            log("  ", line)
            collected.append(line)

        return LegRunner(self.rig, goal=PALETTOWN, budget_s=300, log=sink)

    def spend(self) -> bool:
        if time.monotonic() > self.deadline:
            shot = self.rig.screenshot("wall-budget")
            self.rig.emit("wall_budget", pos=list(self.rig.pos()), screen=shot)
            log("wall budget spent; banking and stopping")
            self.rig.bank(f"{RUN_ID}-walled", directory=BANK_DIR)
            return True
        return False

    def engage_here(self, tag: str) -> None:
        """Ask every body the cartridge lists for this map what it will say. Measured, not assumed."""
        runner = self.runner()
        ok = runner.engage_bodies(("trainer", "npc"))
        self.rig.settle()
        log(f"[{tag}] engage -> {ok}")

    def to_map(self, dst: int, tag: str) -> bool:
        """Hop after hop until ``dst`` is under us. Refusals are measured before banned."""
        rig = self.rig
        banned: set[tuple[int, int]] = set()
        attempts: dict[tuple[int, int], int] = {}
        while rig.pos()[0] != dst:
            if self.spend():
                return False
            mp, x, y = rig.pos()
            chain = rt.route(rig.truth, mp, dst, banned=banned or None)
            if not chain:
                shot = rig.screenshot(f"no-route-{tag}-{mp}")
                rig.emit("no_route", mp=mp, dst=dst, banned=sorted(banned), screen=shot)
                rig.bank(f"{RUN_ID}-noroute", directory=BANK_DIR)
                log(f"no route left from map {mp}; banned={sorted(banned)}")
                return False
            hop = chain[0]
            log(f"[{tag}] at map {mp} ({x},{y}); the router says: " + " -> ".join(f"{h['to']}" for h in chain))
            self.engage_here(f"{tag}-map{mp}")
            mp, _x, _y = rig.pos()  # the engage may have walked; re-read
            if hop["via"] == "edge":
                res = rig.cross(mp, hop["to"])
            else:
                res = rig.warp(mp, hop["x"], hop["y"])
            now = rig.pos()
            if now[0] == hop["to"]:
                rig.settle()
                self.moves.append(
                    {"tag": tag, "from": mp, "to": hop["to"], "via": hop["via"], "res": str(res), "pos": list(now)}
                )
                log(f"  crossed {mp} -> {hop['to']} via {hop['via']} ({res})")
                continue
            key = (mp, hop["to"])
            attempts[key] = attempts.get(key, 0) + 1
            shot = rig.screenshot(f"refused-{tag}-{mp}-{hop['to']}-{attempts[key]}")
            said = (rig.textbox() or "").strip()
            self.rig.emit(
                "refusal",
                tag=tag,
                **{"from": mp, "to": hop["to"], "via": hop["via"], "res": str(res), "said": said[:300], "screen": shot},
            )
            log(f"  REFUSED {mp} -> {hop['to']} via {hop['via']} ({res}); game said: {said[:240]!r}; screen: {shot}")
            self.refusals.append(
                {"tag": tag, "from": mp, "to": hop["to"], "res": str(res), "said": said[:300], "screen": shot}
            )
            if attempts[key] >= 2:
                banned.add(key)
                log("  asking again would be guessing; that hop is banned and the router picks another way")
            rig.settle()
        return True


def main() -> int:
    baton = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BATON
    rig = Rig(baton, run_id=RUN_ID)
    mp, x, y = rig.pos()
    log(f"talk01 boots at map {mp} ({x},{y}); badges 0b{rig.badges():08b}")
    log(f"party {rig.party()}")
    rig.emit("talk_start", baton=baton, pos=list(rig.pos()), party=str(rig.party()))
    rig.screenshot("boot")

    m = Mission(rig)
    # Mission step 1: the bodies of THIS map get asked first. (9,8) is named in the mission --
    # whether the baton can even get there is a question the next lines answer.
    m.engage_here("route4-batons-map")
    rig.settle()

    # Mission step 2: Pallet. One engineered hop at a time, bodies engaged on every map in between.
    if not m.to_map(PALETTOWN, "to-pallet"):
        rig.finish(outcome="stuck", pos=str(rig.pos()), moves=str(m.moves), refusals=str(m.refusals))
        return 1
    rig.screenshot("pallet-arrived")
    rig.emit("pallet_arrived", pos=list(rig.pos()))
    m.engage_here("pallet")
    rig.settle()

    # Mission step 4 (out of the mission's own order, the road ends here): the south water. The
    # grid says the far shore has no floor; the mission says the picture is the witness.
    res32 = rig.cross(PALETTOWN, SOUTH_WATER)
    pos32 = rig.pos()
    south_open = pos32[0] == SOUTH_WATER
    if south_open:
        rig.screenshot("south-crossed")
        log(f"  SOUTH IS OPEN: across into map {SOUTH_WATER} at {pos32[1:]} ({res32})")
        back = rig.cross(SOUTH_WATER, PALETTOWN)
        log(f"  back to Pallet: {back} @ {rig.pos()}")
        rig.emit("south_verdict", open=True, res=str(res32), landed=list(pos32), back=str(back))
    else:
        shot = rig.screenshot("south-refused")
        said = (rig.textbox() or "").strip()
        rig.emit("south_verdict", open=False, res=str(res32), pos=list(pos32), said=said[:300], screen=shot)
        log(f"  SOUTH REFUSED: {res32}, still at {pos32}; game said: {said[:240]!r}; screen: {shot}")
        rig.settle()

    # Mission step 1, from the side the world actually leaves open: the (9,8) body sits in the
    # pocket the baton pocket cannot reach; the cave's north crossing is its other door.
    if not m.spend() and m.to_map(ROUTE4, "to-pocket"):
        rig.screenshot("route4-pocket")
        m.engage_here("route4-pocket")
        rig.screenshot("route4-final")

    rig.emit(
        "talk_done",
        pos=list(rig.pos()),
        party=str(rig.party()),
        moves=m.moves,
        refusals=m.refusals,
        north_open=bool(south_open),
    )
    rig.bank(f"{RUN_ID}-final", directory=BANK_DIR)
    rig.finish(
        outcome="done",
        pos=str(rig.pos()),
        party=str(rig.party()),
        moves=str(m.moves),
        refusals=str(m.refusals),
        south_open=bool(south_open),
    )
    print(
        __import__("json").dumps(
            {
                "pos": list(rig.pos()),
                "party": rig.party(),
                "moves": m.moves,
                "refusals_len": len(m.refusals),
                "south_open": south_open,
                "run_id": RUN_ID,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BattleWedge as exc:
        print(f"battle wedge: {exc}", flush=True)
        raise SystemExit(2)
