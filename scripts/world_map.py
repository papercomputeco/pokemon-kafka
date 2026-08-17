"""A persistent occupancy map the agent builds as it explores — so navigation isn't blind.

The agent only ever sees a 9x10 collision window around itself and used to forget it the instant
it moved, so every wall had to be re-discovered by local groping (which is why it could reach a
fence but never find the gap that's off-screen on the far side of town).

``WorldMap`` fixes that: because the player's absolute map coordinates are known every turn, each
collision window is *stamped* into a per-map grid at the right place, accumulating a real map of
each location as the agent walks. ``plan_step`` then runs A* over that accumulated grid toward a
target — routing around walls it has already seen and heading into unexplored space when the goal
is off-screen (unknown tiles are treated as walkable so the search is drawn toward the goal, and
self-corrects as new walls are observed).

Pure logic, fully unit-tested. No pixels, no external map data — just the walkability the game
already exposes, remembered.
"""

from __future__ import annotations

import heapq
import json
from collections import deque
from pathlib import Path

# Player is always at the centre of the 9x10 (rows x cols) collision window.
_PLAYER_ROW = 4
_PLAYER_COL = 4

# (name, dx, dy) — Pokemon Red overworld is y-down (up decreases y).
_DIRS = (("up", 0, -1), ("down", 0, 1), ("left", -1, 0), ("right", 1, 0))

_MAX_COORD = 255  # map-local coords fit in a byte; anything outside is off-map = blocked


