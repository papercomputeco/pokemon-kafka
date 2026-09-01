"""The road engine: drive to any map over the extracted graph, one measured lesson at a time.

This is the badge-4 expedition's driver, promoted from probe to engine. Every mechanism in it
was learned by playing:

- **Thresholds.** Warp tiles do not all fire on arrival. Ladders fire on ENTRY (step off, step
  back on); gate doors fire on the step THROUGH them (Route 11's west door fires on the
  eastward step). ``through_warp`` tries every direction and undoes plain steps.
- **Gates sever routes.** A route's edge cells can be unreachable because its gate building
  cuts the map in half. ``pass_gate`` goes through the building — and a candidate door only
  counts if the far side can actually path to the goal (Route 11's Diglett house taught that
  the nearest door is not always the gate).
- **Edges are offset.** The neighbor's grid does not align with every edge cell (the
  connection header carries an offset the extraction does not), so ``cross_edge`` sweeps the
  outward step across open edge cells until one hands over.
- **Interiors are traversed by sides.** A gate entered on one side exits by the mats on
  another; non-edge warps (a 2F stairway) are never exits.
- **Stalls are not refusals.** A stalled step with a textbox up is usually a trainer's
  pre-battle speech — A leads into the fight and the injected battle handler owns it. The
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
# up — spin arrows, teleport pads — so a planned path is a category error there and the engine's
# own answer is the facing-keyed oracle. Read from the map, never assumed.
FACILITY_TILESET = 22

_OPPOSITE = {"down": "up", "up": "down", "right": "left", "left": "right"}
_OUTWARD = {"west": "left", "east": "right", "north": "up", "south": "down"}


def _default_battle(io) -> None:
    raise QuartermasterError("road: a battle started and no battle handler was injected")


def live_bodies(io) -> set[tuple[int, int]]:
    """Positions of every live sprite — a beaten trainer still stands, and paths route around."""
    out = set()
    for i in range(1, 16):
        if io.read(SPRITE_STATE_BASE + i * 0x10):
            out.add((io.read(SPRITE_DATA_BASE + i * 0x10 + 5) - 4, io.read(SPRITE_DATA_BASE + i * 0x10 + 4) - 4))
    return out


def _step(io, direction: str) -> None:
    io.press(direction, hold=8, release=8)
    io.wait(30)


def reachable(truth, pairs, map_id: int, start, blocked=()) -> set[tuple[int, int]]:
    """Every cell reachable from ``start`` on this map, treating ``blocked`` cells as solid."""
    from collections import deque

    import rom_truth as rt

    m = truth["maps"][str(map_id)]
    w, h = m["width"], m["height"]
    blocked = set(blocked)
    seen = {tuple(start)}
    queue = deque([tuple(start)])
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if not (0 <= nx < w and 0 <= ny < h) or (nx, ny) in seen or (nx, ny) in blocked:
                continue
            if m["grid"][ny][nx] != "1" or not rt.passable(m, pairs, x, y, nx, ny):
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return seen


def walkable(truth, pairs, map_id: int, start, bodies=(), keep=()) -> set[tuple[int, int]]:
    """The cells ``walk`` can actually deliver us to: bodies *and* every warp tile are walls.

    ``reachable`` answers a terrain question and ``walk`` answers a movement one, and inside a
    facility the two disagree wildly — because ``walk`` refuses to thread a door tile as floor
    (a pad fires the moment you step on it, so a route "through" one is a route off the floor).
    Silph 5F is the measurement: the corridor holding the CARD KEY is *reachable* from anywhere
    on the floor, and the only path to it crosses the teleport pad at (27,3). Every approach that
    trusted ``reachable`` was refused live, on both of the two sessions that hunted that key,
    with no sentence on screen to explain it. Ride the pad and the same corridor is nine steps.

    ``keep`` are warp tiles that stay open — the targets of the walk itself, which ``walk``
    excludes from its own warp block for the same reason.
    """
    warps = {(w[0], w[1]) for w in truth["maps"][str(map_id)]["warps"]} - set(keep)
    return reachable(truth, pairs, map_id, start, set(bodies) | warps)


def pads_reaching(truth, pairs, map_id: int, targets, bodies=()) -> list[tuple[tuple[int, int], int]]:
    """``(pad, the map it pairs with)`` for every warp tile on this map that *stands* inside a
    region holding ``targets`` — the ride hidden behind a bare "could not reach".

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
    pocket that is itself behind card-key doors — so the useful question is never "which pad is
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
                hops = 1
            else:
                continue
            found.append({"from_map": int(src), "door": (wx, wy), "lands": lands, "hops": hops})
    found.sort(key=lambda r: (r["hops"], r["from_map"], r["door"]))
    return [r for r in found if r["door"] not in direct or r["from_map"] != map_id]


