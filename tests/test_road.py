"""The road engine, driven through a scripted world.

Every mechanism ported from the badge-4 expedition is exercised against a FakeIO whose
d-pad presses move the player over truth-shaped grids, with warp behavior scripted per
test: entry warps fire on arrival, thresholds fire on the directional step through, and
misaligned edges hand over only at their true crossing cells."""

import pytest
import quartermaster as qm
import road


def _map(grid, connections=None, warps=None):
    return {
        "width": len(grid[0]),
        "height": len(grid),
        "grid": grid,
        "tileset": 1,  # ledges are an overworld-tileset mechanism; keep them out of these tests
        "connections": connections or {},
        "warps": warps or [],
        "sprites": [],
    }


class RoadIO:
    """Presses mutate the same registers the engine reads: d-pads move over the grid,
    arrival warps and threshold warps teleport, and a `frozen` flag models an input-eating
    screen (a guard, a lingering box)."""

    def __init__(self, truth, start, arrive=None, thresholds=None, frozen_at=None):
        self.truth = truth
        self.mem = {qm.ADDR_MAP: start[0], qm.ADDR_X: start[1], qm.ADDR_Y: start[2]}
        self.arrive = arrive or {}  # (map,x,y) -> (map,x,y): fires when stepped onto
        self.thresholds = thresholds or {}  # (map,x,y,dir) -> (map,x,y): fires stepping off
        self.frozen_at = frozen_at or set()  # (map,x,y): d-pads are eaten while standing here
        self.pressed = []

    def _tp(self, dest):
        self.mem[qm.ADDR_MAP], self.mem[qm.ADDR_X], self.mem[qm.ADDR_Y] = dest

    def press(self, btn, hold=8, release=8):
        self.pressed.append(btn)
        if btn not in ("up", "down", "left", "right"):
            return
        mp, x, y = qm.read_pos(self)
        if (mp, x, y) in self.frozen_at:
            return
        th = self.thresholds.get((mp, x, y, btn))
        if th:
            self._tp(th)
            return
        dx, dy = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}[btn]
        nx, ny = x + dx, y + dy
        m = self.truth["maps"][str(mp)]
        if not (0 <= nx < m["width"] and 0 <= ny < m["height"]) or m["grid"][ny][nx] != "1":
            return
        self._tp(self.arrive.get((mp, nx, ny), (mp, nx, ny)))

    def wait(self, frames=30):
        pass

    def read(self, addr):
        return self.mem.get(addr, 0)


PAIRS: set = set()


# --------------------------------------------------------------------------- edge_cells / bodies


def test_edge_cells_all_four_sides():
    truth = {
        "maps": {
            "1": _map(["111", "111", "101"], connections={"north": 2, "south": 3, "west": 4, "east": 5}),
        }
    }
    assert road.edge_cells(truth, 1, 2) == ({(0, 0), (1, 0), (2, 0)}, "up")
    assert road.edge_cells(truth, 1, 3) == ({(0, 2), (2, 2)}, "down")
    assert road.edge_cells(truth, 1, 4) == ({(0, 0), (0, 1), (0, 2)}, "left")
    assert road.edge_cells(truth, 1, 5) == ({(2, 0), (2, 1), (2, 2)}, "right")


def test_live_bodies_reads_the_sprite_table():
    io = RoadIO({"maps": {}}, (0, 0, 0))
    io.mem[road.SPRITE_STATE_BASE + 0x10] = 1
    io.mem[road.SPRITE_DATA_BASE + 0x10 + 4] = 7 + 4  # y
    io.mem[road.SPRITE_DATA_BASE + 0x10 + 5] = 3 + 4  # x
    assert road.live_bodies(io) == {(3, 7)}


# --------------------------------------------------------------------------- walk


def _open_world(w=6, h=1, **kw):
    return {"maps": {"1": _map(["1" * w] * h, **kw)}}


def test_walk_arrives():
    io = RoadIO(_open_world(), (1, 0, 0))
    assert road.walk(io, io.truth, PAIRS, 1, {(4, 0)}) is True
    assert qm.read_pos(io) == (1, 4, 0)


def test_walk_reports_map_change():
    io = RoadIO(_open_world(), (1, 0, 0), arrive={(1, 2, 0): (9, 5, 5)})
    assert road.walk(io, io.truth, PAIRS, 1, {(4, 0)}) == "map-change"


def test_walk_no_path_and_body_blocked():
    truth = {"maps": {"1": _map(["101"])}}
    io = RoadIO(truth, (1, 0, 0))
    assert road.walk(io, truth, PAIRS, 1, {(2, 0)}) == "no-path"
    io2 = RoadIO(_open_world(w=3), (1, 0, 0))
    io2.mem[road.SPRITE_STATE_BASE + 0x10] = 1
    io2.mem[road.SPRITE_DATA_BASE + 0x10 + 4] = 0 + 4
    io2.mem[road.SPRITE_DATA_BASE + 0x10 + 5] = 1 + 4
    assert road.walk(io2, io2.truth, PAIRS, 1, {(2, 0)}) == "body-blocked"


