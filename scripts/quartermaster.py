#!/usr/bin/env python3
"""Quartermaster — marts, healing, and capture: the roster engine's first pieces.

The road past Misty needs what the solo Charmeleon lane has never had: supplies and teammates
(benchmarks/2026-08-25-router-cerulean.md postscript; the Elite Four makes it non-optional).
This module adds them in two shapes:

* An **errand** is a baton transformer: load a save state, run one self-contained job — walk to
  the mart and buy the shopping list, walk to the Center and heal — and save the state back.
  Errands run BETWEEN legs (`errand` CLI below), so relay segments stay pure navigation/battle
  and a lane never has to learn shopping mid-mission. Every menu phase is RAM-verified, never
  blind-timed: the 2026-08-26 mart probe showed the shop dialog cadence swallowing fixed-timing
  scripts (a purchase "confirmed" two A-presses before the money actually moved) — so each phase
  repeats its press until its own predicate flips (menu registers, money delta, bag delta), with
  a strike cap.

* **Catch policy** is a pair of pure functions the agent's battle turn consults: a wild battle
  against a wanted, weakened species with a ball in the bag becomes ``{"action": "item"}`` on the
  ball's bag slot — the exact menu path the potion action already drives.

    uv run python scripts/quartermaster.py errand --state in.state --out out.state \
        --buy poke_ball=6,potion=4 --heal            # supplies + full HP, one command

RAM signals (Red/Blue US): menu cursor/extent 0xCC26/0xCC28, text box id 0xD125 (14 = shop
BUY/SELL/QUIT, 13 = the scrolling item list), money BCD at 0xD347, bag at 0xD31D, party structs
(44 bytes) at 0xD16B — all verified live in the mart probe.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent

ADDR_MAP, ADDR_Y, ADDR_X = 0xD35E, 0xD361, 0xD362
ADDR_IN_BATTLE = 0xD057
ADDR_MENU_CUR, ADDR_MENU_MAX, ADDR_TEXT_ID = 0xCC26, 0xCC28, 0xD125
ADDR_MONEY = 0xD347  # 3 BCD bytes
ADDR_BAG_COUNT, ADDR_BAG_ITEMS = 0xD31D, 0xD31E
ADDR_PARTY_COUNT, ADDR_PARTY_STRUCTS = 0xD163, 0xD16B
PARTY_STRUCT_SIZE = 44

TEXT_SHOP_MENU, TEXT_ITEM_LIST = 14, 13

# Item ids (pokered constants). POKE_BALL=4 verified live (the probe's purchase landed as (4, 4)).
MASTER_BALL, ULTRA_BALL, GREAT_BALL, POKE_BALL = 1, 2, 3, 4
POTION, SUPER_POTION = 0x14, 0x13
BALL_IDS = (POKE_BALL, GREAT_BALL, ULTRA_BALL, MASTER_BALL)  # cheapest first: spend plain balls first
PRICES = {POKE_BALL: 200, POTION: 300, SUPER_POTION: 700}
ITEM_NAMES = {POKE_BALL: "poke_ball", GREAT_BALL: "great_ball", POTION: "potion", SUPER_POTION: "super_potion"}
NAME_TO_ITEM = {v: k for k, v in ITEM_NAMES.items()}


@dataclass(frozen=True)
class Shop:
    """One mart: where its door is in the city, where to stand and face inside, what it sells
    (menu order — the cursor index IS the stock index)."""

    city_map: int
    door_xy: tuple[int, int]
    interior_map: int
    counter_xy: tuple[int, int]
    face: str
    stock: tuple[int, ...]
    exit_xy: tuple[int, int]


@dataclass(frozen=True)
class Center:
    city_map: int
    door_xy: tuple[int, int]
    interior_map: int
    counter_xy: tuple[int, int]
    face: str
    exit_xy: tuple[int, int]


# Verified live 2026-08-26 (mart probe): door (25,25) lands at (3,7); the clerk is talked to from
# (2,5) facing left; stock order Poke Ball, Potion, ... (indexes past 1 unpurchased so far).
SHOPS = {
    3: Shop(3, (25, 25), 67, (2, 5), "left", (POKE_BALL, POTION), (3, 7)),
}
# Cerulean Center: door (19,17) in the city; the nurse (3,1) is talked to across the counter
# from (3,3) facing up — the same geometry as Pewter's flow.
CENTERS = {
    3: Center(3, (19, 17), 64, (3, 3), "up", (3, 7)),
}


class QuartermasterError(RuntimeError):
    """An errand phase exhausted its strike cap — the state is saved as-is for diagnosis."""


# --------------------------------------------------------------------------- io + readers


class EmuIO:
    """Thin PyBoy adapter — everything the errands touch, mockable in tests."""

    def __init__(self, pyboy):
        self.pyboy = pyboy

    def press(self, btn: str, hold: int = 8, release: int = 8) -> None:
        self.pyboy.button_press(btn)
        for _ in range(hold):
            self.pyboy.tick()
        self.pyboy.button_release(btn)
        for _ in range(release):
            self.pyboy.tick()

    def wait(self, frames: int = 30) -> None:
        for _ in range(frames):
            self.pyboy.tick()

    def read(self, addr: int) -> int:
        return self.pyboy.memory[addr]


def read_pos(io) -> tuple[int, int, int]:
    return io.read(ADDR_MAP), io.read(ADDR_X), io.read(ADDR_Y)


def read_money(io) -> int:
    return int("".join(f"{io.read(ADDR_MONEY + k):02x}" for k in range(3)))


def read_bag(io) -> list[tuple[int, int]]:
    n = io.read(ADDR_BAG_COUNT)
    return [(io.read(ADDR_BAG_ITEMS + 2 * i), io.read(ADDR_BAG_ITEMS + 2 * i + 1)) for i in range(n)]


def read_party(io) -> list[dict]:
    out = []
    for i in range(io.read(ADDR_PARTY_COUNT)):
        base = ADDR_PARTY_STRUCTS + PARTY_STRUCT_SIZE * i
        out.append(
            {
                "species": io.read(base),
                "hp": (io.read(base + 1) << 8) | io.read(base + 2),
                "level": io.read(base + 33),
                "max_hp": (io.read(base + 34) << 8) | io.read(base + 35),
            }
        )
    return out


def menu_state(io) -> tuple[int, int, int]:
    return io.read(ADDR_MENU_CUR), io.read(ADDR_MENU_MAX), io.read(ADDR_TEXT_ID)


# --------------------------------------------------------------------------- pure policy


def plan_purchases(money: int, bag: list[tuple[int, int]], balls: int = 6, potions: int = 4, reserve: int = 100):
    """What to buy to reach the targets, affordably, reserve kept. ``[(item_id, qty)]``.

    Balls before potions: a missed catch window costs a roster slot forever; a missing potion
    costs a Center trip."""
    have = {}
    for item, qty in bag:
        have[item] = have.get(item, 0) + qty
    have_balls = sum(have.get(b, 0) for b in BALL_IDS)
    wants = [(POKE_BALL, max(0, balls - have_balls)), (POTION, max(0, potions - have.get(POTION, 0)))]
    plan = []
    budget = money - reserve
    for item, qty in wants:
        price = PRICES[item]
        afford = max(0, min(qty, budget // price))
        if afford:
            plan.append((item, afford))
            budget -= afford * price
    return plan


def parse_catch(spec: str) -> set[int]:
    """``"Oddish,Spearow"`` (or raw internal ids) -> the species-id set for ``should_catch``."""
    from memory_reader import SPECIES_ID_MAP

    inv = {v.lower(): k for k, v in SPECIES_ID_MAP.items()}
    out: set[int] = set()
    for part in filter(None, (p.strip() for p in spec.split(","))):
        if part.lower() in inv:
            out.add(inv[part.lower()])
        elif part.isdigit():
            out.add(int(part))
        else:
            raise SystemExit(f"unknown species {part!r} — add it to memory_reader.SPECIES_ID_MAP")
    return out


def find_ball(bag: list[tuple[int, int]]) -> tuple[int, int] | None:
    """(bag index, item id) of the cheapest ball in the bag, or None."""
    for ball in BALL_IDS:
        for i, (item, qty) in enumerate(bag):
            if item == ball and qty > 0:
                return i, item
    return None


def should_catch(
    battle,
    party_species: list[int],
    bag: list[tuple[int, int]],
    wanted: set[int],
    hp_ratio_max: float = 1.0,
) -> tuple[int, int] | None:
    """(bag index, ball id) when this wild is worth a ball right now, else None.

    Worth it = wild battle, a species on the wanted list that the party lacks, room in the
    party, the enemy at or under the throw threshold, and a ball to throw. The default throws
    IMMEDIATELY: an over-leveled lead KOs an early-route wild before any weaken window opens
    (the first probe fought its only encounter to death), and every wanted species out here has
    a 200+ catch rate, where a full-HP Poke Ball throw usually lands. Lower the threshold when
    hunting genuinely hard catches — weakening logic is that day's work, not this one's."""
    if getattr(battle, "battle_type", 0) != 1:
        return None
    if battle.enemy_species not in wanted or battle.enemy_species in party_species:
        return None
    if len(party_species) >= 6:
        return None
    if battle.enemy_hp > max(1, battle.enemy_max_hp) * hp_ratio_max:
        return None
    return find_ball(bag)


# --------------------------------------------------------------------------- verified driving


def settle(io, predicate, action, cap: int, label: str):
    """Repeat ``action`` until ``predicate()`` holds — the probe's lesson institutionalized:
    dialogs advance on their own cadence, so every phase is verified, never timed."""
    for _ in range(cap):
        if predicate():
            return
        action()
        io.wait(30)
    raise QuartermasterError(f"{label}: no progress after {cap} attempts")


def flee_battle(io, cap: int = 25) -> None:
    """Run from a wild encounter that interrupted an errand walk. Errands don't fight — battles
    belong to the agent's strategy; an errand's only battle move is leaving. The 2x2 battle menu
    is normalized to FIGHT (up+left) then walked to RUN (down, right), the same grid the agent's
    menu driver uses; a failed escape just repeats until the flag clears."""
    for _ in range(cap):
        if not io.read(ADDR_IN_BATTLE):
            io.wait(30)
            return
        for btn in ("b", "up", "left", "down", "right", "a"):
            io.press(btn)
            io.wait(10)
        io.wait(90)
        io.press("b")
        io.wait(30)
    raise QuartermasterError(f"flee: still in battle after {cap} attempts")


def walk_to(io, truth, pairs, map_id: int, target: tuple[int, int], cap: int = 400) -> None:
    """Truth-planned walk on ``map_id`` to ``target`` (or off it, via a warp). Each step is
    position-verified; the first press after a turn only rotates, so a stalled press retries —
    and a step that STAYS stalled presses B first: a lingering menu or dialog eats d-pad input
    silently (``wTextBoxID`` reads stale after a menu closes, so it cannot be trusted as a
    "menus are gone" signal — the position is the only honest detector)."""
    import rom_truth as rt

    def moved(before) -> bool:
        # Poll until the position settles instead of reading once: a LEDGE hop's animation
        # outlasts a fixed wait, and a stale read here caused a blind re-press that queued an
        # extra step and walked the lane off-plan into a one-way pocket (2026-08-26 probe).
        for _ in range(10):
            io.wait(8)
            if read_pos(io) != before:
                io.wait(30)  # finish the animation before the next plan reads position
                return True
        return False

    stalled = 0
    for _ in range(cap):
        if io.read(ADDR_IN_BATTLE):
            flee_battle(io)
            continue
        mp, x, y = read_pos(io)
        if mp != map_id or (x, y) == target:
            io.wait(60)  # let a warp transition finish before the caller reads position
            return
        if stalled:
            io.press("b")
            io.wait(12)
        path = rt.path_on_map(truth, pairs, map_id, (x, y), {target}, blocked=rt.sprite_tiles(truth, map_id))
        if not path or len(path) < 2:
            raise QuartermasterError(f"walk: no path on map {map_id} from {(x, y)} to {target}")
        (x0, y0), (x1, y1) = path[0], path[1]
        d = "right" if x1 > x0 else "left" if x1 < x0 else "down" if y1 > y0 else "up"
        io.press(d)
        ok = moved((mp, x, y))
        if not ok:
            io.press(d)  # the first press against a new facing only turns in place
            ok = moved((mp, x, y))
        stalled = 0 if ok else stalled + 1
        if stalled > 12:
            raise QuartermasterError(f"walk: wedged at {(x, y)} on map {map_id} heading {d}")
    raise QuartermasterError(f"walk: {cap} steps without reaching {target} on map {map_id}")


def leave_interior(io, interior_map: int) -> None:
    """From the exit mat, walk out: interior door mats sit on the bottom row and hand the player
    over on the step DOWN off them — standing on the mat is not outside (the same lesson as edge
    hops: arriving on the exit tile is not arriving)."""
    for _ in range(6):
        if read_pos(io)[0] != interior_map:
            io.wait(60)
            return
        io.press("down")
        io.wait(30)
    raise QuartermasterError(f"exit: still on map {interior_map} after 6 steps down from the mat")


def buy(io, shop: Shop, plan: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Execute the purchase plan at an open counter. Returns [(item, qty)] actually bought.

    Assumes the player stands at ``shop.counter_xy``; opens the shop menu itself."""
    io.press(shop.face)
    io.wait(12)
    settle(
        io,
        lambda: menu_state(io)[1:] == (2, TEXT_SHOP_MENU),
        lambda: io.press("a"),
        cap=10,
        label="open shop menu",
    )
    bought = []
    for item, qty in plan:
        idx = shop.stock.index(item)
        money_before, bag_before = read_money(io), dict(read_bag(io))
        io.press("a")  # BUY
        settle(io, lambda: menu_state(io)[2] == TEXT_ITEM_LIST, lambda: io.press("a"), cap=6, label="item list")
        # Cursor to the stock index, verified against the live cursor register.
        for _ in range(12):
            cur = io.read(ADDR_MENU_CUR)
            if cur == idx:
                break
            io.press("down" if cur < idx else "up")
            io.wait(8)
        io.press("a")  # item -> quantity selector
        io.wait(30)
        for _ in range(qty - 1):
            io.press("up")
            io.wait(8)
        io.press("a")  # quantity -> "that'll be N. okay?"
        settle(
            io,
            lambda: read_money(io) < money_before,
            lambda: io.press("a"),
            cap=8,
            label=f"confirm purchase of item {item}",
        )
        gained = dict(read_bag(io)).get(item, 0) - bag_before.get(item, 0)
        bought.append((item, gained))
        io.press("b")  # back to the item list edge cases; harmless if already there
        io.wait(20)
    # Leave the menus entirely: B until the shop menu itself is gone.
    for _ in range(6):
        if menu_state(io)[2] not in (TEXT_SHOP_MENU, TEXT_ITEM_LIST):
            break
        io.press("b")
        io.wait(20)
    return bought


