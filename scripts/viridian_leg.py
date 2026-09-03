#!/usr/bin/env python3
"""Badge-8 leg — Cerulean (66) -> street (3) -> 15 -> 14 -> 2 -> 13 -> 1 -> gym (45).

The chain is the engine's own: ``rom_truth.route(truth, 66, 45)`` on THIS cartridge gives
[3, 15, 14, 2, 13, 1, 45], and map 1's fifth warp is (32, 7) -> 45. Every hop is a measured
map connection, not a recalled geography fact; nothing here is a map name. The leg is driven
hop by hop (the supervisor's crew ladder is not needed for a known chain), each milestone is
banked so the next invocation resumes from the latest baton, and the gym finishes by meeting
every trainer the cartridge lists for map 45 and reading the BADGES byte before and after.

Usage:  uv run python scripts/viridian_leg.py [state-file]
        (defaults to data/local_runs/roster-bench/bicycle.state)
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from expedition_rig import BattleWedge, Rig  # noqa: E402

BANK_DIR = SCRIPT_DIR.parent / "data" / "local_runs" / "roster-bench"


def log(*args) -> None:
    print(*args, flush=True)


def bank(rig: Rig, name: str) -> Path:
    p = rig.bank(name, directory=BANK_DIR)
    log(f"banked {p.name} @ {rig.pos()} badges={rig.badges()}")
    return p


def hop(rig: Rig, a: int, b: int) -> str:
    """One measured edge connection, logged and emitted."""
    log(f"-- cross {a} -> {b} from {rig.pos()}")
    r = rig.cross(a, b)
    log(f"-- cross {a} -> {b}: {r!r} now {rig.pos()}")
    rig.emit("leg.hop", a=a, b=b, result=str(r), pos=list(rig.pos()))
    return str(r)


def go_and_talk(rig: Rig, spot: tuple[int, int]) -> tuple[bool, str]:
    """Walk to a cell beside ``spot``, face it, talk; battles resolve inside."""
    import road

    mp = rig.pos()[0]
    bx, by = spot
    adjacent = {(bx + 1, by), (bx - 1, by), (bx, by + 1), (bx, by - 1)}
    near = road.reachable(rig.truth, rig.pairs, mp, rig.pos()[1:], rig.bodies()) & adjacent
    if not near:
        return False, ""
    r = rig.walk(mp, near, cap=400)
    if rig.pos()[0] != mp:
        return False, f"map-change:{rig.pos()[0]}"
    if rig.pos()[1:] not in adjacent:
        return False, str(r)
    _, x, y = rig.pos()
    face = "right" if bx > x else "left" if bx < x else "down" if by > y else "up"
    said = rig.talk(face)
    return True, said


def main() -> int:
    started = sys.argv[1] if len(sys.argv) > 1 else str(BANK_DIR / "bicycle.state")
    rig = Rig(started, run_id="badge8-20260903")
    mp0, x0, y0 = rig.pos()
    log(f"== badge-8 leg from ({mp0},{x0},{y0}) party={rig.party()} badges={rig.badges()} bag={rig.bag()}")
    rig.emit(
        "leg.open",
        from_state=str(started),
        pos=list(rig.pos()),
        party=str(rig.party()),
        badges=rig.badges(),
        bag=str(rig.bag()),
    )

    def ensure(mp: int, label: str) -> bool:
        if rig.pos()[0] == mp and not (BANK_DIR / f"{label}.state").exists():
            bank(rig, label)
            rig.emit("leg.milestone", m=label, pos=list(rig.pos()), badges=rig.badges())
        return rig.pos()[0] == mp

    try:
        # 1) bike shop (66) -> the street (3): the two door mats are LAST_MAP, and last map is 3.
        if rig.pos()[0] == 66:
            hop_out = rig.warp(66, 3, 7)
            log("shop door (3,7):", hop_out, rig.pos())
            if rig.pos()[0] != 3:
                hop_out = rig.warp(66, 2, 7)
                log("shop door (2,7):", hop_out, rig.pos())
            rig.emit("leg.hop", a=66, b=3, result=str(hop_out), pos=list(rig.pos()))
            ensure(3, "m1_cerulean")

        # 2) street (3) -> route map 15: one measured west-east connection; the sweep finds
        #    whichever boundary row the cartridge actually maps across.
        if rig.pos()[0] == 3:
            r = hop(rig, 3, 15)
            if rig.pos()[0] != 15:
                log(f"first cross failed ({r}); stepping into the refusal to read it")
                rig.io.press("left", hold=8, release=8)
                rig.io.wait(40)
                said = rig.dialogue()
                log(f'  the game says: "{said}"')
                rig.emit("leg.refusal", a=3, b=15, said=said, pos=list(rig.pos()))
            ensure(15, "m2_route4")

        # 3) map 15 -> map 14 (the south edge).
        if rig.pos()[0] == 15:
            r = hop(rig, 15, 14)
            if rig.pos()[0] != 14:
                rig.io.press("down", hold=8, release=8)
                rig.io.wait(40)
                said = rig.dialogue()
                log(f"15->14 failed ({r}); the game says: {said!r}")
                rig.emit("leg.refusal", a=15, b=14, result=r, said=said, pos=list(rig.pos()))
            ensure(14, "m3_route3")

        # 4) map 14 -> map 2 (west edge; trainers on the way are fought by the handler).
        if rig.pos()[0] == 14:
            r = hop(rig, 14, 2)
            rig.emit("leg.hop", a=14, b=2, result=str(r), pos=list(rig.pos()))
            ensure(2, "m4_pewter")

        # 5) map 2 -> map 13 (south edge).
        if rig.pos()[0] == 2:
            r = hop(rig, 2, 13)
            rig.emit("leg.hop", a=2, b=13, result=str(r), pos=list(rig.pos()))
            ensure(13, "m5_route1")

        # 6) map 13 -> map 1 (north edge).
        if rig.pos()[0] == 13:
            r = hop(rig, 13, 1)
            rig.emit("leg.hop", a=13, b=1, result=str(r), pos=list(rig.pos()))
            ensure(1, "m6_viridian")

        # 7) map 1 -> the gym (45): warp (32, 7) is the fifth of map 1's warps in this ROM.
        if rig.pos()[0] == 1:
            r = rig.warp(1, 32, 7)
            log("gym door (32,7):", r, rig.pos())
            rig.emit("leg.hop", a=1, b=45, result=str(r), pos=list(rig.pos()))
            ensure(45, "m7_gym")

        # 8) the gym: meet every trainer the cartridge lists, watch the BADGES byte.
        if rig.pos()[0] == 45:
            m = rig.truth["maps"]["45"]
            trainers = [(s["x"], s["y"]) for s in m.get("sprites", []) if s["kind"] == "trainer"]
            log(f"gym trainers: {trainers}")
            badges_before = rig.badges()
            for spot in trainers:
                ok, said = go_and_talk(rig, spot)
                log(f"met {spot}: {ok} badges={rig.badges()} said={said[:110]!r}")
                rig.emit("leg.gym_body", spot=list(spot), reached=ok, badges=rig.badges(), said=said[:300])
                if rig.badges() != badges_before:
                    log("!! badge bit moved")
                    break
            badges_after = rig.badges()
            log(f"BADGES byte: {badges_before} -> {badges_after}")
            rig.emit(
                "leg.gym_done",
                badges_before=badges_before,
                badges_after=badges_after,
                party=str(rig.party()),
                pos=list(rig.pos()),
            )
            if rig.bag_full() is False:
                for s in m.get("sprites", []):
                    if s.get("kind") == "item":
                        log(f"item ball at {s['x']},{s['y']} (item {s.get('item')})")
                        rig.walk(45, {(s["x"], s["y"])}, cap=200)
                        log("after ball walk:", rig.pos(), "bag:", rig.bag())
                        break
            ok8 = badges_after > badges_before
            bank(rig, "badge8" if ok8 else "gym-fought")
            rig.emit("leg.close", badge_gained=ok8, badges=badges_after, pos=list(rig.pos()))
            log(f"== badge-8 leg finished: badge {'GAINED' if ok8 else 'NOT YET'} {rig.pos()}")
            return 0 if ok8 else 2

        log(f"== stopped on map {rig.pos()[0]} without finishing; latest bank is the baton")
        return 1
    except BattleWedge as e:
        log(f"BATTLE WEDGE: {e}")
        rig.emit("leg.wedge", err=str(e), pos=list(rig.pos()))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
