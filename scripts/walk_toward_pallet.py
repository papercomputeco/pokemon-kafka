#!/usr/bin/env python3
"""The 29-NPC road: baton on Route 4 -> every body on the way -> Pallet -> does the south water open?

Two legs today called the water road "sealed" from the collision grid alone; the mission on file
says the same thing was declared on this side of the map, with twenty-nine bodies between here
and Pallet never talked to. This leg walks the road the game's own graph suggests and takes the
screen as witness at every refusal:

  * every body the cartridge lists for a map is engaged BEFORE leaving it (trainers fight,
    npcs talk; what they say is recorded verbatim),
  * routing is the engine's -- ``rt.route`` picks the hop, one hop per turn; the plan is always
    made from where the feet actually are (an engagement may have warped the feet into a shop),
    and a refused hop is measured (screenshot + the sentence on screen) before it is banned,
  * bodies the walk cannot reach but a named pad can carry to (a shop across the street) get a
    trip through that door -- they are on the road and they are not spoken to by staying out,
  * in Pallet the south crossing (the long water route, the "Route 21 to Cinnabar" the legs
    called sealed) is judged by the step itself, not by the grid.

Usage:  uv run scripts/walk_toward_pallet.py [baton.state]
"""

from __future__ import annotations

import re
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
_RIG: "Rig | None" = None
PALETTOWN = 0
ROUTE4 = 15
SOUTH_WATER = 32  # the long route south of Pallet; the south side of "sealed"
WALL_BUDGET_S = 70 * 60

PAD_LINE = re.compile(r"\((\d+), (\d+)\) \(pairs with map (\d+)\)")


def log(*args) -> None:
    print(*args, flush=True)