def ride_pad(io, truth, pairs, map_id: int, targets, *, battle=_default_battle):
    """Reach ``targets`` by riding a pad that stands in their region and stepping off its far side.

    The capability every Silph leg was missing. ``walk`` treats a pad as a wall — correctly, since
    stepping on one fires it — so a region whose only entrance *is* a pad is unreachable to it, and
    the leg reports "could not reach" with nothing on screen to explain why. Measured on 5F: from
    (26,3) a step east fires the pad at (27,3) and lands on 7F (21,15); step off it and back on and
    we return **standing on (27,3)**, inside the region the walk could never enter, with (28,3) one
    step away. Same tiles, same engine; the only difference is riding rather than routing.

    The round trip matters: arriving on a pad does not re-fire it, so the far side is left and
    re-entered to come back. Returns True when we end on ``map_id`` inside the target region.
    """
    import rom_truth as rt

    for pad, _dest in pads_reaching(truth, pairs, map_id, targets, live_bodies(io)):
        if walk(io, truth, pairs, map_id, {pad}, battle=battle) not in (True, "map-change"):
            continue
        mp, x, y = read_pos(io)
        if mp == map_id:  # the pad did not fire on arrival — a threshold, so step onto it again
            _step(io, "right")
            mp, x, y = read_pos(io)
        if mp == map_id:
            continue  # not a pad we can ride; try the next one
        # On the far side, standing on its warp tile: step off, then back on, to come home.
        far = truth["maps"][str(mp)]
        for direction, (dx, dy) in (("down", (0, 1)), ("up", (0, -1)), ("left", (-1, 0)), ("right", (1, 0))):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < far["width"] and 0 <= ny < far["height"]):
                continue
            if far["grid"][ny][nx] != "1" or not rt.passable(far, pairs, x, y, nx, ny):
                continue
            _step(io, direction)
            if read_pos(io)[1:] != (nx, ny):
                continue  # a body or a script ate the step; try another side
            _step(io, {"down": "up", "up": "down", "left": "right", "right": "left"}[direction])
            if read_pos(io)[0] == map_id:
                return walk(io, truth, pairs, map_id, targets, battle=battle) is True
            break
    return False


def gate_doors(truth, map_id: int) -> set[tuple[int, int]]:
    """The doors on this map that belong to a gate building rather than a dead-end house.

    Measurable signature, no recall needed: a building you can *pass through* is entered from
    this map by two or more doors (Route 12's gate is (10,15), (11,15) and (10,21), all into map
    87 — two doors on the north side of the severance and one on the south). A house is entered
    by exactly one. ``pass_gate`` aims at the nearest door first and Route 11's Diglett house
    taught what that costs; this is the same lesson as a lookup.
    """
    by_dest: dict[int, set[tuple[int, int]]] = {}
    for wx, wy, dst, _wid in truth["maps"].get(str(map_id), {}).get("warps", []):
        by_dest.setdefault(dst, set()).add((wx, wy))
    return {door for doors in by_dest.values() if len(doors) > 1 for door in doors}


def blocking_body(truth, pairs, map_id: int, start, targets, bodies):
    """The one body whose removal reconnects ``targets`` — the wall, not the bump.

    ``walk`` reports the body it bumped into. That is often not the body that matters. Measured
    on Route 12: the step north was refused by a trainer at (14,76) that column 15 walks straight
    around, while the actual severance was a single sprite at (10,62) fifteen tiles away — one
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
    side = next(k for k, v in m.get("connections", {}).items() if v == nxt)
    if side in ("north", "south"):
        row = 0 if side == "north" else m["height"] - 1
        return {(x, row) for x in range(m["width"]) if m["grid"][row][x] == "1"}, _OUTWARD[side]
    col = 0 if side == "west" else m["width"] - 1
    return {(col, y) for y in range(m["height"]) if m["grid"][y][col] == "1"}, _OUTWARD[side]


def walk(io, truth, pairs, map_id: int, targets, *, battle=_default_battle, cap: int = 500, avoid_warps: bool = True):
    """BFS-walk toward the nearest target; battles are the handler's, stalls get A/B cycles.

    ``avoid_warps`` (the standing doctrine: never thread a door tile as floor) blocks every
    non-target warp tile — measured here when a walk to a gate door was swallowed en route
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
        path = rt.path_on_map(truth, pairs, map_id, (x, y), targets, blocked=live_bodies(io) | warp_block)
        if not path or len(path) < 2:
            path = rt.path_on_map(truth, pairs, map_id, (x, y), targets, blocked=warp_block)
            if not path or len(path) < 2:
                return "no-path"
            if tuple(path[1]) in live_bodies(io):
                # Bodies are not walls: wanderers move — wait them out before giving up
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

    With ``exclude_entry=False`` the entry side is allowed too — the retreat a gate-passer
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
        r = walk(io, truth, pairs, interior, set(sides[side]), cap=80, battle=battle)
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
            # Only failure to leave AT ALL is a guard holding us — the finding is on screen.
            if traverse_interior(io, truth, pairs, interior, battle=battle, exclude_entry=False) is not True:
                return False
            continue
        if r2 is True and read_pos(io)[0] == cur:
            _, nx, ny = read_pos(io)
            if rt.path_on_map(truth, pairs, cur, (nx, ny), set(goal_cells)):
                return True


def cross_edge(io, truth, pairs, cur: int, nxt: int, *, battle=_default_battle):
    """Cross a map connection, sweeping the outward step across edge cells for alignment."""
    cells, d = edge_cells(truth, cur, nxt)
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


def cut_facing(io, face: str) -> None:
    """The measured field-Cut flow: face the growth, START -> POKeMON -> lead -> CUT (row 0).

    The lead must know Cut — its field submenu then opens with CUT on row 0 (measured on
    Charmeleon and Charizard alike). Opens both cuttable tile classes: 0x3D bushes and
    0x50 trees.

    Cadence note: the menu phases here run at 60/25 frames, not the 15/45 that reads as "fast
    enough". `quartermaster` measured the shop dialog swallowing fixed-timing scripts, and
    `Rig.toss_stack` lost an evening to exactly that — the same presses freed a bag slot at 60
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
    """Cut, then *prove it* by stepping — the predicate the bare flow never had.

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