def heal(io, center: Center) -> None:
    """Talk to the nurse and A through the heal until the whole party reads full."""

    def healed() -> bool:
        party = read_party(io)
        return bool(party) and all(p["hp"] == p["max_hp"] for p in party)

    io.press(center.face)
    io.wait(12)
    settle(io, healed, lambda: io.press("a"), cap=30, label="nurse heal")
    # Dismiss the trailing "we hope to see you again" text.
    for _ in range(4):
        io.press("b")
        io.wait(20)


# --------------------------------------------------------------------------- errands


def run_errand(io, truth, buy_plan: list[tuple[int, int]] | None, do_heal: bool) -> dict:
    """From anywhere in a known city: mart errand (if a plan), then Center errand (if asked).
    Returns a report dict; raises QuartermasterError when a phase caps out."""
    import rom_truth as rt

    pairs = rt.loaded_pairs(truth)
    mp, _, _ = read_pos(io)
    report: dict = {"city": mp, "bought": [], "healed": False}
    if buy_plan:
        shop = SHOPS.get(mp)
        if shop is None:
            raise QuartermasterError(f"no known mart in city map {mp}")
        walk_to(io, truth, pairs, shop.city_map, shop.door_xy)
        walk_to(io, truth, pairs, shop.interior_map, shop.counter_xy)
        report["bought"] = buy(io, shop, buy_plan)
        walk_to(io, truth, pairs, shop.interior_map, shop.exit_xy)
        leave_interior(io, shop.interior_map)
    if do_heal:
        center = CENTERS.get(read_pos(io)[0])
        if center is None:
            raise QuartermasterError(f"no known center in city map {read_pos(io)[0]}")
        walk_to(io, truth, pairs, center.city_map, center.door_xy)
        walk_to(io, truth, pairs, center.interior_map, center.counter_xy)
        heal(io, center)
        report["healed"] = True
        walk_to(io, truth, pairs, center.interior_map, center.exit_xy)
        leave_interior(io, center.interior_map)
    report["money"] = read_money(io)
    report["bag"] = read_bag(io)
    report["party"] = read_party(io)
    return report


