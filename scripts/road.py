"""The road engine: drive to any map over the extracted graph, one measured lesson at a time.

This is the badge-4 expedition's driver, promoted from probe to engine. Every mechanism in it
was learned by playing:

- **Thresholds.** Warp tiles do not all fire on arrival. Ladders fire on ENTRY (step off, step
  back on); gate doors fire on the step THROUGH them (Route 11's west door fires on the
  eastward step). ``through_warp`` tries every direction and undoes plain steps.
- **Gates sever routes.** A route's edge cells can be unreachable because its gate building
  cuts the map in half. ``pass_gate`` goes through the building - and a candidate door only
  counts if the far side can actually path to the goal (Route 11's Diglett house taught that
  the nearest door is not always the gate).
- **Edges are offset.** The neighbor's grid does not align with every edge cell (the
  connection header carries an offset the extraction does not), so ``cross_edge`` sweeps the
  outward step across open edge cells until one hands over.
- **Interiors are traversed by sides.** A gate entered on one side exits by the mats on
  another; non-edge warps (a 2F stairway) are never exits.
- **Stalls are not refusals.** A stalled step with a textbox up is usually a trainer's
  pre-battle speech - A leads into the fight and the injected battle handler owns it. The
  text BUFFER stays stale after boxes close (measured), so text alone never means blocked:
  only failing to move after repeated A/B cycles does.
- **Cut opens two tile classes.** 0x3D (the Vermilion yard and Celadon hedge bushes) and
  0x50 (Erika's garden trees) both fall to the measured field-Cut flow, driven purely by the
  menu registers.

Battles are delegated through an injected ``battle(io)`` callable so the agent's full battle
turn (catch hook, potions, forced switch, evolution guard) can own every encounter; the
default refuses to guess and raises instead.
"""

from quartermaster import ADDR_IN_BATTLE, ADDR_MENU_CUR, QuartermasterError, read_pos

# Live sprite table: C1x0 nonzero = slot in use; C2x4/C2x5 hold (y,x)+4 map coordinates.
SPRITE_STATE_BASE = 0xC100
SPRITE_DATA_BASE = 0xC200

# Tileset 22 is the facility floor set (Rocket Hideout, Silph Co). Its tiles decide where you end
# up - spin arrows, teleport pads - so a planned path is a category error there and the engine's
# own answer is the facing-keyed oracle. Read from the map, never assumed.
FACILITY_TILESET = 22

_OPPOSITE = {"down": "up", "up": "down", "right": "left", "left": "right"}
_OUTWARD = {"west": "left", "east": "right", "north": "up", "south": "down"}


def _default_battle(io) -> None:
    raise QuartermasterError("road: a battle started and no battle handler was injected")


BOULDER_PIC = 63  # the picture of every sprite on the boulder maps (108, 155, 159-162, 192, 194, 198), extracted


def live_sprites(io, bounds: tuple[int, int] | None = None) -> dict[int, tuple[int, int]]:
    """``{slot: (x, y)}`` for every live sprite, slot 1..15 -- slot ``i`` draws the cartridge's
    sprite ``i - 1`` for the map, which is how a boulder keeps its identity after it moves."""
    out = {}
    for i in range(1, 16):
        if io.read(SPRITE_STATE_BASE + i * 0x10):
            xy = (io.read(SPRITE_DATA_BASE + i * 0x10 + 5) - 4, io.read(SPRITE_DATA_BASE + i * 0x10 + 4) - 4)
            if bounds is None or (0 <= xy[0] < bounds[0] and 0 <= xy[1] < bounds[1]):
                out[i] = xy
    return out


def live_bodies(io, bounds: tuple[int, int] | None = None) -> set[tuple[int, int]]:
    """Positions of every live sprite - a beaten trainer still stands, and paths route around.

    ``bounds`` is the current map's ``(width, height)``, and passing it matters: the sprite table
    has sixteen slots and the unused ones decode to coordinates that are not on any map. Silph 3F
    is 30x18 and a leg was told the body severing its hop stood at **(18,22)** - four rows past
    the south wall. It then walked over to "engage" that body, which opened the pause menu, and
    wrote down what the menu said ("OPTION EXIT") as the sentence the blocker spoke.
    """
    out = set()
    for i in range(1, 16):
        if io.read(SPRITE_STATE_BASE + i * 0x10):
            out.add((io.read(SPRITE_DATA_BASE + i * 0x10 + 5) - 4, io.read(SPRITE_DATA_BASE + i * 0x10 + 4) - 4))
    if bounds is not None:
        w, h = bounds
        out = {(x, y) for x, y in out if 0 <= x < w and 0 <= y < h}
    return out


def _step(io, direction: str) -> None:
    io.press(direction, hold=8, release=8)
    io.wait(30)


def reachable(truth, pairs, map_id: int, start, blocked=()) -> set[tuple[int, int]]:
    """Every cell reachable from ``start`` on this map, treating ``blocked`` cells as solid.

    One-way LEDGE hops count, the way ``rom_truth.path_on_map`` already counts them: a hop
    lands two cells out over a tile the grid calls solid. Measured on Route 19 (map 30): the
    beach a leg arrives on from Fuchsia is a six-cell strip whose only way down to the plaza
    and the sea is three ledge rows, and a flood fill that cannot hop them reported the shore
    as unreachable while the planner walked it in nine presses.
    """
    from collections import deque

    import rom_truth as rt

    m = truth["maps"][str(map_id)]
    w, h = m["width"], m["height"]
    blocked = set(blocked)
    tiles = m.get("tiles")
    ledges = rt.loaded_ledges(truth) if m.get("tileset") == 0 and tiles else set()

    def tile(tx, ty):
        return int(tiles[ty][2 * tx : 2 * tx + 2], 16)

    # A door is a warp tile the collision grid calls solid (the Elite Four rooms' (4,0)/(5,0),
    # measured): it is reachable from the cell beside it, and leads off the map, so it is a
    # terminal cell here -- seen, never expanded from.
    warps = {(wp[0], wp[1]) for wp in m.get("warps", [])}
    seen = {tuple(start)}
    queue = deque([tuple(start)])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in seen or (nx, ny) in blocked:
                continue
            if (nx, ny) in warps and m["grid"][ny][nx] != "1" and m["grid"][y][x] == "1":
                seen.add((nx, ny))
                continue
            if m["grid"][ny][nx] != "1" or not rt.passable(m, pairs, x, y, nx, ny):
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
        if not ledges:
            continue
        for d, (dx, dy) in rt.LEDGE_DELTAS.items():
            mx, my, lx, ly = x + dx, y + dy, x + 2 * dx, y + 2 * dy
            if not (0 <= lx < w and 0 <= ly < h) or (lx, ly) in seen or (lx, ly) in blocked or (mx, my) in blocked:
                continue
            if (d, tile(x, y), tile(mx, my)) in ledges and m["grid"][ly][lx] == "1":
                seen.add((lx, ly))
                queue.append((lx, ly))
    return seen


def walkable(truth, pairs, map_id: int, start, bodies=(), keep=()) -> set[tuple[int, int]]:
    """The cells ``walk`` can actually deliver us to: bodies *and* every warp tile are walls.

    ``reachable`` answers a terrain question and ``walk`` answers a movement one, and inside a
    facility the two disagree wildly - because ``walk`` refuses to thread a door tile as floor
    (a pad fires the moment you step on it, so a route "through" one is a route off the floor).
    Silph 5F is the measurement: the corridor holding the CARD KEY is *reachable* from anywhere
    on the floor, and the only path to it crosses the teleport pad at (27,3). Every approach that
    trusted ``reachable`` was refused live, on both of the two sessions that hunted that key,
    with no sentence on screen to explain it. Ride the pad and the same corridor is nine steps.

    ``keep`` are warp tiles that stay open - the targets of the walk itself, which ``walk``
    excludes from its own warp block for the same reason.
    """
    warps = {(w[0], w[1]) for w in truth["maps"][str(map_id)]["warps"]} - set(keep)
    return reachable(truth, pairs, map_id, start, set(bodies) | warps)


def pads_reaching(truth, pairs, map_id: int, targets, bodies=()) -> list[tuple[tuple[int, int], int]]:
    """``(pad, the map it pairs with)`` for every warp tile on this map that *stands* inside a
    region holding ``targets`` - the ride hidden behind a bare "could not reach".

    A leg that cannot walk to a cell is not stuck if a pad lands beside it: Silph 5F's card-key
    corridor is nine steps from the pad at (27,3), which pairs with 7F, and zero routes from
    anywhere else on the floor. Naming the pad is the difference between a wall and a detour.
    """
    targets = set(targets)
    out = []
    for wx, wy, dest, _wid in truth["maps"][str(map_id)]["warps"]:
        pad = (wx, wy)
        if pad in targets:
            continue
        if walkable(truth, pairs, map_id, pad, bodies, keep={pad} | targets) & targets:
            out.append((pad, dest))
    return out