def test_walk_delegates_battles_and_finishes():
    io = RoadIO(_open_world(), (1, 0, 0))
    io.mem[qm.ADDR_IN_BATTLE] = 1
    fought = []

    def battle(io_):
        fought.append(True)
        io_.mem[qm.ADDR_IN_BATTLE] = 0

    assert road.walk(io, io.truth, PAIRS, 1, {(3, 0)}, battle=battle) is True
    assert fought == [True]


def test_walk_without_a_handler_refuses_to_guess():
    io = RoadIO(_open_world(), (1, 0, 0))
    io.mem[qm.ADDR_IN_BATTLE] = 1
    with pytest.raises(qm.QuartermasterError, match="no battle handler"):
        road.walk(io, io.truth, PAIRS, 1, {(3, 0)})


def test_walk_stall_cycles_then_refused():
    """An input-eating screen: A/B cycles fire, and only persistent immobility refuses."""
    io = RoadIO(_open_world(), (1, 1, 0), frozen_at={(1, 1, 0)})
    assert road.walk(io, io.truth, PAIRS, 1, {(4, 0)}) == "refused"
    assert io.pressed.count("a") == 12  # 4 cycles x 3 A-presses
    assert "b" in io.pressed


def test_walk_stall_speech_leads_into_the_fight():
    """The trainer-speech shape: frozen until an A opens the battle, which the handler wins."""
    io = RoadIO(_open_world(), (1, 1, 0), frozen_at={(1, 1, 0)})
    orig = io.press

    def press(btn, hold=8, release=8):
        if btn == "a":
            io.mem[qm.ADDR_IN_BATTLE] = 2
        orig(btn, hold, release)

    io.press = press

    def battle(io_):
        io_.mem[qm.ADDR_IN_BATTLE] = 0
        io_.frozen_at = set()  # the fight over, the road is open

    assert road.walk(io, io.truth, PAIRS, 1, {(4, 0)}, battle=battle) is True


def test_walk_cap():
    io = RoadIO(_open_world(), (1, 0, 0), frozen_at={(1, 0, 0)})
    assert road.walk(io, io.truth, PAIRS, 1, {(4, 0)}, cap=3) == "cap"


# --------------------------------------------------------------------------- warps


def test_through_warp_fires_on_arrival():
    io = RoadIO(_open_world(), (1, 0, 0), arrive={(1, 3, 0): (7, 1, 1)})
    assert road.through_warp(io, io.truth, PAIRS, 1, 3, 0) is True
    assert qm.read_pos(io)[0] == 7


def test_through_warp_threshold_fires_on_the_step_through():
    """Route 11's gate door: standing on the tile does nothing; the deeper step fires."""
    truth = _open_world(w=4)
    io = RoadIO(truth, (1, 0, 0), thresholds={(1, 3, 0, "right"): (7, 0, 5)})
    assert road.through_warp(io, io.truth, PAIRS, 1, 3, 0) is True
    assert qm.read_pos(io)[0] == 7


def test_through_warp_ladder_fires_on_reentry():
    """The Rock Tunnel ladder: step off, and the step BACK onto the tile fires."""
    truth = _open_world(w=4)
    io = RoadIO(truth, (1, 2, 0))
    # walking onto (3,0) as a target does not fire; stepping right is walled; the undo of a
    # successful left step re-enters the tile, which now fires.
    fired = {"armed": False}
    orig_tp = io._tp

    def tp(dest):
        if dest == (1, 3, 0) and fired["armed"]:
            orig_tp((7, 9, 9))
        else:
            fired["armed"] = dest == (1, 2, 0)
            orig_tp(dest)

    io._tp = tp
    assert road.through_warp(io, io.truth, PAIRS, 1, 3, 0) is True
    assert qm.read_pos(io)[0] == 7


def test_through_warp_dead_and_walk_failure_passthrough():
    io = RoadIO({"maps": {"1": _map(["0001"])}}, (1, 3, 0))
    assert road.through_warp(io, io.truth, PAIRS, 1, 3, 0) == "warp-dead"
    io2 = RoadIO({"maps": {"1": _map(["101"])}}, (1, 0, 0))
    assert road.through_warp(io2, io2.truth, PAIRS, 1, 2, 0) == "no-path"


# --------------------------------------------------------------------------- interiors and gates


GATE = _map(["111"] * 3, warps=[[0, 1, 255, 0], [2, 1, 255, 1]])


