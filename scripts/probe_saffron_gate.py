"""Measure the Saffron-side gate (map 70, the Route 6 gate house) across banked saves.

Lane 33 (2026-09-07) walked into its guard eight times from a 2-badge save: "I on guard duty. Gee,
I thi..." and a refused step. The sentence is measured; what clears it is not. This probe boots
each named baton, walks toward Saffron (map 10) through that gate with no model seated, and
records: badges and bag before, whether the gate passed, every refusal sentence the game
printed, the bag after (an item consumed is a clear), and what the guard says when talked to.
The clear is whatever differs between the last refused save and the first passed one.

    uv run python scripts/probe_saffron_gate.py captain_done badge3 badge4 b5_celadon BADGE5
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from expedition_rig import Rig  # noqa: E402
from supervisor import LegRunner  # noqa: E402

GATE_HOUSE = 70
SAFFRON = 10
VERMILION = 5
NO_CONSULT = lambda tier, facts, menu: (None, "consults disabled", "none")  # noqa: E731


def probe(name: str, deposit: str | None = None) -> dict:
    rig = Rig(f"data/local_runs/roster-bench/{name}.state", live_label=f"probe saffron gate — {name}")
    out = {"baton": name, "start": list(rig.pos()), "badges": f"0b{rig.badges():08b}", "bag_before": rig.bag_named()}
    quiet = lambda *a: None  # noqa: E731
    # Capture what every talk returned: _what_it_said reads a buffer the talk has already consumed.
    talks: list[str] = []
    real_talk = rig.talk
    rig.talk = lambda face: talks.append(real_talk(face)) or talks[-1]  # type: ignore[method-assign]
    if deposit:
        # Bank the named item at the nearest Center's PC first: if the gate still passes without it
        # in the bag, the clear is state on the lineage, not the item in hand.
        here = rig.pos()[0]
        centers = [w[2] for w in rig.truth["maps"].get(str(here), {}).get("warps", []) if rig.center_counter(w[2])]
        if centers:
            LegRunner(rig, goal=centers[0], budget_s=240, consult=NO_CONSULT, log=quiet).run()
        out["deposited"] = bool(rig.pc_store_item(deposit)) if rig.center_pc(rig.pos()[0]) else "no-center"
        out["bag_after_deposit"] = rig.bag_named()
    if rig.pos()[0] not in (VERMILION, 19, GATE_HOUSE):
        # Approach from Vermilion so every save meets the same gate; a save that cannot get
        # there walks at Saffron from where it stands and meets whichever gate house is on the way.
        first = LegRunner(rig, goal=VERMILION, budget_s=420, consult=NO_CONSULT, log=quiet).run()
        out["to_vermilion"] = first.get("outcome")
    runner = LegRunner(rig, goal=SAFFRON, budget_s=360, consult=NO_CONSULT, log=quiet)
    result = runner.run()
    out["outcome"] = result.get("outcome")
    out["pos"] = list(rig.pos())
    out["refusals"] = result.get("gates") or {}
    out["passed"] = rig.pos()[0] == SAFFRON or result.get("ok", False)
    out["bag_after"] = rig.bag_named()
    before = {n for n, _ in out["bag_before"]}
    after = {n for n, _ in out["bag_after"]}
    out["bag_lost"] = sorted(before - after)
    out["bag_gained"] = sorted(after - before)
    # What the guard says when spoken to: in the house the refusal left us in, or — after a pass —
    # back in the Route 6 gate house so the open gate's guard is heard too.
    if out["passed"]:
        LegRunner(rig, goal=GATE_HOUSE, budget_s=240, consult=NO_CONSULT, log=quiet).run()
    house = rig.pos()[0]
    if house != SAFFRON:
        heard = {}
        for s in rig.truth["maps"].get(str(house), {}).get("sprites", []):
            spot = (s["x"], s["y"])
            if s.get("kind") in ("trainer", "npc") and runner._go_and_talk(spot):
                heard[f"{house}:{spot}"] = talks[-1] if talks else ""
        out["guard_says"] = heard
        out["bag_after_talk"] = rig.bag_named()
    rig.finish(outcome=f"probe saffron gate: {'passed' if out['passed'] else 'refused'}")
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    deposit = None
    if args and args[0] == "--deposit":
        deposit, args = args[1], args[2:]
    for baton in args:
        try:
            row = probe(baton, deposit)
        except Exception as exc:  # noqa: BLE001 — one bad baton must not end the sweep
            row = {"baton": baton, "error": repr(exc)}
        print(json.dumps(row), flush=True)