def rides_to(truth, pairs, map_id: int, targets, bodies=()) -> list[dict]:
    """Every door **on any map** whose landing can walk to ``targets``, nearest-first by hops.

    ``pads_reaching`` answers "which pad on this floor", which is not the question a gated
    building poses. Silph asks the cross-floor one: the CARD KEY's corridor on 5F is entered only
    from the pad at (27,3), which is entered only by riding 7F's (21,15), which sits in a 7F
    pocket that is itself behind card-key doors - so the useful question is never "which pad is
    beside the target" but "which door, anywhere in the building, lands somewhere that can reach
    it". Three legs died re-deriving that by hand, one floor at a time.

    Each entry is ``{"from_map", "door", "lands", "hops"}``: ride ``door`` on ``from_map`` and you
    arrive at ``lands``, from which the target is walkable. ``hops`` is 0 when the landing walks
    straight to the target and 1 when it reaches a pad that does. Landings are read from the
    destination's own warp list, the same way the router resolves a hop, and reachability is the
    movement question (``walkable``), not the terrain one.
    """
    targets = set(targets)
    here = truth["maps"].get(str(map_id))
    if here is None:
        return []
    direct = {(w[0], w[1]) for w in here["warps"]}
    # Landings on this map that walk to the target, plus landings that reach a pad that does.
    relay = {pad for pad, _dest in pads_reaching(truth, pairs, map_id, targets, bodies)}
    found: list[dict] = []
    for src, m in truth["maps"].items():
        for wx, wy, dest, wid in m["warps"]:
            if dest != map_id or wid >= len(here["warps"]):
                continue
            lands = (here["warps"][wid][0], here["warps"][wid][1])
            open_here = walkable(truth, pairs, map_id, lands, bodies, keep={lands} | targets | relay)
            if open_here & targets:
                hops = 0
            elif open_here & relay:
                hops = 1  # pragma: no cover - a two-step ride; exercised live on Silph 5F
            else:
                continue
            found.append({"from_map": int(src), "door": (wx, wy), "lands": lands, "hops": hops})
    found.sort(key=lambda r: (r["hops"], r["from_map"], r["door"]))
    return [r for r in found if r["door"] not in direct or r["from_map"] != map_id]


def pad_land(truth, map_id: int, warp) -> tuple[int, int] | None:
    """The cell a same-map warp lands on - its destination index reads the same map's own list.

    ``255`` (0xFF) is the ROM's "same map" destination and resolves here too: Sabrina's gym's two
    arrival mats (8,17)/(9,17) carry it. A door to another map is ``None`` - the pad graph is the
    within-floor structure, and cross-floor round trips are ``_return_through``'s job.
    """
    m = truth["maps"].get(str(map_id))
    if m is None:
        return None
    _wx, _wy, dst, idx = warp
    if dst not in (0xFF, map_id):
        return None
    if not isinstance(idx, int) or not (0 <= idx < len(m["warps"])):
        return None
    return (m["warps"][idx][0], m["warps"][idx][1])


def pad_route(truth, pairs, map_id: int, start, targets, bodies=()) -> list[tuple[int, int]] | None:
    """The shortest ride SEQUENCE that brings ``targets`` into walkable reach, or None.

    BFS over the pad graph, which the cartridge already gave us complete: every warp's landing is
    an index into its own warp list, and every pad's pocket is a ``walkable`` region. Riding
    pads in table order *explores* that graph; riding a route through it is a measurement plus a
    walk, and exploration is what a leg's budget is not for. Sabrina's gym is thirty pads in
    2-cycles (every landing is another pad tile), one pocket has exactly one exit (its own pad,
    re-fired by stepping off it and back on), and the leader's pocket sits two rides from the
    door while the table-order hunt burns its budget standing elsewhere.

    ``[]`` means the walk already covers ``targets`` and ``ride_pad``'s own walk collects it.
    Entries are the warp tiles to ride, in order. Landings are re-measured live by the caller,
    and the next hop re-plans from wherever the cartridge actually left us, so table and live may
    disagree in either direction and the loop still converges.
    """
    from collections import deque

    targets = set(targets)
    if not targets or truth["maps"].get(str(map_id)) is None:
        return None  # checked BEFORE `walkable`, which raises on a map we do not model
    bodies = set(bodies)
    # The targets stay open. `walkable` treats every warp tile as a wall, which is right for
    # routing *through* one and wrong when the target IS one - and a gym's exit mat is exactly
    # that. Without this the goal is unreachable by construction: badge 6 was won at (9,9) behind
    # thirty pads and the leg then re-tried the mat at (8,17) until its budget ran out, because
    # the BFS could never report the mat as reached. `walk` excludes its own targets from the
    # warp block for the same reason.
    if walkable(truth, pairs, map_id, start, bodies, keep=targets) & targets:
        return []
    m = truth["maps"][str(map_id)]
    pads = [w for w in m.get("warps", []) if pad_land(truth, map_id, w) is not None]
    routes = {tuple(start): []}
    queue = deque([tuple(start)])
    while queue:
        anchor = queue.popleft()
        for warp in pads:
            pad = (warp[0], warp[1])
            if not (walkable(truth, pairs, map_id, anchor, bodies, keep={pad}) & {pad}):
                continue  # this pad does not stand in the pocket we are standing in
            land = pad_land(truth, map_id, warp)
            if land in routes:
                continue
            routes[land] = routes[anchor] + [pad]
            queue.append(land)
            if walkable(truth, pairs, map_id, land, bodies, keep=targets) & targets:
                return routes[land]  # pragma: no cover - reached only when a ride opens the target
    return None


def ride_pad(  # pragma: no cover - drives the emulator; verified live, not in unit tests
    io, truth, pairs, map_id: int, targets, *, battle=_default_battle, rides: int = 6
):
    """Reach ``targets`` by riding pads, when no walk can get there.

    The capability every Silph leg was missing. ``walk`` treats a pad as a wall - correctly, since
    stepping on one fires it - so a region whose only entrance *is* a pad is unreachable to it, and
    the leg reports "could not reach" with nothing on screen to explain why.

    Two shapes, both measured. A pad that pairs with **another map** is ridden as a round trip:
    Silph 5F's (26,3) step east fires (27,3), lands on 7F (21,15), and stepping off it and back on
    returns us *standing on (27,3)* - inside the region the walk could never enter, with (28,3) one
    step away. Arriving on a pad does not re-fire it, which is why the far side must be left and
    re-entered. A pad that points at **its own map** simply moves us: Sabrina's gym is thirty of
    those (30 of its 32 warps), and there is no far side to come back from.

    The order of the rides comes from ``pad_route`` - a BFS over the pad graph - because
    table-order hunting is how a leg rides one wrong pocket per hop and spends its budget.
    Each hop still tries a sequence of pads (routed first, the old nearest-use hunt behind),
    and after every ride the landing is re-measured and the next hop re-plans from wherever the
    cartridge actually left us, so table and live may disagree in either direction and the call
    still converges.
    """
    targets = set(targets)
    tried: set[tuple[int, int]] = set()  # pads already ridden this call, so a maze cannot cycle
    rides = max(int(rides), 1)
    for _ in range(rides):
        if walk(io, truth, pairs, map_id, targets, battle=battle) is True:
            return True
        pos = read_pos(io)
        if pos[0] != map_id:
            return False  # a ride took us off this floor and could not come back
        if _ride_hop(io, truth, pairs, map_id, targets, tried, battle=battle):
            if walk(io, truth, pairs, map_id, targets, battle=battle) is True:
                return True  # the landing put the targets within feet
            continue  # we moved; the next hop re-plans from where the cartridge left us
        return False  # no pad here took us anywhere; more hops would ride the same dead ends
    return False


def _ride_hop(io, truth, pairs, map_id: int, targets, tried: set[tuple[int, int]], *, battle=_default_battle) -> bool:
    """One hop: ride the routed sequence first, the old nearest-use hunt behind - walk after each.

    True if any pad actually moved us, False if none did. Pads that never took us stay untried
    (a walk not reaching a tile is not a ride); ones that did are consumed, because a maze of
    pads is a graph with cycles and riding the same one each hop is how a leg spends its budget
    standing in two rooms.
    """
    bodies = live_bodies(io)
    here = read_pos(io)[1:]
    routed = [p for p in (pad_route(truth, pairs, map_id, here, targets, bodies) or []) if p not in tried]
    best = [
        pad
        for pad, _dest in pads_reaching(truth, pairs, map_id, targets, bodies)
        if pad not in tried and pad not in routed
    ]
    others = [
        (w[0], w[1])
        for w in truth["maps"][str(map_id)]["warps"]
        if (w[0], w[1]) not in best
        and (w[0], w[1]) not in routed
        and (w[0], w[1]) not in tried
        and walkable(truth, pairs, map_id, here, bodies, keep={(w[0], w[1])}) & {(w[0], w[1])}
    ]
    moved = False
    for pad in routed + best + others:
        before = read_pos(io)
        now = _ride_live(io, truth, pairs, map_id, pad, battle=battle)
        if now == before:
            continue  # never got moving toward this pad - not a ride, so it stays untried
        tried.add(pad)  # only pads that actually moved us count as spent
        moved = True
        if now[0] != map_id and not _return_through(io, truth, pairs, map_id, now[0], now[1], now[2]):
            return True  # pragma: no cover - drives the emulator; verified live on Silph 5F
        if walk(io, truth, pairs, map_id, targets, battle=battle) is True:
            return True
    return moved