def test_traverse_interior_exits_the_far_side():
    truth = {"maps": {"8": GATE}}
    io = RoadIO(truth, (8, 0, 1), thresholds={(8, 2, 1, "right"): (1, 5, 0)})
    assert road.traverse_interior(io, truth, PAIRS, 8) is True
    assert qm.read_pos(io)[0] == 1


def test_traverse_interior_north_south_mats():
    """A vertical gate: entered by the south mats, exited by the north (mat rows classify)."""
    tall = _map(["111"] * 4, warps=[[1, 0, 255, 0], [1, 3, 255, 1]])
    truth = {"maps": {"8": tall}}
    io = RoadIO(truth, (8, 1, 3), thresholds={(8, 1, 0, "up"): (2, 4, 4)})
    assert road.traverse_interior(io, truth, PAIRS, 8) is True
    assert qm.read_pos(io) == (2, 4, 4)


def test_traverse_interior_map_change_and_unknown_and_stuck():
    truth = {"maps": {"8": GATE}}
    io = RoadIO(truth, (8, 0, 1), arrive={(8, 2, 1): (1, 5, 0)})
    assert road.traverse_interior(io, truth, PAIRS, 8) is True
    assert road.traverse_interior(RoadIO(truth, (8, 0, 1)), truth, PAIRS, 99) == "unknown-interior"
    io3 = RoadIO(truth, (8, 0, 1))  # far mat reachable but nothing ever fires
    assert road.traverse_interior(io3, truth, PAIRS, 8) == "interior-stuck"


def _gate_world():
    """A route severed mid-map: west half, wall, east half; a decoy house and a real gate."""
    route = _map(
        ["1111011", "1111011"],
        connections={"east": 3},
        warps=[[1, 0, 60, 0], [3, 0, 8, 0], [3, 1, 8, 1]],
    )
    house = _map(["11"], warps=[[0, 0, 255, 0]])  # one door: back where you came from
    return {"maps": {"2": route, "8": GATE, "60": house}}


def test_pass_gate_validates_candidates_and_crosses():
    truth = _gate_world()
    io = RoadIO(
        truth,
        (2, 0, 0),
        arrive={(2, 1, 0): (60, 1, 0), (2, 3, 0): (8, 0, 1), (2, 3, 1): (8, 0, 1)},
        thresholds={(60, 0, 0, "left"): (2, 0, 0), (8, 2, 1, "right"): (2, 5, 0)},
    )
    cells = {(6, 0), (6, 1)}
    assert road.pass_gate(io, truth, PAIRS, 2, cells) is True
    assert qm.read_pos(io) == (2, 5, 0)


def test_pass_gate_guard_refusal_and_exhaustion():
    truth = _gate_world()
    # the gate interior eats every input: a guard — pass_gate reports failure from inside
    io = RoadIO(truth, (2, 2, 0), arrive={(2, 3, 0): (8, 1, 1)}, frozen_at={(8, 1, 1)})
    io.truth["maps"]["2"]["warps"] = [[3, 0, 8, 0]]
    assert road.pass_gate(io, truth, PAIRS, 2, {(6, 0)}) is False
    # no candidate ever leaves the map at all
    truth2 = _gate_world()
    io2 = RoadIO(truth2, (2, 0, 0))
    assert road.pass_gate(io2, truth2, PAIRS, 2, {(6, 0)}) is False


# --------------------------------------------------------------------------- edges


def test_cross_edge_sweeps_for_the_aligned_cell():
    """Only the second edge cell actually hands over (the connection-offset lesson)."""
    truth = {"maps": {"1": _map(["111", "111"], connections={"east": 2})}}
    io = RoadIO(truth, (1, 0, 0), thresholds={(1, 2, 1, "right"): (2, 0, 1)})
    assert road.cross_edge(io, truth, PAIRS, 1, 2) is True
    assert qm.read_pos(io)[0] == 2


def test_cross_edge_walk_failure_and_stuck():
    truth = {"maps": {"1": _map(["101"], connections={"east": 2})}}
    io = RoadIO(truth, (1, 0, 0))
    assert road.cross_edge(io, truth, PAIRS, 1, 2) == "no-path"
    truth2 = {"maps": {"1": _map(["111"], connections={"east": 2})}}
    io2 = RoadIO(truth2, (1, 0, 0))
    assert road.cross_edge(io2, truth2, PAIRS, 1, 2) == "stuck-on-edge"


def test_cross_edge_hands_over_en_route_to_the_next_cell():
    """The map can change while WALKING toward another candidate cell."""
    truth = {"maps": {"1": _map(["111", "111"], connections={"east": 2})}}
    io = RoadIO(truth, (1, 2, 0), arrive={(1, 2, 1): (2, 0, 1)})
    assert road.cross_edge(io, truth, PAIRS, 1, 2) is True