# --------------------------------------------------------------------------- cli


def parse_buy(spec: str) -> list[tuple[int, int]]:
    """ "poke_ball=6,potion=4" -> [(4, 6), (20, 4)]; unknown names refuse loudly."""
    plan = []
    for part in filter(None, spec.split(",")):
        name, _, qty = part.partition("=")
        if name not in NAME_TO_ITEM:
            raise SystemExit(f"unknown item {name!r} (choose from {', '.join(sorted(NAME_TO_ITEM))})")
        plan.append((NAME_TO_ITEM[name], int(qty or 1)))
    return plan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    er = sub.add_parser("errand", help="mart and/or heal, state in -> state out")
    er.add_argument("--rom", type=Path, default=WORKSPACE / "rom" / "pokemon_red.gb")
    er.add_argument("--state", type=Path, required=True)
    er.add_argument("--out", type=Path, required=True)
    er.add_argument("--buy", default="", help="e.g. poke_ball=6,potion=4 (capped by money and plan_purchases)")
    er.add_argument("--heal", action="store_true")
    er.add_argument("--reserve", type=int, default=100)
    args = ap.parse_args(argv)

    import rom_truth as rt
    from pyboy import PyBoy

    pb = PyBoy(str(args.rom), window="null")
    with open(args.state, "rb") as f:
        pb.load_state(f)
    io = EmuIO(pb)
    truth = rt.load_truth()
    requested = parse_buy(args.buy)
    plan = []
    if requested:
        # The request states the TARGETS; the planner clamps to money and what the bag holds.
        targets = {item: qty for item, qty in requested}
        plan = plan_purchases(
            read_money(io),
            read_bag(io),
            balls=targets.get(POKE_BALL, 0),
            potions=targets.get(POTION, 0),
            reserve=args.reserve,
        )
    try:
        report = run_errand(io, truth, plan, args.heal)
    finally:
        with open(args.out, "wb") as f:
            pb.save_state(f)
        pb.stop()
    print(f"errand done: bought {report['bought']} healed {report['healed']} money {report['money']}")
    print(f"party: {[(p['species'], p['level'], p['hp'], p['max_hp']) for p in report['party']]}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