def _ride_live(io, truth, pairs, map_id: int, pad, *, battle=_default_battle) -> tuple[int, int, int]:
    """End up where ``pad`` lands - by walking onto it, or re-firing it from our own feet.

    A pad does not fire the moment we are standing on it; it fires on (re)entry. A dead-end
    pocket's only exit IS its own pad - Sabrina's gym parks the gym-side trainer in one - and
    the step-off-and-back is the whole ride. Each side is tried once; a blocked side costs
    nothing but the step, and a side that takes us anywhere counts as the measurement.
    """
    was = read_pos(io)
    if was[0] == map_id and was[1:] == pad:
        for direction, back in (("right", "left"), ("left", "right"), ("down", "up"), ("up", "down")):
            _step(io, direction)
            io.wait(60)
            if read_pos(io) == was:
                continue  # pragma: no cover - drives the emulator; a held or closed side
            _step(io, back)
            io.wait(60)
            now = read_pos(io)
            if now != was:
                return now  # the pad re-fired (or something else moved us - position is the fact)
        return was  # pragma: no cover - drives the emulator; a pad that fires for nobody
    walk(io, truth, pairs, map_id, {pad}, battle=battle)
    # The walk's own verdict is not the signal: a pad that fires mid-walk leaves it still trying
    # to reach a tile we have already been teleported off, and it reports "no-path". Position is
    # the measurement.
    return read_pos(io)


def _return_through(  # pragma: no cover - drives the emulator; verified live, not in unit tests
    io, truth, pairs, map_id: int, mp: int, x: int, y: int
) -> bool:
    """Standing on the far side's warp tile, step off and back on to come home. True if we did."""
    import rom_truth as rt

    far = truth["maps"].get(str(mp))
    if not far:
        return False
    for direction, (dx, dy) in (("down", (0, 1)), ("up", (0, -1)), ("left", (-1, 0)), ("right", (1, 0))):
        nx, ny = x + dx, y + dy
        if not (0 <= nx < far["width"] and 0 <= ny < far["height"]):
            continue
        if far["grid"][ny][nx] != "1" or not rt.passable(far, pairs, x, y, nx, ny):
            continue
        _step(io, direction)
        if read_pos(io)[1:] != (nx, ny):
            continue  # a body or a script ate the step; try another side
        _step(io, _OPPOSITE[direction])
        return read_pos(io)[0] == map_id
    return False


def gate_doors(truth, map_id: int) -> set[tuple[int, int]]:
    """The doors on this map that belong to a gate building rather than a dead-end house.

    Measurable signature, no recall needed: a building you can *pass through* is entered from
    this map by two or more doors (Route 12's gate is (10,15), (11,15) and (10,21), all into map
    87 - two doors on the north side of the severance and one on the south). A house is entered
    by exactly one. ``pass_gate`` aims at the nearest door first and Route 11's Diglett house
    taught what that costs; this is the same lesson as a lookup.
    """
    by_dest: dict[int, set[tuple[int, int]]] = {}
    for wx, wy, dst, _wid in truth["maps"].get(str(map_id), {}).get("warps", []):
        by_dest.setdefault(dst, set()).add((wx, wy))
    return {door for doors in by_dest.values() if len(doors) > 1 for door in doors}


def blocking_body(truth, pairs, map_id: int, start, targets, bodies):
    """The one body whose removal reconnects ``targets`` - the wall, not the bump.

    ``walk`` reports the body it bumped into. That is often not the body that matters. Measured
    on Route 12: the step north was refused by a trainer at (14,76) that column 15 walks straight
    around, while the actual severance was a single sprite at (10,62) fifteen tiles away - one
    body holding 237 cells and the map's only gate door hostage. Naming the bystander sends a
    crew to argue with the wrong sprite, and "body-blocked" then reads as a wall when it is a
    story gate standing somewhere else entirely.

    Returns ``None`` when the targets are already reachable, or when no *single* body explains
    the severance (two parked trainers in one corridor are terrain, not a gate).
    """
    targets = set(targets)
    bodies = set(bodies)
    if reachable(truth, pairs, map_id, start, bodies) & targets:
        return None
    for body in sorted(bodies):
        if reachable(truth, pairs, map_id, start, bodies - {body}) & targets:
            return body
    return None


def edge_cells(truth: dict, cur: int, nxt: int) -> tuple[set[tuple[int, int]], str]:
    """The open cells on ``cur``'s edge facing ``nxt``, and the outward direction."""
    m = truth["maps"][str(cur)]
    side = next((k for k, v in m.get("connections", {}).items() if v == nxt), None)
    if side is None:  # not a neighbour by connection: no edge, no direction (measured: 17->10 on a reroute)
        return set(), ""
    if side in ("north", "south"):
        row = 0 if side == "north" else m["height"] - 1
        return {(x, row) for x in range(m["width"]) if m["grid"][row][x] == "1"}, _OUTWARD[side]
    col = 0 if side == "west" else m["width"] - 1
    return {(col, y) for y in range(m["height"]) if m["grid"][y][col] == "1"}, _OUTWARD[side]


def surf_region(truth, pairs, map_id: int, start) -> set:
    """Everywhere a SURFER can stand from ``start`` on this map: the land the walk reaches, every
    water component (in the tile model) that land touches, and every shore those waters touch,
    to closure. ``start`` may itself be water (a leg banked afloat).

    Route 20, measured 2026-09-06: the west sea reaches only the island's south lobe, whose door
    (58,9) is the way into Seafoam; the NE land the cave's west door opens onto touches the east
    sea. Neither is one walk, and both are one surf.
    """
    m = truth["maps"][str(map_id)]
    w, h = m["width"], m["height"]
    if not m.get("tiles"):
        return reachable(truth, pairs, map_id, tuple(start))
    region: set = set()
    land_todo = []
    water_todo = []
    if _water_model(m, *start):
        if current_at(truth, map_id, start) is not None:
            return {tuple(start)}  # afloat on a conveyor: carried, not standing
        water_todo.append(tuple(start))
    else:
        land_todo.append(tuple(start))
    while land_todo or water_todo:
        while land_todo:
            cell = land_todo.pop()
            if cell in region:
                continue
            land = reachable(truth, pairs, map_id, cell)
            region |= land
            for x, y in land:
                if not shore_ok(m, x, y):
                    continue
                for dx, dy in _FACES:
                    n = (x + dx, y + dy)
                    if 0 <= n[0] < w and 0 <= n[1] < h and n not in region and _water_model(m, *n):
                        if current_at(truth, map_id, n) is None:  # a conveyor is a hop, not a place
                            water_todo.append(n)
        while water_todo:
            cell = water_todo.pop()
            if cell in region:
                continue
            water = set(_water_reach(m, cell[0], cell[1], set()))
            region |= water
            for x, y in water:
                for dx, dy in _FACES:
                    n = (x + dx, y + dy)
                    if 0 <= n[0] < w and 0 <= n[1] < h and n not in region and m["grid"][n[1]][n[0]] == "1":
                        if shore_ok(m, *n):
                            land_todo.append(n)
    return region


def _mat_destinations(maps: dict, mp: int, dwarp: int, came_from) -> list[int]:
    """Where a LAST_MAP mat on ``mp`` with warp index ``dwarp`` can land.

    The game returns to the OUTDOOR map the building was entered from, whatever floors were
    walked in between. Seafoam 1F, measured 2026-09-06: walking up from B1 and out the ground-floor
    mat lands on Route 20, not on B1, though B1 also warps into 1F. So: the map we came from if it
    is an overworld map (tileset 0) with a door into ``mp``; else every overworld map with one;
    else (an indoor mat between indoor floors) every map with one. Only maps with a warp at that
    index count.
    """
    entrants = [
        int(k)
        for k, om in maps.items()
        if int(k) != mp and any(w[2] == mp for w in om["warps"]) and dwarp < len(om["warps"])
    ]
    if came_from is not None and came_from in entrants and maps[str(came_from)].get("tileset") == 0:
        return [came_from]
    outdoor = [k for k in entrants if maps[str(k)].get("tileset") == 0]
    return outdoor or entrants