# --------------------------------------------------------------------------- cut


def test_cut_facing_drives_the_menu_registers():
    io = RoadIO(_open_world(), (1, 0, 0))
    cur = {"v": 0}
    io.read_orig = io.read
    io.read = lambda addr: cur["v"] if addr == qm.ADDR_MENU_CUR else io.read_orig(addr)
    orig = io.press

    def press(btn, hold=8, release=8):
        if btn in ("down", "up"):
            cur["v"] += 1 if btn == "down" else -1
        orig(btn, hold, release)

    io.press = press
    road.cut_facing(io, "right")
    assert io.pressed[0] == "right"
    assert io.pressed.count("down") == 1  # cursor walked to the POKeMON row once
    assert io.pressed.count("a") == 3  # party -> lead -> CUT
    assert io.pressed[-1] == "b"


# --------------------------------------------------------------------------- drive_to


def _two_map_world():
    a = _map(["111"], connections={"east": 2})
    b = _map(["111"], connections={"west": 1}, warps=[[2, 0, 9, 0]])
    c = _map(["11"])
    return {"maps": {"1": a, "2": b, "9": c}}


def test_drive_to_edges_and_warps():
    truth = _two_map_world()
    logs = []
    io = RoadIO(truth, (1, 0, 0), thresholds={(1, 2, 0, "right"): (2, 0, 0)}, arrive={(2, 2, 0): (9, 0, 0)})
    assert road.drive_to(io, truth, PAIRS, 9, log=logs.append) is True
    assert any("--edge-->" in m or "edge" in m for m in logs)


def test_drive_to_no_route_and_hop_failure():
    truth = {"maps": {"1": _map(["111"]), "9": _map(["11"])}}
    io = RoadIO(truth, (1, 0, 0))
    assert road.drive_to(io, truth, PAIRS, 9) is False  # no route at all
    truth2 = {"maps": {"1": _map(["111"], connections={"east": 2}), "2": _map(["111"], connections={"west": 1})}}
    io2 = RoadIO(truth2, (1, 0, 0))  # edge never hands over, no gate to pass
    assert road.drive_to(io2, truth2, PAIRS, 2) is False


def test_drive_to_passes_a_gate_when_the_edge_is_severed():
    route = _map(
        ["110111", "110111"],
        connections={"east": 3},
        warps=[[1, 0, 8, 0]],
    )
    far = _map(["11"], connections={"west": 2})
    truth = {"maps": {"2": route, "8": GATE, "3": far}}
    io = RoadIO(
        truth,
        (2, 0, 0),
        arrive={(2, 1, 0): (8, 0, 1)},
        thresholds={(8, 2, 1, "right"): (2, 3, 0), (2, 5, 0, "right"): (3, 0, 0), (2, 5, 1, "right"): (3, 0, 0)},
    )
    assert road.drive_to(io, truth, PAIRS, 3) is True


def test_drive_to_traverses_a_swallowing_interior():
    """An edge crossing that lands INSIDE a gate: the interior is traversed onward."""
    a = _map(["111"], connections={"east": 3})
    far = _map(["11"], connections={"west": 1})
    truth = {"maps": {"1": a, "8": GATE, "3": far}}
    io = RoadIO(
        truth,
        (1, 0, 0),
        thresholds={(1, 2, 0, "right"): (8, 0, 1), (8, 2, 1, "right"): (3, 0, 0)},
    )
    assert road.drive_to(io, truth, PAIRS, 3) is True
    # and one that refuses from inside (a guard eating input)
    io2 = RoadIO(
        truth,
        (1, 0, 0),
        thresholds={(1, 2, 0, "right"): (8, 1, 1)},
        frozen_at={(8, 1, 1)},
    )
    assert road.drive_to(io2, truth, PAIRS, 3) is False


def test_drive_to_hop_cap_runs_out():
    truth = _two_map_world()
    io = RoadIO(truth, (1, 0, 0), thresholds={(1, 2, 0, "right"): (2, 0, 0)}, arrive={(2, 2, 0): (9, 0, 0)})
    assert road.drive_to(io, truth, PAIRS, 9, max_hops=0) is False


# ------------------------------------------------------------------ the wall vs the bump


def _corridor_truth():
    """A map shaped like Route 12: a wide south room, a two-column corridor north, and one
    choke cell at the top that a single body can plug."""
    #      x: 0123456
    rows = [
        "0011000",  # y=0  the goal edge
        "0011000",  # y=1
        "0001000",  # y=2  the choke: only x=3
        "0011000",  # y=3
        "1111111",  # y=4  the wide south room
        "1111111",  # y=5
    ]
    return {
        "maps": {
            "1": {
                "width": 7,
                "height": 6,
                "tileset": 0,
                "grid": rows,
                "warps": [],
                "sprites": [],
                "connections": {"north": 2},
            },
            "2": {
                "width": 7,
                "height": 6,
                "tileset": 0,
                "grid": rows,
                "warps": [],
                "sprites": [],
                "connections": {"south": 1},
            },
        }
    }