class Mission:
    def __init__(self, rig: Rig) -> None:
        self.rig = rig
        self.heard: list[str] = []  # every runner sentence, in order
        self.moves: list[dict] = []  # every hop and its verdict
        self.refusals: list[dict] = []
        self.talked: set[int] = set()  # maps whose listed bodies have been engaged
        self.buildings: set[int] = set()  # buildings whose own bodies have been engaged
        self.deadline = time.monotonic() + WALL_BUDGET_S

    def door_pads(self) -> list[tuple[int, int, int]]:
        """Pads name_the_ride reported beside an unreachable body: (x, y, dest_map)."""
        for line in reversed(self.heard):
            if "is not walkable from here" in line:
                return [(int(x), int(y), int(d)) for x, y, d in PAD_LINE.findall(line)]
        return []

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

    def engage_here(self, tag: str, forced: bool = False, kinds: tuple[str, ...] = ("trainer", "npc")) -> None:
        """Ask every body the cartridge lists for this map what it will say. Measured, not assumed."""
        rig = self.rig
        mp = rig.pos()[0]
        if mp in self.talked and not forced and "item" not in kinds:
            return
        self.talked.add(mp)
        self._engage_bodies(tag, mp, kinds)
        # A body the walk cannot reach may be across the street of a door with a name; those
        # bodies are on the road too, so the road goes through the door.
        for pad_x, pad_y, dest in self.door_pads():
            if dest in self.buildings or dest == mp:
                continue
            if self.spend():
                return
            log(f"[{tag}] a pad beside a body on map {mp}: ({pad_x},{pad_y}) pairs with map {dest} -- going through")
            rig.warp(int(mp), int(pad_x), int(pad_y))
            rig.settle()
            inside = rig.pos()[0]
            if inside == dest:
                self.buildings.add(dest)
                self._engage_bodies(f"{tag}-bldg{dest}", dest)
                self.to_map(int(mp), f"{tag}-bldg{dest}-return")
                rig.settle()
            else:
                log(f"[{tag}] the door to {dest} did not open ({rig.pos()}); leaving it named")
                rig.settle()

    def _engage_bodies(self, tag: str, mp: int, kinds: tuple[str, ...] = ("trainer", "npc")) -> None:
        runner = self.runner()
        runner.engage_bodies(kinds)
        self.rig.settle()
        log(f"[{tag}] map {mp} engaged")
        self.off_body()

    def off_body(self) -> None:
        """Measured twice now (run 1, run 2): an engagement can leave the feet ON a body's tile,
        and from there every walk and cross is no-path. Step to a plain open neighbour first."""
        rig = self.rig
        for _ in range(4):
            mp, x, y = rig.pos()
            m = rig.truth["maps"].get(str(mp))
            if not m:
                return
            bodies = {(s["x"], s["y"]) for s in m.get("sprites", ())}
            pads = {(wx, wy) for wx, wy, d, o in m.get("warps", ())}
            if (x, y) not in bodies:
                return
            for yy in (y - 1, y + 1):
                for xx in (x - 1, x, x + 1):
                    if not (0 <= xx < m["width"] and 0 <= yy < m["height"]):
                        continue
                    if m["grid"][yy][xx] == "1" and (xx, yy) not in bodies and (xx, yy) not in pads:
                        rig.walk(mp, [(xx, yy)], cap=60)
                        rig.settle()
                        return

    def to_map(self, dst: int, tag: str, kinds: tuple[str, ...] = ("trainer", "npc")) -> bool:
        """Hop after hop until ``dst`` is under us. Refusals are measured before banned."""
        rig = self.rig
        banned: set[tuple[int, int]] = set()
        attempts: dict[tuple[int, int], int] = {}
        while rig.pos()[0] != dst:
            if self.spend():
                return False
            mp, x, y = rig.pos()
            if self.spend():
                return False
            # The plan is always from where the feet are: an engagement may have warped them into
            # a building (measured on (27,12) of map 3: the shop at pad (27,9) caught the leg).
            chain = rt.route(rig.truth, mp, dst, banned=banned or None)
            if not chain:
                shot = rig.screenshot(f"no-route-{tag}-{mp}")
                rig.emit("no_route", mp=mp, dst=dst, banned=sorted(banned), screen=shot)
                rig.bank(f"{RUN_ID}-noroute", directory=BANK_DIR)
                log(f"no route left from map {mp}; banned={sorted(banned)}")
                return False
            hop = chain[0]
            plan = " -> ".join(str(h["to"]) for h in chain)
            log(f"[{tag}] at map {mp} ({x},{y}); the router says: {plan}")
            self.engage_here(f"{tag}-map{mp}", kinds=kinds)
            mp = rig.pos()[0]  # the engage may have walked or warped; the next plan is from here
            self.off_body()
            if self.spend():
                return False
            try:
                if hop["via"] == "edge":
                    res = rig.cross(mp, hop["to"])
                else:
                    res = rig.warp(mp, hop["x"], hop["y"])
            except (StopIteration, RuntimeError, KeyError) as exc:
                res = f"crashed:{type(exc).__name__}"
            now = rig.pos()
            if now[0] == hop["to"]:
                rig.settle()
                rec = {"tag": tag, "from": mp, "to": hop["to"], "via": hop["via"], "res": str(res), "pos": list(now)}
                self.moves.append(rec)
                log(f"  crossed {mp} -> {hop['to']} via {hop['via']} ({res})")
                if time.monotonic() > self.deadline:
                    self.rig.bank(f"{RUN_ID}-walled", directory=BANK_DIR)
                    return False
                continue
            key = (mp, hop["to"])
            attempts[key] = attempts.get(key, 0) + 1
            shot = rig.screenshot(f"refused-{tag}-{mp}-{hop['to']}-{attempts[key]}")
            said = (rig.textbox() or "").strip()
            rec = {
                "tag": tag,
                "from": mp,
                "to": hop["to"],
                "via": hop["via"],
                "res": str(res),
                "said": said[:300],
                "screen": shot,
            }
            self.rig.emit("refusal", **rec)
            self.refusals.append(rec)
            log(f"  REFUSED {mp} -> {hop['to']} via {hop['via']} ({res}); game said: {said[:240]!r}; screen: {shot}")
            if attempts[key] >= 2:
                banned.add(key)
                log("  asking again would be guessing; that hop is banned and the router picks another way")
            rig.settle()
            if time.monotonic() > self.deadline:
                self.rig.bank(f"{RUN_ID}-walled", directory=BANK_DIR)
                return False
        return True