def region_route(
    truth, pairs, src_map: int, src_cell, goal_map: int, banned=frozenset(), max_nodes: int = 300, surf: bool = False
):
    """The first hop out of the player's reachable REGION toward ``goal_map`` - or None.

    ``rom_truth.route`` plans over map ids, and a map is not one place. Route 13, measured
    2026-09-05 (lane 2, seven legs): the routed warp at (12,9) sits north of a one-way ledge row
    the leg stood south of; the walk was no-path, the ban landed elsewhere, and 80 hops went
    50 -> 13 -> 46 without taking the forest (50 -> 51 -> 47 -> 13-north) that joins the two.
    ``rom_truth.pockets`` is undirected and calls both halves one pocket, so the unit here is
    ``reachable`` - the walk's own flood fill, one-way ledges and door tiles included.

    Nodes are (map, region); a hop is a warp standing in the region (a LAST_MAP mat resolves to
    the door on the map that enters this one, by warp index), or a connection the region holds
    edge cells of (entering the far map at the aligned cell, or the nearest open edge cell). A
    water edge has no cell to stand on, so the far map counts as one region there and the surf
    decides live. Regions are keyed by their smallest cell.
    """
    from collections import deque

    import rom_truth as rt

    maps = truth["maps"]
    if src_map == goal_map or str(src_map) not in maps or str(goal_map) not in maps:
        return None

    def region(mp, cell):
        if surf:
            return surf_region(truth, pairs, mp, tuple(cell))
        return reachable(truth, pairs, mp, tuple(cell))

    start = region(src_map, src_cell)
    seen = {(src_map, min(start))}
    queue = deque([(src_map, start, None, None)])
    nodes = 0
    while queue and nodes < max_nodes:
        nodes += 1
        mp, reg, first, came_from = queue.popleft()
        m = maps[str(mp)]
        hops = []
        for wx, wy, dst, dwarp in m["warps"]:
            if (wx, wy) not in reg:
                continue
            if dst == rt.LAST_MAP:
                # Back out the way in. Along the chain that is the map we entered from; at the start
                # (a leg booted inside a building) it is any map with a door into this one. Seafoam
                # 1F, measured 2026-09-06: both Route 20 and B1 warp into it, and without this the
                # router "backed out" of the ground floor into the basement.
                for other in _mat_destinations(maps, mp, dwarp, came_from):
                    if (mp, other) in banned:
                        continue
                    land = (maps[str(other)]["warps"][dwarp][0], maps[str(other)]["warps"][dwarp][1])
                    hops.append((other, land, {"from": mp, "to": other, "via": "mat", "x": wx, "y": wy}))
                continue
            if str(dst) not in maps or (mp, dst) in banned:
                continue
            dw = maps[str(dst)]["warps"]
            if dwarp >= len(dw):
                continue
            land = (dw[dwarp][0], dw[dwarp][1])
            hops.append((dst, land, {"from": mp, "to": dst, "via": "warp", "x": wx, "y": wy, "dest_warp": dwarp}))
        if surf:
            for cur in truth.get("currents", []):
                if int(cur["map"]) != mp or (mp, int(cur["lands"][0])) in banned or str(cur["lands"][0]) not in maps:
                    continue
                body = _water_reach(m, cur["cell"][0], cur["cell"][1], set())
                launches = [
                    (c, f)
                    for c in reg
                    if m["grid"][c[1]][c[0]] == "1" and shore_ok(m, *c)
                    for (dx, dy), f in _FACES.items()
                    if (c[0] + dx, c[1] + dy) in body
                ]
                if launches:
                    (lx, ly), face = min(launches)
                    land = (cur["lands"][1], cur["lands"][2])
                    hop = {"from": mp, "to": int(cur["lands"][0]), "via": "current", "x": lx, "y": ly, "face": face}
                    hops.append((int(cur["lands"][0]), land, hop))
        for side, dst in m["connections"].items():
            if str(dst) not in maps or (mp, dst) in banned:
                continue
            cells, _d = edge_cells(truth, mp, dst)
            mine = cells & reg
            ours_water = _edge_water(m, _d) & reg if (surf and not cells and edge_has_water(truth, mp, dst)) else set()
            if not mine and not ours_water:
                continue  # a land edge this region does not touch; or water, which only a surfer's own water crosses
            dm = maps[str(dst)]
            line = {"north": 0, "south": m["height"] - 1, "west": 0, "east": m["width"] - 1}[side]
            vertical = side in ("north", "south")
            on_line = [c for c in (mine or ours_water) if (c[1] if vertical else c[0]) == line]
            # The connection's alignment (extracted from the header; measured first on Route 15 -> map 3,
            # where the "nearest open cell" guess put the leg in a 13-cell pocket the game never enters).
            shift = m.get("connection_offsets", {}).get(side, 0)

            def across(c):
                if side == "north":
                    return (c[0] + shift, dm["height"] - 1)
                if side == "south":
                    return (c[0] + shift, 0)
                if side == "west":
                    return (dm["width"] - 1, c[1] + shift)
                return (0, c[1] + shift)

            fcells, _fd = edge_cells(truth, dst, mp)
            if mine:
                # One connection, several far regions: map 3's west edge (measured 2026-09-06) opens
                # onto the town at rows 18..19 and onto a fenced strip at rows 21..35, and only the
                # strip walks on to the south edge. Every aligned pair of open cells is its own entry,
                # and the hop carries the cell to cross at.
                seen_far = set()
                for c in sorted(on_line or mine):
                    far_cell = across(c)
                    if far_cell not in fcells:
                        continue
                    far_key = min(reachable(truth, pairs, dst, far_cell))
                    if far_key in seen_far:
                        continue
                    seen_far.add(far_key)
                    hop = {"from": mp, "to": dst, "via": "edge", "edge": side, "x": c[0], "y": c[1]}
                    hops.append((dst, far_cell, hop))
                if seen_far:
                    continue
                if not fcells and surf and dm.get("tiles"):
                    pass  # land here, water there: fall through to the water entry below
                else:
                    continue
            cx, cy = min(on_line or (mine or ours_water))
            aligned = across((cx, cy))
            if fcells:
                nearest = min(fcells, key=lambda c: abs(c[0] - aligned[0]) + abs(c[1] - aligned[1]))
                entry = aligned if aligned in fcells else nearest
            elif surf and dm.get("tiles"):
                # No land to step onto: the far edge is water, and the surf region starts from the water
                # cell we would land on. Counting the whole far map here let Route 20 look crossable by
                # stepping out to Cinnabar and back (measured 2026-09-06, 39 identical hops).
                fline = {"north": dm["height"] - 1, "south": 0, "west": dm["width"] - 1, "east": 0}[side]
                fwater = [
                    (x, y)
                    for y in range(dm["height"])
                    for x in range(dm["width"])
                    if (y if vertical else x) == fline and _water_model(dm, x, y)
                ]
                if not fwater:
                    continue
                entry = min(fwater, key=lambda c: abs(c[0] - aligned[0]) + abs(c[1] - aligned[1]))
            else:
                continue  # nothing modelled to stand on over there
            hops.append((dst, entry, {"from": mp, "to": dst, "via": "edge", "edge": side}))
        for dst, land, hop in hops:
            if surf and hop["via"] != "current":
                carried = current_at(truth, dst, land)
                if carried is not None:  # the door opens onto a conveyor: the node is where it lands
                    dst, land = int(carried["lands"][0]), (carried["lands"][1], carried["lands"][2])
            reg2 = region(dst, land)  # never empty: the entry cell itself stands in it
            key = (dst, min(reg2))
            if key in seen:
                continue
            seen.add(key)
            chosen = first or hop
            if dst == goal_map:
                return chosen
            queue.append((dst, reg2, chosen, mp))
    return None


def edge_has_water(truth: dict, cur: int, nxt: int) -> bool:
    """Does ``cur``'s edge line facing ``nxt`` carry water in the tile model?

    Cinnabar -> Route 20 (8 -> 31), measured 2026-09-05 on lanes 4 and 5 (~800 s each): the east
    column has land at rows 4..13, so the land cross walked there and was refused - the far side
    of those rows is a cliff tile - and "land on the near edge" was read as a genuine block. The
    crossing is on the water rows 14..16 of the same column. An edge with land AND water is a
    shore, and the water is the part that opens; a modelled edge with no water is a wall.
    """
    m = truth["maps"][str(cur)]
    if not m.get("tiles"):
        return False
    _cells, d = edge_cells(truth, cur, nxt)
    if not d:
        return False
    w, h = m["width"], m["height"]
    if d in ("up", "down"):
        row = 0 if d == "up" else h - 1
        return any(_water_model(m, x, row) for x in range(w))
    col = 0 if d == "left" else w - 1
    return any(_water_model(m, col, y) for y in range(h))


def walk(io, truth, pairs, map_id: int, targets, *, battle=_default_battle, cap: int = 500, avoid_warps: bool = True):
    """BFS-walk toward the nearest target; battles are the handler's, stalls get A/B cycles.

    ``avoid_warps`` (the standing doctrine: never thread a door tile as floor) blocks every
    non-target warp tile - measured here when a walk to a gate door was swallowed en route
    by the decoy door beside it. Returns True on arrival, "map-change" when a warp or edge
    fired en route, "no-path" when even the bodiless grid is severed, "body-blocked" when
    only a live sprite bars the next step, "refused" when repeated A/B cycles never move
    us, "cap" on step exhaustion."""
    import rom_truth as rt

    targets = set(targets)
    warp_block: set[tuple[int, int]] = set()
    if avoid_warps:
        warp_block = {(w[0], w[1]) for w in truth["maps"][str(map_id)]["warps"]} - targets
    stalls = cycles = body_waits = 0
    for _ in range(cap):
        if io.read(ADDR_IN_BATTLE):
            battle(io)
        mp, x, y = read_pos(io)
        if mp != map_id:
            return "map-change"
        if (x, y) in targets:
            return True
        # Never block the tile we are standing on. Arriving through a door leaves us ON it, and
        # a warp block that includes our own cell makes every plan from there impossible - which
        # is why "could not step off the warp mat" fired on Silph 3F, the Center's exit and the
        # Safari Zone's arrival pad, and why a leg that had just walked in could not walk on.
        here_block = warp_block - {(x, y)}
        path = rt.path_on_map(truth, pairs, map_id, (x, y), targets, blocked=live_bodies(io) | here_block)
        if not path or len(path) < 2:
            path = rt.path_on_map(truth, pairs, map_id, (x, y), targets, blocked=here_block)
            if not path or len(path) < 2:
                return "no-path"
            if tuple(path[1]) in live_bodies(io):
                # Bodies are not walls: wanderers move - wait them out before giving up
                # (a parked story-body earns the verdict only after real patience).
                body_waits += 1
                if body_waits > 20:
                    return "body-blocked"
                io.wait(60)
                continue
        nx, ny = path[1]
        _step(io, "right" if nx > x else "left" if nx < x else "down" if ny > y else "up")
        if read_pos(io) == (mp, x, y) and not io.read(ADDR_IN_BATTLE):
            stalls += 1
            if stalls >= 4:
                cycles += 1
                for _ in range(3):
                    io.press("a")
                    io.wait(40)
                    if io.read(ADDR_IN_BATTLE):
                        break
                if io.read(ADDR_IN_BATTLE):
                    battle(io)
                else:
                    io.press("b")
                    io.wait(30)
                stalls = 0
                if cycles >= 4:
                    return "refused"
        else:
            stalls = 0
            cycles = 0
    return "cap"