def test_reachable_is_the_body_aware_region():
    truth, pairs = _corridor_truth(), set()
    assert (3, 0) in road.reachable(truth, pairs, 1, (0, 5))
    assert (3, 0) not in road.reachable(truth, pairs, 1, (0, 5), blocked={(3, 2)})


def test_blocking_body_names_the_choke_not_the_body_underfoot():
    """Route 12 in miniature: the bystander at (1,4) is adjacent; the wall is the choke at (3,2)."""
    truth, pairs = _corridor_truth(), set()
    bodies = {(1, 4), (3, 2)}
    assert road.blocking_body(truth, pairs, 1, (0, 5), {(2, 0), (3, 0)}, bodies) == (3, 2)


def test_blocking_body_is_none_when_the_goal_is_already_reachable():
    truth, pairs = _corridor_truth(), set()
    assert road.blocking_body(truth, pairs, 1, (0, 5), {(2, 0), (3, 0)}, {(1, 4)}) is None


def test_two_bodies_in_one_corridor_are_terrain_not_a_gate():
    """No *single* removal reconnects it, so there is no one sprite to go argue with."""
    truth, pairs = _corridor_truth(), set()
    bodies = {(3, 2), (3, 3), (2, 3)}
    assert road.blocking_body(truth, pairs, 1, (0, 5), {(2, 0), (3, 0)}, bodies) is None


class CutIO:
    """A bush that opens after `cuts` applications of the field-Cut flow."""

    def __init__(self, cuts=1):
        self.cuts, self.applied, self.pos = cuts, 0, (1, 5, 5)
        self.presses = []

    def press(self, btn, hold=8, release=8):
        self.presses.append(btn)
        if btn == "a":
            self.applied += 1
        if btn == "up" and self.applied >= self.cuts:
            self.pos = (1, 5, 4)

    def wait(self, frames=30):
        pass

    def read(self, addr):
        return 1  # the field submenu cursor sits where cut_facing wants it


def test_cut_until_open_proves_the_cut_by_stepping(monkeypatch):
    """`cut_facing` fires the menu whether or not anything was cut; the step is the predicate."""
    io = CutIO(cuts=3)
    monkeypatch.setattr(road, "read_pos", lambda i: i.pos)
    assert road.cut_until_open(io, {}, set(), "up") is True
    assert "up" in io.presses


@pytest.fixture
def cut_read_pos(monkeypatch):
    """`cut_until_open`'s fake reads position off `io.pos`. Patch it through monkeypatch so the
    replacement is undone: assigning `road.read_pos` directly leaked into every later test in
    this file, and the first one to use another fake io died on `'RoadIO' has no attribute pos`."""
    monkeypatch.setattr(road, "read_pos", lambda i: i.pos)


def test_cut_until_open_gives_up_after_its_tries(cut_read_pos):
    io = CutIO(cuts=99)
    import rom_truth  # noqa: F401  (road.read_pos is imported at module scope)

    assert road.cut_until_open(io, {}, set(), "up", tries=2) is False


def test_cut_until_open_succeeds_on_the_step_after_the_cut(cut_read_pos):
    io = CutIO(cuts=1)
    assert road.cut_until_open(io, {}, set(), "up") is True


def test_cut_until_open_returns_at_once_when_the_way_is_already_clear(cut_read_pos):
    io = CutIO(cuts=0)
    assert road.cut_until_open(io, {}, set(), "up") is True
    assert "a" not in io.presses  # no menu was opened; the step just worked


def test_walkable_treats_pads_as_walls_and_reachable_does_not():
    """Silph 5F in miniature: the only path to the right-hand corridor crosses a warp pad.

    `reachable` (terrain) says the corridor is open; `walk` refuses to thread a door tile as
    floor, so the corridor is unreachable on foot and nine steps from the pad. Two sessions of
    "the model says reachable and the engine refuses" were this disagreement.
    """
    truth = {
        "maps": {
            "1": {
                "width": 5,
                "height": 1,
                "tileset": 22,
                "grid": ["11111"],
                "warps": [[2, 0, 7, 0]],
                "connections": {},
                "sprites": [],
            }
        }
    }
    pairs = set()
    assert (4, 0) in road.reachable(truth, pairs, 1, (0, 0))
    assert (4, 0) not in road.walkable(truth, pairs, 1, (0, 0))
    assert (4, 0) in road.walkable(truth, pairs, 1, (3, 0))  # already past the pad
    # The pad itself stays open when it is the target of the walk, matching `walk`'s own rule.
    assert (2, 0) in road.walkable(truth, pairs, 1, (0, 0), keep={(2, 0)})