class WorldMap:
    """Accumulated per-map walkability. ``cells[map_id][(x, y)]`` is 1 (walkable) or 0 (wall)."""

    def __init__(self) -> None:
        self.cells: dict[int, dict[tuple[int, int], int]] = {}
        # Tiles the agent *tried* to step onto but couldn't (ledges, map-edge non-exits, NPCs).
        # The collision grid reports these as walkable, so this hard-block is the only record that
        # they can't actually be entered. Unlike walls, though, some blocks are transient — a
        # wandering NPC's tile stays hard-blocked long after the NPC has moved on, and a stale
        # block can seal off a map exit (run 20260810-185357-7f79: blocks at (1,17)/(2,18) cut the
        # forest's left exit corridor). So each block carries a count of how many times ``observe``
        # has since seen the tile walkable (the occupant is gone); at ``block_expiry_observations``
        # the block is dropped and the tile becomes re-testable. A real ledge expires too, but its
        # re-test just fails twice and ``block`` re-arms it — a couple of wasted presses every N
        # sightings, in exchange for never permanently sealing a map on a transient occupant.
        self.blocked: dict[int, dict[tuple[int, int], int]] = {}
        self.block_expiry_observations: int = 25
        # Tiles where a wild encounter has fired (tall grass). Walkable, but the planner can be
        # asked to pay an extra ``encounter_cost`` to enter them so equal-ish paths prefer fewer
        # battles — learned from real encounters, like walls are learned from failed steps.
        self.encounters: dict[int, set[tuple[int, int]]] = {}
        # Each map's real size in walk-tiles (width, height), read from the game's own map
        # header when available. Near a map edge the collision window reads garbage beyond the
        # boundary — phantom "walkable" tiles that fed the planner fake exits (map 37's east
        # corridor, Route 2's rows below the south edge). Known bounds make them impossible:
        # observe() refuses to stamp beyond them and _passable() refuses to route there.
        self.bounds: dict[int, tuple[int, int]] = {}

    def observe(
        self, map_id: int, px: int, py: int, grid: list[list[int]], bounds: tuple[int, int] | None = None
    ) -> None:
        """Stamp a 9x10 collision ``grid`` (player at the centre) into the map at ``(px, py)``."""
        m = self.cells.setdefault(map_id, {})
        if bounds is not None:
            bw, bh = int(bounds[0]), int(bounds[1])
            # Bounds come from the map header — normally trustworthy, but a header read that is
            # stale (map transition) or otherwise wrong used to shrink Pewter gym (map 54) to
            # 10x14 while the agent stood at (16,17) and had already stamped walkable ground out
            # to (21,21): the whole east wing then read as "off-map", explore_step went blind, and
            # cross_step livelocked against the west-wall row. Observed cells are empirical proof
            # the map is at least that big, so never let a bounds read shrink below their extent.
            if m:
                bw = max(bw, max(x for x, _y in m) + 1)
                bh = max(bh, max(_y for _x, _y in m) + 1)
            self.bounds[map_id] = (bw, bh)
        bw, bh = self.bounds.get(map_id, (_MAX_COORD + 1, _MAX_COORD + 1))
        blocked = self.blocked.get(map_id)
        for r in range(min(9, len(grid))):
            row = grid[r]
            for c in range(min(10, len(row))):
                gx = px + (c - _PLAYER_COL)
                gy = py + (r - _PLAYER_ROW)
                if 0 <= gx < bw and 0 <= gy < bh:
                    m[(gx, gy)] = 1 if row[c] else 0
                    # A hard-blocked tile observed walkable again: its occupant may be gone.
                    # Count the sighting; at the expiry threshold, drop the block for a re-test.
                    if row[c] and blocked and (gx, gy) in blocked:
                        blocked[(gx, gy)] += 1
                        if blocked[(gx, gy)] >= self.block_expiry_observations:
                            del blocked[(gx, gy)]

    def block(self, map_id: int, x: int, y: int) -> None:
        """Record that ``(x, y)`` can't be entered (a move into it just failed). Re-blocking an
        expired tile starts a fresh expiry counter."""
        self.blocked.setdefault(map_id, {})[(x, y)] = 0

    def drop_stale_blocks(self, map_id: int, min_seen: int = 1) -> int:
        """Drop every hard-block that observation has since contradicted; returns how many.

        A hard-block records "a real move into this tile failed twice" — but when the blocker was
        a wandering NPC, the tile is open again and every later ``observe`` that sees it walkable
        increments its counter. Normally the block expires at ``block_expiry_observations``
        sightings, but expiry only ticks while the tile stays in view: block a choke tile, walk
        away, and it never expires. When the choke is the map's only exit corridor, the whole goal
        becomes unreachable — Viridian Forest's bug catcher got both (1,17) and (2,18) blocked,
        sealing the single passage to the (2,0) north exit, and the agent two-cycled at (25,21)
        for the rest of the run. Callers that have *exhausted* the map (goal unreachable even
        optimistically AND no frontier left to explore) call this to retest every block the world
        has since reported walkable at least ``min_seen`` times; a still-real blocker simply
        re-blocks after two failed presses, so a wrong drop costs a couple of steps, never a wedge.
        Blocks never seen walkable again (real ledges/trees, or an NPC still standing there) are
        kept — dropping those would just replay the failed presses."""
        blocked = self.blocked.get(map_id)
        if not blocked:
            return 0
        stale = [t for t, seen in blocked.items() if seen >= min_seen]
        for t in stale:
            del blocked[t]
        return len(stale)

    def mark_encounter(self, map_id: int, x: int, y: int) -> None:
        """Record that stepping onto ``(x, y)`` triggered a wild encounter (tall grass)."""
        self.encounters.setdefault(map_id, set()).add((x, y))

    def is_encounter_tile(self, map_id: int, x: int, y: int) -> bool:
        """Has a wild encounter fired on ``(x, y)`` before?"""
        return (x, y) in self.encounters.get(map_id, ())

    # --- persistence: carry the accumulated map across runs --------------------

    def to_dict(self) -> dict:
        """JSON-able snapshot of the learned map (occupancy + hard-blocks + encounter tiles)."""
        return {
            "cells": {str(m): [[x, y, v] for (x, y), v in cells.items()] for m, cells in self.cells.items()},
            "blocked": {str(m): [[x, y, seen] for (x, y), seen in s.items()] for m, s in self.blocked.items()},
            "encounters": {str(m): [[x, y] for (x, y) in sorted(s)] for m, s in self.encounters.items()},
            "bounds": {str(m): [w, h] for m, (w, h) in self.bounds.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorldMap:
        """Rebuild a WorldMap from a :meth:`to_dict` snapshot."""
        wm = cls()
        for m, items in (data.get("cells") or {}).items():
            wm.cells[int(m)] = {(int(x), int(y)): int(v) for x, y, v in items}
        for m, items in (data.get("blocked") or {}).items():
            # Legacy files stored bare [x, y] pairs; newer ones append the expiry counter.
            wm.blocked[int(m)] = {(int(it[0]), int(it[1])): int(it[2]) if len(it) > 2 else 0 for it in items}
        for m, items in (data.get("encounters") or {}).items():
            wm.encounters[int(m)] = {(int(x), int(y)) for x, y in items}
        for m, wh in (data.get("bounds") or {}).items():
            wm.bounds[int(m)] = (int(wh[0]), int(wh[1]))
        return wm

    def save(self, path) -> None:
        """Persist the learned map to ``path`` (creating parent dirs)."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict()), encoding="utf-8")

    @classmethod
    def load(cls, path) -> WorldMap:
        """Load a learned map from ``path``; an empty map if it is missing or unreadable."""
        p = Path(path)
        if not p.is_file():
            return cls()
        try:
            return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return cls()

    def walkable(self, map_id: int, x: int, y: int, default: int = 1) -> int:
        """Known walkability of a tile, or ``default`` (treat unknown as walkable) if unseen."""
        if (x, y) in self.blocked.get(map_id, ()):
            return 0
        return self.cells.get(map_id, {}).get((x, y), default)

    def _passable(self, map_id: int, m: dict[tuple[int, int], int], x: int, y: int) -> bool:
        bw, bh = self.bounds.get(map_id, (_MAX_COORD + 1, _MAX_COORD + 1))
        if x < 0 or y < 0 or x >= bw or y >= bh:
            return False  # off the map's real edge (or the coordinate byte's range)
        if (x, y) in self.blocked.get(map_id, ()):
            return False  # tried and failed — never enter, even if the grid claims walkable
        return m.get((x, y), 1) != 0  # unknown -> passable (optimistic, draws search to the goal)

    def plan_step(
        self,
        map_id: int,
        px: int,
        py: int,
        tx: int,
        ty: int,
        max_nodes: int = 8000,
        encounter_cost: int = 0,
        require_reach: bool = False,
    ) -> str | None:
        """First step ("up"/"down"/"left"/"right") of an A* path from ``(px, py)`` to ``(tx, ty)``
        over the accumulated map. ``None`` only when already on the target. Falls back to a greedy
        step toward the goal if A* can't reach it within ``max_nodes``.

        ``encounter_cost`` (>= 0) is added to the g-cost of entering a known encounter tile, so the
        planner prefers fewer-grass routes among comparable paths without treating grass as a wall.

        ``require_reach=True`` returns ``None`` instead of the fallback when A* did not actually
        reach the goal. The fallback is memoryless — replanned from scratch each turn, its
        closest-seen/greedy target depends on the tile the agent happens to stand on, and when the
        goal is sealed behind observed walls that flips between two adjacent tiles forever (the
        navigation-thrash wedge). Callers with a better "goal unreachable" move (frontier
        exploration) pass this flag so they get the chance to make it.
        """
        if (px, py) == (tx, ty):
            return None
        m = self.cells.get(map_id, {})
        grass = self.encounters.get(map_id, ())
        start, goal = (px, py), (tx, ty)
        openh: list[tuple[int, int, tuple[int, int]]] = [(abs(px - tx) + abs(py - ty), 0, start)]
        came: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        gscore: dict[tuple[int, int], int] = {start: 0}
        nodes = 0
        reached = None
        best = start  # closest-to-goal node seen, for the unreachable fallback
        best_h = abs(px - tx) + abs(py - ty)
        while openh and nodes < max_nodes:
            _, g, cur = heapq.heappop(openh)
            nodes += 1
            if cur == goal:
                reached = goal
                break
            ch = abs(cur[0] - tx) + abs(cur[1] - ty)
            if ch < best_h:
                best_h, best = ch, cur
            cx, cy = cur
            for _name, dx, dy in _DIRS:
                nb = (cx + dx, cy + dy)
                if nb == goal:
                    # A path may end on its goal even if the collision grid stamped it a wall — a
                    # warp/door (the forest exit) reads as impassable but is steppable. Still honor
                    # map bounds and hard-blocks (tiles a real move already failed on).
                    if (
                        nb[0] < 0
                        or nb[1] < 0
                        or nb[0] > _MAX_COORD
                        or nb[1] > _MAX_COORD
                        or nb in self.blocked.get(map_id, ())
                    ):
                        continue
                elif not self._passable(map_id, m, nb[0], nb[1]):
                    continue
                ng = g + 1 + (encounter_cost if nb in grass else 0)
                if nb not in gscore or ng < gscore[nb]:
                    gscore[nb] = ng
                    came[nb] = cur
                    heapq.heappush(openh, (ng + abs(nb[0] - tx) + abs(nb[1] - ty), ng, nb))
        if require_reach and reached is None:
            return None
        end = reached if reached is not None else best
        step = self._first_step(came, start, end)
        if step is None:
            return self._greedy(map_id, m, px, py, tx, ty)
        return self._dir(px, py, step)

    def cross_step(self, map_id: int, px: int, py: int, goal: str, max_nodes: int = 6000) -> str:
        """Step that drives the agent off the map in cardinal ``goal`` ("north"/"south").

        One BFS picks a *pressable* destination — a tile whose forward press could still be the
        way out: off the edge row, into unexplored ground, or into a boundary-row "wall" that has
        never actually been tried (exit warps read as walls in the collision grid, so the only
        way to tell them apart is one press; failing it twice hard-blocks the tile and retires
        the candidate for good). Known-open floor ahead is deliberately NOT a destination by
        itself: steering by "the tile ahead is enterable" is what wedged map 37 (issue #64) —
        the (2,1) pocket is enterable from (2,2) but leads nowhere, so the old local fast path
        and the global sweep disagreed and the agent two-cycled between the two tiles for tens
        of thousands of turns. Because every candidate press either moves the agent or (via the
        caller's failed-move hard-blocks) permanently shrinks the candidate set, successive
        calls always make progress instead of looping.

        Candidates that gain ground toward the edge are preferred (nearest first); failing
        that, the nearest candidate anywhere, then frontier exploration, then a forward nudge."""
        m = self.cells.get(map_id, {})
        sign = -1 if goal == "north" else 1
        fwd = "up" if goal == "north" else "down"
        blocked = self.blocked.get(map_id, ())
        # The known row nearest the target edge: warps sit on the map boundary, so stamped
        # "walls" are only worth pressing there — never interior furniture/tree rows.
        edge_y = (min if sign < 0 else max)(y for _x, y in m) if m else None

        last_y = self.bounds.get(map_id, (0, _MAX_COORD + 1))[1] - 1  # the map's real last row

        def pressable(cx: int, cy: int) -> bool:
            """Could pressing ``fwd`` from (cx, cy) still be the way off the map?"""
            f = (cx, cy + sign)
            if f in blocked:
                return False  # pressed twice and failed — proven impassable, retired
            if f[1] < 0 or f[1] > last_y:
                return True  # pressing off the edge row IS the crossing on outdoor maps
            v = m.get(f)
            if v is None:
                return True  # unexplored — could be open ground or the exit
            return v == 0 and f[1] == edge_y  # a boundary "wall" may be a warp

        start = (px, py)

        def sweep(candidate) -> str | None:
            """First step toward the nearest ``candidate`` tile, preferring ones whose press
            lands past the current row. Returns None when none is reachable."""
            came: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
            q = deque([start])
            nodes = 0
            target = None
            backup = None  # nearest candidate that doesn't gain ground, kept as plan B
            while q and nodes < max_nodes:
                cur = q.popleft()
                nodes += 1
                cx, cy = cur
                if cur != start and candidate(cx, cy):
                    if (cy + sign - py) * sign > 0:  # its press lands past our current row
                        target = cur
                        break
                    if backup is None:
                        backup = cur
                for _name, dx, dy in _DIRS:
                    nb = (cx + dx, cy + dy)
                    # Sweep only over ground *known* walkable (and really on the map):
                    # unknown tiles are probe targets (the forward press), never corridors.
                    # Optimistic traversal let the BFS wrap around a real border wall through
                    # the unstamped void and "gain ground" in fantasy space (the Pallet<->
                    # Route 1 flap), and phantom stamps beyond recorded bounds are just as fake.
                    if nb in came or m.get(nb) != 1 or not self._passable(map_id, m, nb[0], nb[1]):
                        continue
                    came[nb] = cur
                    q.append(nb)
            step = self._first_step(came, start, target if target is not None else backup)
            return step and self._dir(px, py, step)

        if pressable(px, py):
            return fwd  # the press right here may be the exit — try it before sweeping
        d = sweep(pressable)
        if d:
            return d
        # No pressable candidate reachable: map the frontier instead of mashing into a wall.
        d = self.explore_step(map_id, px, py, max_nodes=max_nodes)
        if d:
            return d

        # Fully mapped, every probe retired, and still on the map: the way forward must be a
        # door warp in an *interior* wall — building doors sit rows away from the sweep's edge
        # row (Route 2's forest-gate door is above the (3,43) mat, mid-map). Probe untried
        # walls: each press either warps through a door or hard-blocks after two fails and
        # retires the tile, so this tier provably shrinks to nothing instead of looping.
        def untried_wall(cx: int, cy: int) -> bool:
            f = (cx, cy + sign)
            return f not in blocked and m.get(f) == 0

        if untried_wall(px, py):
            return fwd
        d = sweep(untried_wall)
        if d:
            return d
        # Livelock break (issue #70, Pewter gym): the old tail `or fwd` re-bumped a tile every other
        # layer had already rejected (a dead wall, or an un-ready NPC such as the locked gym leader).
        # Pressing it does not move the agent, so next turn the position and the map are identical
        # and this function returns the same direction — 23,876 turns of it. Nothing upstream can
        # break that: `stuck_turns` counted every one of those turns (max_stuck_streak=23876) but it
        # is only consulted by the *waypoint* navigator's skip rule; cross_step is never passed it.
        # A decision loop with no input that changes has to break itself. With every layer exhausted,
        # retreat laterally or backward (a step that at least changes the position, so the next
        # sweep sees something new) rather than re-bumping the retired tile. The pure `return fwd`
        # remains only for the truly boxed-in case where every neighbour is hard-blocked too.
        bset = self.blocked.get(map_id, {})
        if (px, py + sign) not in bset:
            # The forward tile is not a known dead end (it may be a normal walkable step): keep the
            # old nudge-forward behaviour.
            return fwd
        # Forward is retired, and every other layer found nothing: retreat laterally or backward
        # (a walkable step at least) instead of re-bumping the dead tile — that bump was the
        # Pewter-gym livelock.
        if goal == "north":
            order = (_DIRS[3], _DIRS[2], _DIRS[1])  # right, left, back (down)
        else:
            order = (_DIRS[2], _DIRS[3], _DIRS[0])  # left, right, back (up)
        for name, dx, dy in order:
            if (px + dx, py + dy) not in bset:
                return name
        return fwd

    def known_reachable(self, map_id: int, px: int, py: int, tx: int, ty: int) -> bool:
        """Can ``(tx, ty)`` be reached from ``(px, py)`` over tiles *known* to be walkable?

        Strict (unlike :meth:`plan_step`'s optimism): unknown tiles do NOT count. Used to decide
        whether to commit to the goal or keep exploring — heading for a goal that is only
        ``optimistically`` reachable is what makes the agent oscillate against a wall."""
        if (px, py) == (tx, ty):
            return True
        m = self.cells.get(map_id, {})
        blocked = self.blocked.get(map_id, ())
        seen = {(px, py)}
        q = deque([(px, py)])
        while q:
            cx, cy = q.popleft()
            for _name, dx, dy in _DIRS:
                nb = (cx + dx, cy + dy)
                if nb in seen or nb in blocked:
                    continue
                if nb == (tx, ty):
                    # The goal counts as reachable even if the collision grid stamped it a wall: a
                    # warp/door (the forest exit at (2,0)) reads as impassable but is steppable. A
                    # hard-block (checked above) is the only thing that bars entering the goal.
                    return True
                if m.get(nb, 0) != 1:
                    continue
                seen.add(nb)
                q.append(nb)
        return False

    def explore_step(self, map_id: int, px: int, py: int, max_nodes: int = 8000) -> str | None:
        """First step toward the nearest *unexplored* tile, so the agent maps new ground instead of
        oscillating against an unreachable goal. BFS over passable tiles (unknown counts as
        passable); the first unknown tile reached is the frontier. ``None`` when nothing reachable
        is still unknown (the area is fully mapped)."""
        m = self.cells.get(map_id, {})
        blocked = self.blocked.get(map_id, ())
        start = (px, py)
        came: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        q = deque([start])
        nodes = 0
        while q and nodes < max_nodes:
            cur = q.popleft()
            nodes += 1
            # A frontier: a passable tile we have never observed (not in the occupancy map).
            if cur != start and cur not in m and cur not in blocked:
                step = self._first_step(came, start, cur)
                return self._dir(px, py, step) if step else None
            cx, cy = cur
            for _name, dx, dy in _DIRS:
                nb = (cx + dx, cy + dy)
                if nb in came or not self._passable(map_id, m, nb[0], nb[1]):
                    continue
                came[nb] = cur
                q.append(nb)
        return None

    @staticmethod
    def _first_step(came, start, end):
        """The tile adjacent to ``start`` along the reconstructed path to ``end`` (or None)."""
        if end == start or end not in came:
            return None
        node = end
        while came.get(node) not in (None, start):
            node = came[node]
        return node if came.get(node) == start else None

    @staticmethod
    def _dir(px: int, py: int, nxt: tuple[int, int]) -> str | None:
        dx, dy = nxt[0] - px, nxt[1] - py
        if dx > 0:
            return "right"
        if dx < 0:
            return "left"
        if dy > 0:
            return "down"
        if dy < 0:
            return "up"
        return None

    def _greedy(self, map_id, m, px, py, tx, ty) -> str:
        """Step toward the target along an open neighbour, minimising remaining distance."""
        best_dir, best_score = "up", None
        for name, dx, dy in _DIRS:
            nx, ny = px + dx, py + dy
            if not self._passable(map_id, m, nx, ny):
                continue
            score = abs(nx - tx) + abs(ny - ty)
            if best_score is None or score < best_score:
                best_score, best_dir = score, name
        return best_dir