def through_warp(io, truth, pairs, map_id: int, wx: int, wy: int, *, battle=_default_battle):
    """Walk onto a warp tile and make it fire, whatever its shape (entry warp or threshold)."""
    r = walk(io, truth, pairs, map_id, {(wx, wy)}, battle=battle)
    if r == "map-change":
        io.wait(60)
        return True
    if r is not True:
        return r
    for d in ("right", "left", "up", "down"):
        before = read_pos(io)
        _step(io, d)
        io.wait(60)
        now = read_pos(io)
        if now[0] != map_id:
            return True
        if now != before:
            _step(io, _OPPOSITE[d])  # plain step: undo (re-entering the tile may fire it)
            io.wait(60)
            if read_pos(io)[0] != map_id:
                return True
    return "warp-dead"


def traverse_interior(io, truth, pairs, interior: int, *, battle=_default_battle, exclude_entry: bool = True):
    """Exit a swallowed-hop interior by the mats on a side other than the one we entered.

    With ``exclude_entry=False`` the entry side is allowed too - the retreat a gate-passer
    needs when an interior turns out to be a dead-end house rather than a gate."""
    m = truth["maps"].get(str(interior))
    if m is None:
        return "unknown-interior"
    w, h = m["width"], m["height"]
    _, ex, ey = read_pos(io)
    sides: dict[str, list[tuple[int, int]]] = {"west": [], "east": [], "north": [], "south": []}
    for wx, wy, _dst, _wid in m["warps"]:
        if wx == 0:
            sides["west"].append((wx, wy))
        elif wx == w - 1:
            sides["east"].append((wx, wy))
        elif wy == 0:
            sides["north"].append((wx, wy))
        elif wy == h - 1:
            sides["south"].append((wx, wy))
    entry = "west" if ex <= 1 else "east" if ex >= w - 2 else "north" if ey <= 1 else "south"
    order = [s for s in ("east", "west", "south", "north") if s != entry and sides[s]]
    if not exclude_entry and sides[entry]:
        order.append(entry)
    for side in order:
        # Door by door, not the side as one target set: a gate can carry two corridors on one
        # side (Route 16's 186 has west doors on rows 2-3 and 8-9), and a walk aimed at the set
        # settles for whichever is nearest - the one that lands back where the leg already was.
        for door in sides[side]:
            r = walk(io, truth, pairs, interior, {door}, cap=80, battle=battle)
            if r == "map-change":
                io.wait(60)
                return True
            if r is True:
                _step(io, _OUTWARD[side])
                io.wait(60)
                if read_pos(io)[0] != interior:
                    return True
    return "interior-stuck"


def pass_gate(io, truth, pairs, cur: int, goal_cells, *, battle=_default_battle) -> bool:
    """Cross a route severed by its own gate building, validating each candidate door."""
    import rom_truth as rt

    m = truth["maps"][str(cur)]
    tried: set[tuple[int, int]] = set()
    while True:
        _, sx, sy = read_pos(io)
        cands = [wp for wp in m["warps"] if (wp[0], wp[1]) not in tried]
        if not cands:
            return False
        wx, wy, _dst, _wid = min(cands, key=lambda wp: abs(wp[0] - sx) + abs(wp[1] - sy))
        tried.add((wx, wy))
        r = through_warp(io, truth, pairs, cur, wx, wy, battle=battle)
        if r is not True or read_pos(io)[0] == cur:
            continue
        interior = read_pos(io)[0]
        r2 = traverse_interior(io, truth, pairs, interior, battle=battle)
        if r2 is not True and read_pos(io)[0] == interior:
            # A dead-end house, not a gate: retreat the way we came and try the next door.
            # Only failure to leave AT ALL is a guard holding us - the finding is on screen.
            if traverse_interior(io, truth, pairs, interior, battle=battle, exclude_entry=False) is not True:
                return False
            continue
        if r2 is True and read_pos(io)[0] == cur:
            _, nx, ny = read_pos(io)
            if rt.path_on_map(truth, pairs, cur, (nx, ny), set(goal_cells)):
                return True


def cross_edge(io, truth, pairs, cur: int, nxt: int, *, battle=_default_battle, cells=None):
    """Cross a map connection, sweeping the outward step across edge cells for alignment.

    ``cells`` restricts the sweep to those edge cells: the region router names the cell whose far
    side is the region it wants (map 3's west edge opens onto two, measured 2026-09-06)."""
    all_cells, d = edge_cells(truth, cur, nxt)
    cells = (set(cells) & all_cells) or all_cells if cells else all_cells
    r = walk(io, truth, pairs, cur, cells, battle=battle)
    if r is not True:
        return r
    tried: set[tuple[int, int]] = set()
    for _ in range(len(cells) + 1):
        if read_pos(io)[0] != cur:
            io.wait(60)
            return True
        here = read_pos(io)[1:]
        tried.add(here)
        crossed = False
        for _ in range(3):
            _step(io, d)
            if read_pos(io)[0] != cur:
                crossed = True
                break
        if crossed:
            continue  # the top-of-loop check confirms and returns
        rest = [c for c in cells if c not in tried]
        if not rest:
            break
        nxt_cell = min(rest, key=lambda c: abs(c[0] - here[0]) + abs(c[1] - here[1]))
        walk(io, truth, pairs, cur, {nxt_cell}, cap=60, battle=battle)
    return "stuck-on-edge"


# SURF crossings (sea-to-sea legs), one measured fact at a time: on the sea routes of this
# cartridge the player stands ON the deep water (the surf move is what carries it), so
# "unreachable" there is a SURF problem - walking will never get a single step - and the leg is
# decided by arming the field move in the game's own menu before the step that failed.
# The standable set is not recalled: it is proposed step-for-step by the water model below
# and answered live by the game's refusals, which re-plan the route.
SURF_MAX_STEPS = 200  # water steps per crossing; a straight run in the connection direction
# reaches the far edge well under this, and more than this is a wrong map, not a long sea.
# Every id here is measured, not recalled. 0x14: standable (the island ring stands on it). 0x32:
# the shore-edged water beside a land column - three left steps from (5,y) onto (4,y) on Route 21
# moved the player (probe_tile32, 2026-09-05); it is what the tile model at Route 20's x=62 and
# Route 19's x=0 is made of. 0x11 was here as "the shallows class" without a measurement, and the
# game refused SURF onto it 103 times on map 15 ("No SURFing on GYARADOS here!") - it is a pond
# tile the fence rows enclose, and a model that called it water sent every 15 -> 3 leg to a shore
# that opens nothing.
WATER_TILES = {0x14, 0x32}


# Where water and land meet, per tileset. On the Seafoam tileset (17) SURF launches from, and lands
# on, 0x15 tiles only: measured 2026-09-06 on B3 - the arm from plain floor (23,12) facing the water
# at (23,11) was refused 31 times, the arm from the 0x15 at (23,9) rode onto (23,10) at once, and
# getting off onto plain floor was refused; the 2026-09-04 legend run landed on B4's 0x15 at (7,3).
# A tileset absent here has no such rule: any walkable cell beside water is a shore.
SHORE_TILES: dict[int, set[int]] = {17: {0x15}}


def shore_ok(m, x: int, y: int) -> bool:
    """May the surfer step between this land cell and the water beside it?"""
    allowed = SHORE_TILES.get(m.get("tileset"))
    if allowed is None or not m.get("tiles"):
        return True
    row = m["tiles"][y]
    return int(row[2 * x : 2 * x + 2], 16) in allowed


def current_at(truth, map_id: int, cell) -> dict | None:
    """The measured current whose water body holds ``cell``, or None."""
    m = truth["maps"][str(map_id)]
    for cur in truth.get("currents", []):
        if int(cur["map"]) != int(map_id):
            continue
        body = _water_reach(m, cur["cell"][0], cur["cell"][1], set())
        if tuple(cell) in body:
            return cur
    return None