def test_pads_reaching_names_the_ride_into_a_cut_off_corridor():
    truth = {
        "maps": {
            "1": {
                "width": 5,
                "height": 1,
                "tileset": 22,
                "grid": ["11111"],
                "warps": [[2, 0, 7, 0]],
                "connections": {},
                "sprites": [],
            }
        }
    }
    assert road.pads_reaching(truth, set(), 1, {(4, 0)}) == [((2, 0), 7)]
    assert road.pads_reaching(truth, set(), 1, {(0, 0)}) == [((2, 0), 7)]


def test_ride_pad_enters_a_region_whose_only_door_is_a_pad():
    """Silph 5F in miniature. Row 3 is `..P#` — the pad at x=2 is the only way to x=3, so `walk`
    (which treats pads as walls) can never deliver us there. Riding it lands on the far map,
    stepping off and back on returns us STANDING on the pad, and from there x=3 is one step."""
    truth = {
        "maps": {
            "1": _map(["1111"], warps=[[2, 0, 2, 0]]),
            "2": _map(["111"], warps=[[1, 0, 1, 0]]),
        }
    }
    # Each pad fires on arrival, sending us to the other map's warp tile.
    io = RoadIO(truth, (1, 0, 0), arrive={(1, 2, 0): (2, 1, 0), (2, 1, 0): (1, 2, 0)})
    assert road.walkable(truth, set(), 1, (0, 0)) == {(0, 0), (1, 0)}  # the walk cannot get there
    assert road.ride_pad(io, truth, set(), 1, {(3, 0)}) is True
    assert (io.mem[qm.ADDR_MAP], io.mem[qm.ADDR_X], io.mem[qm.ADDR_Y]) == (1, 3, 0)


def test_ride_pad_reports_failure_when_no_pad_stands_in_the_region():
    truth = {"maps": {"1": _map(["1101"], warps=[])}}
    io = RoadIO(truth, (1, 0, 0))
    assert road.ride_pad(io, truth, set(), 1, {(3, 0)}) is False


def test_live_bodies_clips_to_the_map_it_is_standing_on():
    """The sprite table has sixteen slots and the unused ones decode to coordinates that are not
    on any map. Silph 3F is 30x18 and a leg was told the body severing its hop stood at (18,22),
    four rows past the south wall — then walked over to engage it, opened the pause menu, and
    recorded "OPTION EXIT" as what the blocker said."""

    class SpriteIO:
        def __init__(self, cells):
            self.cells = cells

        def read(self, addr):
            for i, (x, y) in enumerate(self.cells, start=1):
                if addr == road.SPRITE_STATE_BASE + i * 0x10:
                    return 1
                if addr == road.SPRITE_DATA_BASE + i * 0x10 + 5:
                    return x + 4
                if addr == road.SPRITE_DATA_BASE + i * 0x10 + 4:
                    return y + 4
            return 0

    io = SpriteIO([(7, 9), (18, 22)])
    assert road.live_bodies(io) == {(7, 9), (18, 22)}  # unclipped: the junk slot is a "body"
    assert road.live_bodies(io, (30, 18)) == {(7, 9)}  # clipped to the floor we are standing on


def test_a_warp_tile_is_never_an_approach_cell():
    """`keep` exists for the target of a walk, not for the cell you stand on to reach one. Passing
    the whole adjacency as `keep` let a leg "walk next to the blocker" by stepping onto Saffron's
    Silph entrance — it warped indoors, walked back out, and did that until the hop cap fired."""
    truth = {
        "maps": {
            "1": {
                "width": 5,
                "height": 1,
                "tileset": 0,
                "grid": ["11111"],
                "warps": [[3, 0, 9, 0]],
                "connections": {},
                "sprites": [],
            }
        }
    }
    adjacent = {(3, 0), (1, 0)}  # (3,0) is the door beside the body at (4,0); (1,0) is floor
    assert road.walkable(truth, set(), 1, (0, 0)) & adjacent == {(1, 0)}


def test_ride_pad_handles_an_intra_map_pad_that_teleports_within_the_floor():
    """Sabrina's gym is a pad maze: 30 of its 32 warps point at itself, so riding one lands you
    elsewhere on the SAME map and there is no far side to come back from. A leg that only knew
    how to ride between maps met the guide at the door and called the floor engaged."""
    truth = {"maps": {"1": _map(["1" * 7], warps=[[2, 0, 1, 0], [5, 0, 1, 0]])}}
    io = RoadIO(truth, (1, 0, 0), arrive={(1, 2, 0): (1, 5, 0)})
    assert (6, 0) not in road.walkable(truth, set(), 1, (0, 0))  # unreachable on foot
    assert road.ride_pad(io, truth, set(), 1, {(6, 0)}) is True
    assert (io.mem[qm.ADDR_MAP], io.mem[qm.ADDR_X]) == (1, 6)