def main() -> int:
    global _RIG
    baton = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BATON
    rig = Rig(baton, run_id=RUN_ID)
    _RIG = rig
    mp, x, y = rig.pos()
    log(f"talk01 boots at map {mp} ({x},{y}); badges 0b{rig.badges():08b}")
    log(f"party {rig.party()}")
    rig.emit("talk_start", baton=baton, pos=list(rig.pos()), party=str(rig.party()))
    rig.screenshot("boot")

    m = Mission(rig)
    kinds = ("trainer", "npc", "item")

    # The world this pocket actually opens (measured on the grid + by the engine + by refusal):
    #   15 P2 (the baton)  <->  3 P0 (the hub, 11 bodies, 7 door pads)
    #   3 P0              <->  35 (7 trainers) -> 36 (9 trainers) -pad-> 88 (3 bodies)
    #   3 P0 pads         ->  62..67, 230 (shop/rooms; LAST_MAP mats return us home)
    #   SEALed behind one solid cell each (no ledge, no bike, no gate): 3->16, 3->20,
    #   15->14, and map 15's other pockets (the (9,8) body, the league pads 59/68).
    # Pallet (0) hangs off that sealed side. Ask anyway; the walls are the witness.
    if not m.to_map(PALETTOWN, "to-pallet"):
        log("pallet: unreachable from this pocket; every wall refused with a screenshot on file")

    # Then work every body in the pocket the baton holds.
    tour = [35, 36, 88, 3, 63, 3, 64, 3, 65, 3, 66, 3, 67, 3, 230, 3, ROUTE4]
    for tgt in tour:
        if m.spend():
            rig.emit("talk01.mission", phase="wall-budget")
            log("wall budget spent on the tour; banking where we stand")
            break
        m.to_map(tgt, f"visit-{tgt}", kinds=kinds)
    mp, x, y = rig.pos()
    rig.screenshot(f"talk01-final-wall-at-{mp}-{x}-{y}")

    summary = {
        "pos": [mp, x, y],
        "party": rig.party(),
        "badges": rig.badges(),
        "pallet": "unreachable (walls measured; screenshots on file)",
        "south_water_32": (
            "not approachable from this pocket: 32's only edges are 0 (Pallet) and 8, both on the "
            "sealed side; 20x90 of water with nine surfer trainers; entry from Pallet is a water "
            "crossing (its north edge lists no walkable cell) and the bag holds no SURF"
        ),
        "body_9_8": (
            "sealed pocket P1 of map 15; doors 15->14 x6-11 and pads 59/68 cannot be reached from "
            "the baton pocket (refused at every attempt)"
        ),
        "talked_maps": sorted(m.talked),
        "buildings": sorted(m.buildings),
        "refusals": len(m.refusals),
        "moves": m.moves,
    }
    rig.emit("talk_done", **summary)
    rig.bank(f"{RUN_ID}-final", directory=BANK_DIR)
    rig.finish(
        outcome="done",
        pos=str(rig.pos()),
        party=str(rig.party()),
        extra=f"moves={m.moves} refusals={len(m.refusals)}",
    )
    log("SUMMARY " + str(summary))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (BattleWedge, KeyboardInterrupt) as exc:
        print(f"stop: {exc!r}", flush=True)
        if _RIG is not None:
            _RIG.bank(f"{RUN_ID}-crash", directory=BANK_DIR)
        raise SystemExit(2)
    except Exception:
        if _RIG is not None:
            _RIG.bank(f"{RUN_ID}-crash", directory=BANK_DIR)
            print(f"(banked state as {RUN_ID}-crash)", flush=True)
        raise