def _water_model(m, x: int, y: int) -> bool:
    """Propose whether this cell is standable mid-SURF. Maps without tile data (fake truth in
    tests) propose everything and let the injected io's refusals be the authority."""
    tiles = m.get("tiles")
    if tiles is None:
        return True
    # Off the map is never water. Measured on Route 23 (20x144): facing across the map edge read an
    # empty slice and int('') crashed the whole League leg at the Route 22 -> 23 hop.
    if not (0 <= y < len(tiles)) or not (0 <= x < len(tiles[y]) // 2):
        return False
    return int(tiles[y][2 * x : 2 * x + 2], 16) in WATER_TILES


def _water_reach(m, sx: int, sy: int, blocked: set) -> dict:
    """BFS predecessor map over the water model. The start cell stands unconditionally (the
    shore left us here); everything after it must pass the model and no measured refusal."""
    from collections import deque

    w, h = m["width"], m["height"]

    def ok(x, y, is_start=False):
        return 0 <= x < w and 0 <= y < h and (x, y) not in blocked and (is_start or _water_model(m, x, y))

    if not ok(sx, sy, is_start=True):
        return {}
    prev = {(sx, sy): None}
    queue = deque([(sx, sy)])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if ok(nx, ny) and (nx, ny) not in prev:
                prev[(nx, ny)] = (x, y)
                queue.append((nx, ny))
    return prev


def shore_stand(truth, pairs, cur: int, nxt: int, start, bodies=()) -> tuple[tuple[int, int], str] | None:
    """Where to stand, and which way to face, to arm SURF for the ``cur`` -> ``nxt`` crossing.

    Measured 2026-09-04 on Route 19 (map 30): the leg arrived from Fuchsia at (9,0) on the land
    strip, stepped west along it until the fence refused it, and armed SURF facing that fence.
    The game answered "There's no place to get off!" three times and the ladder wrote the
    crossing off - while the water the crossing needs began thirty rows south. SURF animates
    the player onto the tile they face, so the arm belongs on a land cell that touches water
    whose component actually reaches the far edge. This finds the nearest such cell by walk,
    or None when we already stand beside such water (nothing to do) or the map has no tile
    model to ask (the fakes in tests, where the io's refusals are the authority).
    """
    m = truth["maps"][str(cur)]
    if not m.get("tiles"):
        return None
    _cells, d = edge_cells(truth, cur, nxt)
    if not d:
        return None
    good = _edge_water(m, d)  # water cells in a component that touches the far edge
    if not good:
        return None
    faces = ((0, 1, "down"), (0, -1, "up"), (1, 0, "right"), (-1, 0, "left"))
    sx, sy = start
    if shore_ok(m, sx, sy) and any((sx + dx, sy + dy) in good for dx, dy, _f in faces):
        return None  # already on the shore
    best = None
    for x, y in walkable(truth, pairs, cur, (sx, sy), bodies):
        if not shore_ok(m, x, y):
            continue
        for dx, dy, face in faces:
            if (x + dx, y + dy) in good:
                dist = abs(x - sx) + abs(y - sy)
                if best is None or dist < best[0]:
                    best = (dist, (x, y), face)
    return (best[1], best[2]) if best else None


def _board_water(io, truth, pairs, cur: int, nxt: int, arm_surf, battle) -> bool:
    """From dry land, get afloat on water that reaches the far edge: walk to the shore cell
    ``shore_stand`` names (or stay, if this cell already touches such water), face the water,
    arm SURF. True once the position reads as a water cell in the model.

    Route 21 -> Pallet, measured 2026-09-05 (run 20260905-220532-b24c): the straight north run
    from the sea boarded the land plaza at x=8..13, walked it to row 1 and was refused by the
    rock at (11,0); SURF was then armed facing that rock and failed. The only water that reaches
    row 0 is the x=5..7 column; the crossing is a water ROUTE, and it starts from a shore that
    touches that column - not from wherever the straight line stopped.
    """
    m = truth["maps"][str(cur)]
    here = read_pos(io)
    if here[0] != cur:
        return False
    stand = shore_stand(truth, pairs, cur, nxt, here[1:])
    if stand is not None:
        cell, face = stand
        walk(io, truth, pairs, cur, {cell}, battle=battle)
        if read_pos(io)[0] != cur:
            return False
    else:
        # already beside edge-reaching water: face it (any water neighbour in a far-edge component)
        _cells, d = edge_cells(truth, cur, nxt)
        x, y = read_pos(io)[1:3]
        face = None
        for dx, dy, f in ((0, 1, "down"), (0, -1, "up"), (1, 0, "right"), (-1, 0, "left")):
            if not shore_ok(m, x, y):
                break
            if _water_model(m, x + dx, y + dy) and _touches_far_edge(m, x + dx, y + dy, d):
                face = f
                break
        if face is None:
            return False
    io.press(face, hold=8, release=8)
    io.wait(30)
    if io.read(ADDR_IN_BATTLE) and battle:
        # A wild drawn on the last shore step owns the screen: the POKeMON menu is not there to
        # open ("Gyarados is not on the POKeMON menu (a battle owns the screen)", Route 20,
        # measured 2026-09-05), and an arm attempted into it is a refusal that never was.
        battle(io)
        io.press(face, hold=8, release=8)
        io.wait(30)
    if not arm_surf():
        return False
    for _ in range(3):
        io.press("a")
        io.wait(40)
    mp, x, y = read_pos(io)
    return mp == cur and _water_model(m, x, y)


def _edge_water(m, d: str) -> set:
    """Every water cell (in the model) whose component touches the edge the crossing leaves by."""
    w, h = m["width"], m["height"]
    far = {"left": lambda c: c[0] == 0, "right": lambda c: c[0] == w - 1, "up": lambda c: c[1] == 0}
    far["down"] = lambda c: c[1] == h - 1
    good: set = set()
    seen: set = set()
    for y in range(h):
        for x in range(w):
            if (x, y) in seen or not _water_model(m, x, y):
                continue
            comp = _water_reach(m, x, y, set())
            seen |= set(comp)
            if any(far[d](c) for c in comp):
                good |= set(comp)
    return good


def _hop_to_far_shore(io, truth, pairs, cur: int, nxt: int, d: str, arm_surf, battle) -> bool:
    """When no water from here reaches the far edge, cross to land that does: surf to the island
    (or bank) whose shore touches edge-reaching water, and stand on it. True once ashore there.

    Route 20 (31 -> 30), measured 2026-09-05 (probe_r20_east, 20260905-225930-8d52): the west sea
    stops at x=61 and the east sea starts at x=63; between them stands the island - land at
    x=54..61 with the shore-edged water 0x32 at x=62. No water joins the two seas, so every
    routed crossing from the west found nothing and every straight run ended on the island's west
    rock. The crossing is sea -> island -> sea: ``surf_route`` lands on the island (it already
    walks a shore, arms, and re-plans refused cells), and the caller boards from its far shore.
    """
    m = truth["maps"][str(cur)]
    good = _edge_water(m, d)
    if not good:
        return False
    w, h = m["width"], m["height"]
    stands = set()
    for x, y in good:
        for dx, dy in _FACES:
            n = (x + dx, y + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and m["grid"][n[1]][n[0]] == "1" and shore_ok(m, *n):
                stands.add(n)
    if not stands:
        return False
    here = tuple(read_pos(io)[1:3])
    if not _water_model(m, *here) and reachable(truth, pairs, cur, here) & stands:
        return False  # a walk already reaches a shore of the far water: nothing to hop
    r = surf_route(io, truth, pairs, cur, stands, arm_surf=arm_surf, battle=battle)
    return r is True and read_pos(io)[0] == cur


def _touches_far_edge(m, x: int, y: int, d: str) -> bool:
    """Does the water component holding (x, y) reach the edge the crossing leaves by?"""
    w, h = m["width"], m["height"]
    far = {"left": lambda c: c[0] == 0, "right": lambda c: c[0] == w - 1, "up": lambda c: c[1] == 0}
    far["down"] = lambda c: c[1] == h - 1
    return any(far[d](c) for c in _water_reach(m, x, y, set()))


def _water_cross(io, truth, cur: int, nxt: int, d: str, battle, *, pairs=None, arm_surf=None) -> bool | str | None:
    """Route the water to an opening edge cell, live-corrected: propose a path on the water
    model, verify it press-by-press, let each refusal re-plan. Returns True once the map has
    flipped to the far map, "detoured" when a step flipped to a third map (the ladder takes
    the state back), None when the whole shore has been asked and answered no (or no water
    path exists - which for a walker means the calling refusal stands: there was no surf to
    carry the route).

    The measured 30->31 case forces the shape: the west edge opens on rows 40..52 only, the
    approach is on row 10, and the column between carries a solid notch at rows 38..39, so a
    single-column slide cannot round it. Slides find no row; a route finds one.

    North and south edges are the same shape turned: Route 21's north edge (map 32 -> 0,
    measured 2026-09-05) opens only on the x=5..7 water column, and the candidate set is the
    edge ROW's columns. When ``pairs`` and ``arm_surf`` are given and the player stands on dry
    land in the model, the crossing first boards the water from the shore (``_board_water``);
    a water BFS from a landlocked cell finds nothing, which is how the plaza refusal became
    "stuck-on-edge" with the open column six tiles west.

    A step cancelled by a wild is fought and re-stepped on the SAME row: a cancelled step and
    a refused step are the same bytes at the position, and reading the first as "solid" is the
    exact error the encounter tests fixed for the crossing step.
    """
    m = truth["maps"][str(cur)]
    w = m["width"]
    h = m["height"]
    if d not in ("left", "right", "up", "down"):
        return None
    if pairs is not None and arm_surf is not None and m.get("tiles"):
        mp, x, y = read_pos(io)
        if mp == cur and not _water_model(m, x, y) and not _board_water(io, truth, pairs, cur, nxt, arm_surf, battle):
            return None

    def key_between(a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx:
            return "right" if dx > 0 else "left"
        return "down" if dy > 0 else "up"

    blocked: set = set()  # cells the game has refused - measurements, not recall
    start_x, start_y = read_pos(io)[1:3]
    if d in ("left", "right"):
        edge_col = 0 if d == "left" else w - 1
        # near first; the opening band of an unequal-height edge can sit far along the shore
        # (measured: 30 rows), so the whole shore is the candidate set and nearness is only the order
        candidates = [(edge_col, y) for y in sorted(range(h), key=lambda y: abs(y - start_y))]
    else:
        edge_row = 0 if d == "up" else h - 1
        candidates = [(x, edge_row) for x in sorted(range(w), key=lambda x: abs(x - start_x))]
    for target in candidates:
        sx, sy = read_pos(io)[1:3]
        prev = _water_reach(m, sx, sy, blocked)
        if target not in prev:
            continue  # no water path to this cell now; a later refusal or cell may change that
        path = [target]
        while prev[path[-1]] is not None:
            path.append(prev[path[-1]])
        path.reverse()  # stand -> target
        walked = True
        cell = (sx, sy)
        for step in path[1:]:
            k = key_between(cell, step)
            while True:
                io.press(k, hold=15, release=15)
                io.wait(25)
                if io.read(ADDR_IN_BATTLE) and battle:
                    battle(io)
                    continue  # a wild cancelled the step; re-step it
                pos = read_pos(io)
                if pos[0] != cur:
                    return True if pos[0] == nxt else "detoured"
                if pos[1:] == step:
                    cell = step
                    break
                blocked.add(step)
                walked = False
                break
            if not walked:
                break
        if not walked:
            continue  # that cell is solid where the model said water; replan for the next target
        while True:
            io.press(d, hold=15, release=15)
            io.wait(45)
            if io.read(ADDR_IN_BATTLE) and battle:
                battle(io)
                continue
            pos = read_pos(io)
            if pos[0] != cur:
                return True if pos[0] == nxt else "detoured"
            break
        # This cell stands but does not open. `candidates` visits each exactly once, so there is
        # nothing to remember: the next iteration is already a different cell.
    return None


_FACES = {(0, 1): "down", (0, -1): "up", (1, 0): "right", (-1, 0): "left"}


def _key_between(a, b) -> str:
    dx, dy = b[0] - a[0], b[1] - a[1]
    if dx:
        return "right" if dx > 0 else "left"
    return "down" if dy > 0 else "up"


def _shore_regions(truth, pairs, map_id: int, start, targets, bodies):
    """(here, there): the land region ``start`` is in, and the land that reaches ``targets``."""
    m = truth["maps"][str(map_id)]
    w, h = m["width"], m["height"]
    here = reachable(truth, pairs, map_id, tuple(start), bodies)
    there: set = set()
    for t in targets:
        there.add(t)
        there |= reachable(truth, pairs, map_id, t, bodies)
        for dx, dy in _FACES:
            n = (t[0] + dx, t[1] + dy)
            if 0 <= n[0] < w and 0 <= n[1] < h and m["grid"][n[1]][n[0]] == "1" and n not in bodies:
                there |= reachable(truth, pairs, map_id, n, bodies)
    return here, there - here


def _water_exits(m, prev: dict, there: set, bodies: set):
    """``(path over water, landing)`` pairs from a water BFS ``prev`` onto the land in ``there``."""
    out = []
    for cell in prev:
        for ex, ey in _FACES:
            land = (cell[0] + ex, cell[1] + ey)
            if land not in there or land in bodies or m["grid"][land[1]][land[0]] != "1" or not shore_ok(m, *land):
                continue
            path = [cell]
            while prev[path[-1]] is not None:
                path.append(prev[path[-1]])
            path.reverse()
            out.append((path, land))
    return out


def water_route(truth, pairs, map_id: int, start, targets, bodies=()):
    """A SURF route INSIDE one map: ``(stand, face_in, water_path, landing, face_out)`` from the
    land region ``start`` is in, across a water component, onto the land region that reaches
    ``targets`` -- or None when a walk already reaches them, or no water joins the two.

    Measured on Route 23 (2026-09-05): the hop 34->108 is a warp on the far side of a channel;
    the planner saw land only, reported no-path, and the whole League leg died on the shore.
    ``surf_cross`` crosses a map EDGE; this crosses to a cell. Water is solid in the extracted
    grid (367 cells on map 34, none walkable), so land regions never bleed into it.
    """
    m = truth["maps"].get(str(map_id))
    if not m or not m.get("tiles"):
        return None
    w, h = m["width"], m["height"]
    bodies = set(bodies)
    targets = set(targets)
    here, there = _shore_regions(truth, pairs, map_id, start, targets, bodies)
    if here & targets:
        return None
    best = None
    for ax, ay in here:
        if not shore_ok(m, ax, ay):
            continue
        for (dx, dy), face_in in _FACES.items():
            wx, wy = ax + dx, ay + dy
            if not (0 <= wx < w and 0 <= wy < h) or (wx, wy) in bodies or not _water_model(m, wx, wy):
                continue
            prev = _water_reach(m, wx, wy, bodies)
            for path, land in _water_exits(m, prev, there, bodies):
                cost = len(path) + abs(ax - start[0]) + abs(ay - start[1])
                if best is None or cost < best[0]:
                    face_out = _key_between(path[-1], land)
                    best = (cost, ((ax, ay), face_in, path, land, face_out))
    return best[1] if best else None


def _press_toward(io, cur: int, cell, step, battle) -> tuple:
    """Press once toward ``step`` (re-pressing after a wild, or when a lingering box ate it);
    returns the position read afterwards."""
    key = _key_between(cell, step)
    pos = read_pos(io)
    for _ in range(4):
        io.press(key, hold=15, release=15)
        io.wait(25)
        if io.read(ADDR_IN_BATTLE) and battle:
            battle(io)
            continue
        pos = read_pos(io)
        if pos[0] != cur or tuple(pos[1:3]) == tuple(step):
            break
    return pos


def surf_route(
    io,
    truth,
    pairs,
    cur: int,
    targets,
    *,
    arm_surf=None,
    mount=None,
    battle=_default_battle,
    bodies=(),
    settle=None,
    replans: int = 24,
    log=None,
    dismiss=None,
):
    """Ride ``water_route`` for real: walk to the stand, face the water, arm SURF, then route
    over the water to a landing on the far region, re-planning around every cell the game
    refuses (the model calls it water; a rock sits there -- measured on map 34). True on the
    landing; "no-route" when no water joins the regions; "surfmoved-failed" when the water is
    exhausted; "detoured" when a step flipped the map.

    ``dismiss()`` advances a box a step ran into: measured on Route 23 (2026-09-05) at (8,96),
    a badge guard in the channel says "You can pass here only if you have the MARSHBADGE" and
    every press is eaten until the page is turned; with the badge held he steps aside. A refusal
    is only a refusal once the page is gone.
    ``mount(face)`` gets the surfer onto the water facing ``face`` and answers by position (the
    rig's ``surf_onto``); without it, ``arm_surf`` is called after a turn toward the water and
    ``settle`` closes what arming leaves on screen: measured on Route 23 (2026-09-05, screenshot
    surf_refused.png), the party menu stays up with "AAAA got on GYARADOS" typing out, and every
    direction press until it closes goes nowhere. The io alone cannot see a box; the rig can.
    """
    m = truth["maps"].get(str(cur)) or {}
    if not m.get("tiles"):
        # Without a tile model the water model proposes EVERY cell as water (its contract for
        # the edge crossing's live corrections); here that read a gym floor as open sea and
        # stalled the engage loop "afloat" (measured on maps 45, 171, 236). No model, no route.
        return "no-route"
    bodies = set(bodies)
    targets = set(targets)
    say = log or (lambda *_: None)
    here_cell = tuple(read_pos(io)[1:3])
    afloat = _water_model(m, *here_cell)  # already surfing (a previous route ended mid-water)
    if afloat:
        stand, face_in = here_cell, None
        _here, there = _shore_regions(truth, pairs, cur, here_cell, targets, bodies)
        if not there:
            return "no-route"
        say(f"    afloat at {here_cell}; routing to the far bank")
    else:
        plan = water_route(truth, pairs, cur, here_cell, targets, bodies)
        if plan is None:
            return "no-route"
        stand, face_in, _path, _landing, _face_out = plan
        say(f"    surf plan: stand {stand} face {face_in}, {len(_path)} water cells, land {_landing}")
        r = walk(io, truth, pairs, cur, {stand}, battle=battle)
        if r is not True:
            return r
    if afloat:
        pass
    elif mount is not None:
        if not mount(face_in):
            return "surfmoved-failed"
    else:
        io.press(face_in, hold=8, release=8)  # a walker's step into water is refused: it turns
        io.wait(30)
        if arm_surf is None or not arm_surf():
            return "surfmoved-failed"
        for _ in range(3):
            io.press("a")
            io.wait(40)
        if settle is not None:
            settle()  # the party menu and "AAAA got on GYARADOS!" (measured, Route 23) close here
        for _ in range(3):
            io.press("b")
            io.wait(20)
    if not afloat:
        _here, there = _shore_regions(truth, pairs, cur, stand, targets, bodies)
    blocked = set(bodies)
    for _ in range(replans):
        pos = read_pos(io)
        if pos[0] != cur:
            return "detoured"
        cell = tuple(pos[1:3])
        if cell in there:
            return True
        if face_in is not None and not _water_model(m, *cell) and cell == tuple(stand):
            # still ashore: the confirmation did not carry us on; one step into the water
            pos = _press_toward(
                io, cur, cell, (cell[0] + _FACES_DELTA[face_in][0], cell[1] + _FACES_DELTA[face_in][1]), battle
            )
            if tuple(pos[1:3]) == cell:
                return "surfmoved-failed"
            continue
        prev = _water_reach(m, cell[0], cell[1], blocked)
        exits = _water_exits(m, prev, there, blocked)  # a landing the game refused is out too
        if not exits:
            say(f"    no water exit from {cell} with {len(blocked - bodies)} refused cell(s)")
            return "surfmoved-failed"
        path, land = min(exits, key=lambda e: len(e[0]))
        say(f"    water leg from {cell}: {len(path)} cells to land at {land}")
        for step in path[1:] + [land]:
            pos = _press_toward(io, cur, cell, step, battle)
            if pos[0] == cur and tuple(pos[1:3]) != step and dismiss is not None:
                dismiss()  # a guard's page, a "got on" line: turn it, then ask the step again
                pos = _press_toward(io, cur, cell, step, battle)
            if pos[0] != cur:
                return "detoured"
            if tuple(pos[1:3]) != step:
                # refused: a rock where the model said water, or "There's no place to get off!"
                # (measured at (7,88) on map 34) at a landing -- replan without that cell
                say(f"    refused {cell} -> {step}; replanning")
                blocked.add(step)
                break
            cell = step
    return "surfmoved-failed"


_FACES_DELTA = {v: k for k, v in _FACES.items()}


# Measured twice, on two different counters: a Pokemon Center nurse at (3,1) is talked to from
# (3,3) facing up, and the BIKE SHOP clerk at (6,2) from (4,2) facing right. The body sits two
# tiles away along one axis with the counter tile between, so NO cell is adjacent to it and a
# neighbour-only approach reports it unreachable -- which is exactly what happened when a recon
# leg stood in the shop holding the BIKE VOUCHER and logged "body (6,2) unreachable/no response".
COUNTER_SPAN = 2


def counter_stands(body: tuple[int, int]) -> list[tuple[tuple[int, int], str]]:
    """``[(cell, facing)]`` for talking to a body ACROSS a counter, two tiles away.

    ``center_counter`` hard-codes this geometry for the 14x8 tileset-6 Center interior. Nothing
    generalised it, so every other counter in the game -- shops, clerks, desks -- was invisible to
    a walk that only ever tries the four neighbouring tiles.
    """
    bx, by = body
    n = COUNTER_SPAN
    return [
        ((bx - n, by), "right"),
        ((bx + n, by), "left"),
        ((bx, by - n), "down"),
        ((bx, by + n), "up"),
    ]


def surf_cross(io, truth, pairs, cur: int, nxt: int, *, arm_surf, battle=_default_battle):
    """Cross a connection whose near edge has no walkable cell to stand on - i.e. water - and
    the A* cannot plan. A route (measured on 30/31/32: 5-8% walkable, a central land plaza with
    open water either side of it) traverses straight in its connection direction: SURF carries
    the water, walking carries the plaza, and arming SURF glues them. A refused step is the
    signal I am on the wrong side of the surf (facing water, not carrying it) - arm there, then
    verify. Once the route is refused where the model proposed it, the shore is asked before
    the leg is written "solid": edges of unequal height open as a BAND of rows (measured
    30->31: rows 40..52, approach at row 10, a solid notch in the approach column between),
    so the refusal replans the water route (``_water_cross``) instead of ending it.

    Returns True once the map changes to the far side, "detoured" when a step crossed an
    unintended edge (the ladder backtracks the state), "stuck-on-edge" / "surfmoved-failed"
    when the shore has refused every row (the ladder then bans and reroutes, so a bad line
    costs one hop rather than hanging)."""
    _, d = edge_cells(truth, cur, nxt)
    if not d:
        return "no-route"
    left = SURF_MAX_STEPS
    armed = False
    stand = shore_stand(truth, pairs, cur, nxt, read_pos(io)[1:])
    if stand is not None:
        # Not beside the water this crossing needs: go to the nearest shore cell that is, face
        # the water and arm there, before any straight-line step can carry us along the land.
        cell, face = stand
        walk(io, truth, pairs, cur, {cell}, battle=battle)
        io.press(face, hold=8, release=8)
        io.wait(30)
        if io.read(ADDR_IN_BATTLE) and battle:
            battle(io)  # a wild on the last shore step: fight it before the menu is asked for
            io.press(face, hold=8, release=8)
            io.wait(30)
        armed = arm_surf()
        for _ in range(3):
            io.press("a")
            io.wait(40)
        if not armed:
            r = _water_cross(io, truth, cur, nxt, d, battle)
            return "surfmoved-failed" if r is None else r
    if truth["maps"][str(cur)].get("tiles"):
        # A modelled shore is routed, not run straight: the straight line from the sea on Route 21
        # boards the land plaza and ends facing rock (measured 2026-09-05), while the water that
        # opens the north edge is a column six tiles west. Board from the shore if on land, BFS
        # the water to an edge cell, step out. The straight run below stays as the fallback.
        r = _water_cross(io, truth, cur, nxt, d, battle, pairs=pairs, arm_surf=arm_surf)
        if r is None and read_pos(io)[0] == cur and _hop_to_far_shore(io, truth, pairs, cur, nxt, d, arm_surf, battle):
            # ashore on the land whose far side touches the edge water (Route 20's island): board
            # there and route again
            r = _water_cross(io, truth, cur, nxt, d, battle, pairs=pairs, arm_surf=arm_surf)
        if r is not None:
            return r
        if read_pos(io)[0] != cur:
            io.wait(60)
            return True
    while left > 0:
        left -= 1
        if io.read(ADDR_IN_BATTLE) and battle:
            battle(io)
        mp, x, y = read_pos(io)
        if mp != cur:
            io.wait(60)
            return True
        before = (x, y)
        _step(io, d)
        if io.read(ADDR_IN_BATTLE) and battle:
            # A wild encounter CANCELS the step, so the position is unchanged - byte-for-byte
            # indistinguishable from a refusal unless the battle is checked for first. Reading
            # it as a refusal is what ended the badge-7 crossing last attempt: the leg armed
            # SURF into a battle (where the START menu does not open), re-stepped, saw no
            # movement and wrote "stuck-on-edge" in the middle of open water.
            battle(io)
            continue
        if read_pos(io)[0] != cur:
            io.wait(60)
            return True
        if read_pos(io)[1:] == before:
            # refused on this step. If SURF is not armed yet, arm it - the field-move menu is
            # only openable while walking, so the arm belongs on the last dry step, never mid
            # water - and give the same step one more try.
            if not armed:
                armed = arm_surf()
                for _ in range(3):
                    io.press("a")
                    io.wait(40)
                if not armed:
                    r = _water_cross(io, truth, cur, nxt, d, battle)
                    return "surfmoved-failed" if r is None else r
                _step(io, d)
                io.wait(45)
                if io.read(ADDR_IN_BATTLE) and battle:
                    battle(io)
                    continue
                if read_pos(io)[1:] != before:
                    continue  # the arm took; the route is open; keep going
            r = _water_cross(io, truth, cur, nxt, d, battle)
            return "stuck-on-edge" if r is None else r
    raise RuntimeError(f"surf_cross({cur}->{nxt}) spun {SURF_MAX_STEPS} steps without crossing")


def cut_facing(io, face: str) -> None:
    """The measured field-Cut flow: face the growth, START -> POKeMON -> lead -> CUT (row 0).

    The lead must know Cut - its field submenu then opens with CUT on row 0 (measured on
    Charmeleon and Charizard alike). Opens both cuttable tile classes: 0x3D bushes and
    0x50 trees.

    Cadence note: the menu phases here run at 60/25 frames, not the 15/45 that reads as "fast
    enough". `quartermaster` measured the shop dialog swallowing fixed-timing scripts, and
    `Rig.toss_stack` lost an evening to exactly that - the same presses freed a bag slot at 60
    and silently did nothing at 45, which the caller reported as the game refusing. Where a
    phase has a predicate, wait on the predicate; where it does not, be generous.
    """
    io.press(face)
    io.wait(25)
    io.press("start")
    io.wait(50)
    for _ in range(6):
        if io.read(ADDR_MENU_CUR) == 1:
            break
        io.press("down" if io.read(ADDR_MENU_CUR) < 1 else "up")
        io.wait(20)
    for _ in range(3):
        io.press("a")
        io.wait(60)
    for _ in range(5):
        io.press("b")
        io.wait(30)


def cut_until_open(io, truth, pairs, face: str, tries: int = 3) -> bool:
    """Cut, then *prove it* by stepping - the predicate the bare flow never had.

    ``cut_facing`` fires the menu and returns whether or not anything was cut. Callers then
    stepped hopefully and read a refusal as terrain. The step is the predicate: if we moved, the
    growth is gone; if not, cut again. The Vermilion yard bush regrows on map reload, so one
    attempt was never a safe assumption anyway.
    """
    delta = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[face]
    for _ in range(tries):
        before = read_pos(io)
        _step(io, face)
        if read_pos(io) != before:
            return True
        cut_facing(io, face)
        before = read_pos(io)
        _step(io, face)
        if read_pos(io) != before:
            return True
    _ = delta
    return False


def drive_to(io, truth, pairs, dst: int, *, battle=_default_battle, max_hops: int = 25, log=None) -> bool:
    """Follow rt.route hop by hop until ``dst``; gates, thresholds, and interiors handled."""
    import rom_truth as rt

    say = log or (lambda _msg: None)
    gate_tries: dict[int, int] = {}
    for _ in range(max_hops):
        cur = read_pos(io)[0]
        if cur == dst:
            return True
        chain = rt.route(truth, cur, dst)
        if not chain:
            say(f"no route {cur} -> {dst}")
            return False
        hop = chain[0]
        say(f"hop: {cur} --{hop['via']}--> {hop['to']}")
        if hop["via"] == "edge":
            r = cross_edge(io, truth, pairs, cur, hop["to"], battle=battle)
            if r == "no-path" and gate_tries.get(cur, 0) < 2:
                gate_tries[cur] = gate_tries.get(cur, 0) + 1
                cells, _d = edge_cells(truth, cur, hop["to"])
                if pass_gate(io, truth, pairs, cur, cells, battle=battle):
                    continue
        else:
            r = through_warp(io, truth, pairs, cur, hop["x"], hop["y"], battle=battle)
        now = read_pos(io)[0]
        if now == cur and r is not True:
            say(f"hop failed: {r}")
            return False
        if now not in (cur, hop["to"]):
            say(f"interior {now} swallowed the hop")
            r2 = traverse_interior(io, truth, pairs, now, battle=battle)
            if r2 is not True and read_pos(io)[0] == now:
                say(f"interior refused: {r2}")
                return False
    return read_pos(io)[0] == dst