def test_ride_pad_chains_hops_through_a_maze():
    """One ride is enough for Silph's floors; Sabrina's gym is thirty pads deep, and the pocket
    holding a trainer sits several rides from the door."""
    truth = {"maps": {"1": _map(["1" * 9], warps=[[2, 0, 1, 0], [4, 0, 1, 0], [6, 0, 1, 0]])}}
    io = RoadIO(truth, (1, 0, 0), arrive={(1, 2, 0): (1, 4, 0), (1, 4, 0): (1, 6, 0)})
    assert (8, 0) not in road.walkable(truth, set(), 1, (0, 0))
    assert road.ride_pad(io, truth, set(), 1, {(8, 0)}) is True
    assert io.mem[qm.ADDR_X] == 8


def test_ride_pad_stops_after_its_hop_budget():
    truth = {"maps": {"1": _map(["1" * 9], warps=[[2, 0, 1, 0]])}}
    io = RoadIO(truth, (1, 0, 0), arrive={(1, 2, 0): (1, 0, 0)})  # a pad that loops us home
    assert road.ride_pad(io, truth, set(), 1, {(8, 0)}, rides=2) is False


def test_pad_land_resolves_the_same_map_destination_not_the_others():
    # 255 (0xFF) is the ROM's "this map" destination and its index reads the map's own warp list.
    m = _map(["1" * 7], warps=[[2, 0, 255, 1], [3, 0, 1, 0], [5, 0, 2, 0]])
    road.truth = {"maps": {"1": m, "2": m}}
    assert road.pad_land(road.truth, 1, [2, 0, 255, 1]) == (3, 0)
    assert road.pad_land(road.truth, 1, [3, 0, 1, 0]) == (2, 0)
    assert road.pad_land(road.truth, 1, [5, 0, 2, 0]) is None  # a door to another map is not the graph
    assert road.pad_land(road.truth, 1, [2, 0, 255, 9]) is None  # an index past the list is a decode lie


def test_pad_route_orders_the_rides_the_table_order_hunt_gives_up_on():
    # (2,0) and (5,0) ride at each other; (7,0) rides home and opens the last pocket. The table
    # lists (7,0) LAST, so the nearest-use hunt stands on (5,0)'s pocket and never rides it — the
    # BFS says ride (2,0), then (7,0), and the walk takes the last two steps.
    road.truth = {"maps": {"1": _map(["1" * 9], warps=[[2, 0, 1, 1], [5, 0, 1, 0], [7, 0, 1, 2]])}}
    assert road.pad_route(road.truth, set(), 1, (0, 0), {(8, 0)}) == [(2, 0), (7, 0)]
    assert road.pad_route(road.truth, set(), 1, (0, 0), {(1, 0)}) == []  # a plain walk covers it
    assert road.pad_route(road.truth, set(), 1, (0, 0), {}) is None


def test_pad_route_says_ride_your_own_pad_when_it_is_the_only_exit():
    # Standing ON a pad does not fire it. When that pad's landing pocket holds the target, the
    # route is the pad itself — the caller re-fires it by stepping off and back on.
    road.truth = {"maps": {"1": _map(["1" * 7], warps=[[1, 0, 1, 1], [4, 0, 1, 0]])}}
    assert road.pad_route(road.truth, set(), 1, (1, 0), {(5, 0)}) == [(1, 0)]


def test_pad_route_sees_the_bodies_severing_the_pocket():
    road.truth = {"maps": {"1": _map(["1" * 9], warps=[[2, 0, 1, 1], [5, 0, 1, 0]])}}
    assert road.pad_route(road.truth, set(), 1, (0, 0), {(8, 0)}) == [(2, 0)]
    assert road.pad_route(road.truth, set(), 1, (0, 0), {(8, 0)}, bodies={(6, 0), (7, 0)}) is None


def test_ride_pad_rides_the_routed_sequence_and_walks_the_rest():
    truth = {"maps": {"1": _map(["1" * 9], warps=[[2, 0, 1, 1], [5, 0, 1, 0], [7, 0, 1, 2]])}}
    io = RoadIO(truth, (1, 0, 0), arrive={(1, 2, 0): (1, 5, 0), (1, 7, 0): (1, 7, 0)})
    assert road.ride_pad(io, truth, set(), 1, {(8, 0)}, rides=3) is True
    assert qm.read_pos(io) == (1, 8, 0)
    assert io.pressed.count("right") == 5  # the route: (1,0), (2,0), (6,0), (7,0), (8,0)


def test_ride_pad_refires_the_pad_its_feet_are_on():
    # The (9,8) pocket's only exit is its own pad, and we arrive standing on such a pad: the ride
    # is stepping off it and back on, which is what re-fires it.
    truth = {"maps": {"1": _map(["1" * 7], warps=[[1, 0, 1, 1], [4, 0, 1, 0]])}}
    io = RoadIO(truth, (1, 1, 0), arrive={(1, 1, 0): (1, 4, 0)})
    assert road.ride_pad(io, truth, set(), 1, {(5, 0)}, rides=2) is True
    assert qm.read_pos(io) == (1, 5, 0)


def test_ride_pad_reaches_every_standing_body_in_sabrinas_gym():
    # The measured shape: 32 warps, every same-map pad riding in 2-cycles (each landing is
    # another pad tile), five unengaged bodies, and a baton bench at (17,14). The old engine
    # rode its budget standing in two pockets on all five; the routed engine must reach each,
    # and stand on the facing cell, within six rides.
    import rom_truth as rt

    truth = rt.load_truth()
    pairs = rt.loaded_pairs(truth)
    m = truth["maps"]["178"]
    arrive = {
        (178, w[0], w[1]): (178, land[0], land[1])
        for w in m["warps"]
        if (land := road.pad_land(truth, 178, w)) is not None
    }
    bodies = {(3, 1), (3, 7), (3, 13), (9, 8), (10, 1), (10, 15)}
    for body in ((9, 8), (10, 1), (3, 7), (3, 13), (3, 1)):
        x, y = body
        ring = {(x, y + 1), (x, y - 1), (x + 1, y), (x - 1, y), (x, y - 2)}
        ring = {c for c in ring if 0 <= c[0] < m["width"] and 0 <= c[1] < m["height"]}
        io = RoadIO({"maps": {"178": m}}, (178, 17, 14), arrive=arrive)
        assert road.ride_pad(io, {"maps": {"178": m}}, pairs, 178, ring, rides=6) is True, f"no ride reaches {body}"
        assert qm.read_pos(io)[1:] in ring, f"did not stand on the {body} facing cell"
    # And leaving a dead pocket: standing on (11,11), the (9,8) pocket's only pad, the (10,1)
    # facing cells are two rides away — the first ride is re-firing the pad under us.
    ring = {(9, 1), (11, 1), (10, 0), (10, 2)}
    io = RoadIO({"maps": {"178": m}}, (178, 11, 11), arrive=arrive)
    assert road.pad_route({"maps": {"178": m}}, pairs, 178, (11, 11), ring, bodies) == [(11, 11), (5, 3)]
    assert road.ride_pad(io, {"maps": {"178": m}}, pairs, 178, ring, rides=4) is True
    assert qm.read_pos(io)[1:] in ring


def test_pad_route_can_target_a_warp_tile_itself():
    """A gym's exit mat is a warp tile, and `walkable` calls every warp a wall — so a route TO one
    is unreachable by construction unless the target stays open. Badge 6 was won at (9,9) behind
    Sabrina's pads and the next leg burned its whole budget re-trying the mat at (8,17)."""
    # Pad (2,0) lands on pad (5,0); (6,0) is the exit door to map 9. Walking east from (0,0)
    # is stopped by the pad at (2,0), exactly as `walk` blocks door tiles.
    truth = {"maps": {"1": _map(["1" * 7], warps=[[2, 0, 1, 1], [5, 0, 1, 0], [6, 0, 9, 0]])}}
    assert road.pad_route(truth, set(), 1, (0, 0), {(6, 0)}) == [(2, 0)]  # ride, then step to it
    assert road.pad_route(truth, set(), 1, (5, 0), {(6, 0)}) == []  # already beside the door
    assert road.pad_route(truth, set(), 1, (0, 0), {(1, 0)}) == []  # a plain walk reaches it


def test_a_walk_that_starts_on_a_door_can_still_plan():
    """Arriving through a door leaves us standing ON it. Blocking every warp tile then makes the
    start cell a wall and no plan exists — the bug behind 'could not step off the warp mat' on
    Silph 3F, the Center exit, and the Safari Zone's arrival pad."""
    truth = {"maps": {"1": _map(["1111"], warps=[[0, 0, 9, 0]])}}
    io = RoadIO(truth, (1, 0, 0))  # standing on the door at (0,0)
    assert road.walk(io, truth, set(), 1, {(3, 0)}) is True
    assert (io.mem[qm.ADDR_X], io.mem[qm.ADDR_Y]) == (3, 0)
