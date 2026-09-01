"""The Rig's sink, tested without booting a cartridge.

A run that does not emit is unminable, so the sink's shape is doctrine: one file per UTC date
under ``data/telemetry/game/``, one JSON object per line, every line carrying the run_id that
correlates it to ``runs/<run_id>/``.
"""

import json
from datetime import datetime, timezone

import expedition_rig as rig


def test_the_sink_is_one_file_per_utc_date(tmp_path):
    when = datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc)
    assert rig.telemetry_path(when, root=tmp_path).name == "2026-08-31.jsonl"


def test_events_append_as_jsonl_and_carry_the_run_id(tmp_path):
    rig.emit_event("run-abc", "supervisor.leg_start", {"goal": 157}, root=tmp_path)
    rig.emit_event("run-abc", "supervisor.leg_end", {"outcome": "arrived"}, root=tmp_path)
    lines = [json.loads(x) for x in rig.telemetry_path(root=tmp_path).read_text().splitlines()]
    assert [x["event"] for x in lines] == ["supervisor.leg_start", "supervisor.leg_end"]
    assert {x["run_id"] for x in lines} == {"run-abc"}
    assert lines[0]["source"] == "expedition" and lines[0]["goal"] == 157
    assert lines[1]["ts"]  # every line is stamped; the sink is time-ordered by append


def test_the_sink_directory_is_created_on_first_write(tmp_path):
    root = tmp_path / "not" / "yet"
    rig.emit_event("run-xyz", "supervisor.hop_failed", {"failure": "no-path"}, root=root)
    assert rig.telemetry_path(root=root).exists()


class FakeIO:
    """A world that swallows every step until `parked` rounds of A/B have been spent.

    Stepping onto a warp tile moves us to another map, exactly as the cartridge does — which is
    how the badge-6 leg warped itself back into the gym it had just left.
    """

    def __init__(self, rig, *, parked=0, walls=(), warp_to=None):
        self.rig = rig
        self.parked = parked
        self.walls = set(walls)
        self.warp_to = warp_to  # {(x, y): destination map id}
        self.presses: list[str] = []

    def press(self, button, hold=8, release=8):
        self.presses.append(button)
        if button in ("a", "b"):
            self.parked = max(0, self.parked - (1 if button == "b" else 0))
            return
        if self.parked or button in self.walls:
            return
        dx, dy = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}[button]
        nx, ny = self.rig.mem[0xD362] + dx, self.rig.mem[0xD361] + dy
        self.rig.mem[0xD362], self.rig.mem[0xD361] = nx, ny
        if self.warp_to and (nx, ny) in self.warp_to:
            self.rig.mem[0xD35E] = self.warp_to[(nx, ny)]

    def wait(self, frames=30):
        pass


def _stub_rig(*, parked=0, walls=(), warps=(), warp_to=None, at=(4, 11)):
    """A Rig with only the pieces settle() touches — no cartridge, no PyBoy."""
    r = rig.Rig.__new__(rig.Rig)
    r.mem = {0xD35E: 157, 0xD362: at[0], 0xD361: at[1], rig.ADDR_BADGES: 0b11111, 0xD057: 0}
    r.truth = {"maps": {"157": {"warps": [[wx, wy, 7, 0] for wx, wy in warps]}}}
    r.io = FakeIO(r, parked=parked, walls=walls, warp_to=warp_to)
    r.ctl = r.io
    return r


def test_probe_step_moves_and_undoes_itself():
    r = _stub_rig()
    assert r.probe_step() is True
    assert r.pos() == (157, 4, 11)  # the probe left the world exactly where it found it
    assert r.io.presses[:2] == ["down", "up"]


def test_probe_step_reports_false_when_every_direction_is_swallowed():
    r = _stub_rig(parked=99)
    assert r.probe_step() is False


def test_settle_flushes_a_parked_textbox_and_proves_it_with_a_step():
    """BADGE5.state was banked on Koga's TM line and refused all four steps until flushed."""
    r = _stub_rig(parked=2)
    assert r.settle() is True
    assert "b" in r.io.presses  # A advances the pages, B closes what A opened
    assert r.pos() == (157, 4, 11)


def test_settle_gives_up_honestly_rather_than_claiming_a_flush():
    r = _stub_rig(parked=99)
    assert r.settle(max_rounds=3) is False


def test_the_probe_refuses_to_thread_a_door():
    """Measured: a baton banked one tile below Fuchsia gym's mat probed *up* and warped inside."""
    r = _stub_rig(at=(5, 28), warps=[(5, 27)], warp_to={(5, 27): 999})
    assert r.probe_step() is True
    assert r.pos()[0] == 157  # the probe proved input without going through the door
    assert "up" not in r.io.presses[:1]


def test_the_probe_uses_a_door_only_when_there_is_nothing_else():
    """A state wedged in a doorway still has to be able to prove it accepts input."""
    r = _stub_rig(at=(5, 28), warps=[(5, 27), (5, 29), (4, 28), (6, 28)], warp_to={(5, 29): 999})
    assert r.probe_step() is True
    assert r.pos()[0] == 999  # it went through, because every neighbour was a door


def test_the_rig_points_at_this_repos_rom_and_baton_shelf():
    assert rig.ROM_DEFAULT.name == "pokemon_red.gb"
    assert rig.BATON_DIR.parts[-2:] == ("local_runs", "roster-bench")
    assert rig.TELEMETRY_DIR.parts[-2:] == ("telemetry", "game")


def test_settled_pos_rejects_a_torn_read_across_a_warp():
    """(234, 17, 11) on a map 16 tiles wide is the transition window, not a place."""
    r = _stub_rig(at=(17, 11))
    r.mem[0xD35E] = 234
    r.truth = {"maps": {"234": {"width": 16, "height": 18, "warps": []}}}
    calls = {"n": 0}

    def press(button, hold=8, release=8):  # the transition completes as the world ticks on
        calls["n"] += 1

    def wait(frames=30):
        r.mem[0xD362], r.mem[0xD361] = 13, 7
        r.mem[0xD35E] = 209

    r.io.press, r.io.wait = press, wait
    r.truth["maps"]["209"] = {"width": 26, "height": 18, "warps": []}
    assert r.settled_pos() == (209, 13, 7)


def test_settled_pos_returns_a_stable_in_bounds_read_unchanged():
    r = _stub_rig(at=(4, 11))
    r.truth = {"maps": {"157": {"width": 10, "height": 18, "warps": []}}}
    r.io.wait = lambda frames=30: None
    assert r.settled_pos() == (157, 4, 11)


def _bag_rig(bag, items=None):
    r = rig.Rig.__new__(rig.Rig)
    r.mem = {rig.ADDR_BAG_COUNT: len(bag)}
    for i, (item, qty) in enumerate(bag):
        r.mem[rig.ADDR_BAG_ITEMS + 2 * i] = item
        r.mem[rig.ADDR_BAG_ITEMS + 2 * i + 1] = qty
    r.truth = {"items": items or {"60": "FRESH WATER", "74": "LIFT KEY", "40": "RARE CANDY"}}
    r.run_id = "t"
    r.telemetry_root = None
    r.settle = lambda *a, **kw: True  # the real one presses buttons; nothing to press here
    return r


def test_the_bag_is_read_as_named_items_not_raw_ids():
    r = _bag_rig([(74, 1), (60, 6)])
    assert r.bag_named() == [("LIFT KEY", 1), ("FRESH WATER", 6)]
    assert r.item_name(999) == "#999"  # TMs live past the name list and keep their id


def test_the_bag_is_full_only_at_the_measured_slot_cap():
    assert _bag_rig([(4, 1)] * (rig.BAG_SLOTS - 1)).bag_full() is False
    assert _bag_rig([(4, 1)] * rig.BAG_SLOTS).bag_full() is True


def test_make_room_tosses_the_largest_stack(monkeypatch, tmp_path):
    """Quantity is the measured signal: key items are single copies, consumables come in stacks."""
    r = _bag_rig([(74, 1), (60, 6), (40, 2)])
    r.telemetry_root = tmp_path
    tossed = {}

    def toss(item):
        tossed["item"] = item
        return True

    r.toss_stack = toss
    assert r.make_room() is True
    assert tossed["item"] == 60  # FRESH WATER x6, not the LIFT KEY and not RARE CANDY x2


def test_make_room_refuses_when_every_slot_is_a_single_item(tmp_path):
    r = _bag_rig([(74, 1), (72, 1), (73, 1)])
    r.telemetry_root = tmp_path
    assert r.make_room() is False  # nothing here is expendable; say so rather than tossing a key


class LiftRig:
    """A lift car whose panel prints a scrolling floor list, like Silph's and the Hideout's."""

    def __init__(self, floors, target_row=0):
        self.floors = floors
        self.cursor = 0
        self.presses = []
        self.left = False

    def window_row(self, row):
        i = (row - 4) // 2
        return self.floors[i] if 0 <= i < len(self.floors) else ""


def test_the_floor_labels_are_read_off_the_panel_not_indexed():
    """Which floor sits at which index is exactly the sort of fact this project has been burned
    by recalling, so the label under the cursor is decoded from the window layer."""
    r = rig.Rig.__new__(rig.Rig)
    r.window_row = lambda row: {4: "1F", 6: "2F", 8: "3F"}.get(row, "")
    assert r.elevator_floors() == ["1F", "2F", "3F"]


def test_a_car_without_a_sign_is_reported_not_guessed(capsys):
    r = rig.Rig.__new__(rig.Rig)
    r.mem = {0xD35E: 236, 0xD362: 1, 0xD361: 2}
    r.truth = {"maps": {"236": {"warps": [], "signs": []}}}
    assert r.ride_elevator("5F") is False
    assert "no sign to use as a lift panel" in capsys.readouterr().out


def test_make_room_falls_back_to_a_tm_when_nothing_is_stacked(tmp_path):
    """Every slot a single item is not the same as nothing being expendable: TMs are named by
    the cartridge, we carry eight, and the game refuses to toss anything it considers a key."""
    r = _bag_rig([(74, 1), (72, 1), (207, 1)], items={"74": "LIFT KEY", "72": "SILPH SCOPE", "207": "TM07"})
    r.telemetry_root = tmp_path
    tried = []

    def toss(item):
        tried.append(item)
        return True

    r.toss_stack = toss
    assert r.make_room() is True
    assert tried == [207]  # the TM, never the LIFT KEY or the SILPH SCOPE


def test_make_room_moves_on_when_the_game_refuses_a_toss(tmp_path):
    r = _bag_rig([(207, 1), (210, 1)], items={"207": "TM07", "210": "TM10"})
    r.telemetry_root = tmp_path
    tried = []

    def toss(item):
        tried.append(item)
        return item == 210  # the first one will not go

    r.toss_stack = toss
    assert r.make_room() is True
    assert tried == [207, 210]


def test_make_room_still_refuses_a_bag_of_only_key_items(tmp_path):
    r = _bag_rig([(74, 1), (72, 1)], items={"74": "LIFT KEY", "72": "SILPH SCOPE"})
    r.telemetry_root = tmp_path
    assert r.make_room() is False


def test_text_from_returns_only_what_the_action_produced():
    r = rig.Rig.__new__(rig.Rig)
    state = {"text": "AAAAAAA got 750 for winning!"}
    r.dialogue = lambda: state["text"]
    assert r.text_from(lambda: None) == ""  # a sticky buffer is not this action's message
    assert r.text_from(lambda: state.update(text="Darn! It needs a CARD KEY!")) == "Darn! It needs a CARD KEY!"


class FieldMenuRig:
    """A party field submenu whose rows are whatever the mon happens to know."""

    def __init__(self, moves):
        self.moves = moves
        self.cursor = 0
        self.chosen = None
        self.presses = []

    def window_row(self, row):
        i = (row - 4) // 2
        return self.moves[i] if 0 <= i < len(self.moves) else ""


def test_a_field_move_is_found_by_name_not_by_a_remembered_row():
    """`cut_facing` hardcodes CUT on row 0. Which move sits on which row depends on the mon."""
    r = rig.Rig.__new__(rig.Rig)
    menu = FieldMenuRig(["FLY", "SURF", "STRENGTH", "CUT"])
    r.window_row = menu.window_row
    assert r.field_moves(4) == ["FLY", "SURF", "STRENGTH", "CUT"]


def test_a_move_the_party_does_not_know_is_reported_not_guessed(capsys):
    r = rig.Rig.__new__(rig.Rig)
    menu = FieldMenuRig(["CUT", "FLASH"])
    r.window_row = menu.window_row
    r.field_moves = lambda rows=8: menu.moves
    r.mem = {0xCC26: 0}

    class Ctl:
        def press(self, b):
            pass

        def wait(self, n=0):
            pass

    r.ctl = Ctl()
    assert r.use_field_move("SURF") is False
    assert "no field move called 'SURF'" in capsys.readouterr().out


# --------------------------------------------------------------- the plain reads and delegations


def _reader_rig(mem=None, truth=None):
    r = rig.Rig.__new__(rig.Rig)
    r.mem = mem if mem is not None else {}
    r.truth = truth if truth is not None else {"maps": {}}
    r.pairs = set()
    r.io = object()
    return r


def test_badges_is_read_straight_from_ram():
    assert _reader_rig({rig.ADDR_BADGES: 0b11111}).badges() == 31


def test_party_is_decoded_from_the_struct_table():
    mem = {rig.ADDR_PARTY_COUNT: 1}
    base = rig.ADDR_PARTY_STRUCTS
    mem[base] = 1  # whatever species id 1 is in this ROM's internal order
    mem[base + 33] = 99
    mem[base + 1], mem[base + 2] = 1, 0x2C  # 300 hp, big-endian across two bytes
    species, level, hp = _reader_rig(mem).party()[0]
    assert (level, hp) == (99, 300) and isinstance(species, str)


def test_dialogue_survives_a_buffer_read_that_throws():
    r = _reader_rig()

    class Reader:
        def read_dialogue(self):
            raise RuntimeError("mid-redraw")

    r.mr = Reader()
    assert r.dialogue() == ""  # a text buffer mid-redraw is not a leg failure


def test_item_balls_come_from_the_extraction():
    truth = {"maps": {"9": {"sprites": [{"kind": "item", "x": 1, "y": 2}, {"kind": "npc", "x": 3, "y": 4}]}}}
    assert _reader_rig(truth=truth).item_balls(9) == [(1, 2)]
    assert _reader_rig(truth=truth).item_balls(404) == []


def test_warp_tiles_come_from_the_extraction():
    truth = {"maps": {"9": {"warps": [[1, 2, 3, 0], [4, 5, 6, 0]]}}}
    assert _reader_rig(truth=truth).warp_tiles(9) == {(1, 2), (4, 5)}


def test_settled_pos_gives_up_after_its_tries_rather_than_spinning():
    r = _stub_rig(at=(4, 11))
    r.truth = {"maps": {"157": {"width": 10, "height": 18, "warps": []}}}
    moves = iter(range(100))
    r.io.wait = lambda frames=30: r.mem.__setitem__(0xD362, next(moves))  # never settles
    assert r.settled_pos(tries=3)[0] == 157


def test_flush_text_reports_whether_the_buffer_actually_emptied():
    r = _stub_rig()
    r.dialogue = lambda: ""
    assert r.flush_text() is True
    r.dialogue = lambda: "still here"
    assert r.flush_text(tries=2) is False


def test_settle_resolves_a_battle_before_probing():
    r = _stub_rig(parked=1)
    r.mem[0xD057] = 1
    fought = []

    def battle():
        fought.append(True)
        r.mem[0xD057] = 0

    r.battle = battle
    assert r.settle() is True
    assert fought == [True]


def test_the_road_delegations_pass_the_battle_handler_through(monkeypatch):
    """Every mover hands the agent's battle turn to `road`; a delegation that forgets it raises."""
    import road as road_mod

    r = _reader_rig()
    r.battle = lambda io=None: None
    seen = {}

    def spy(*a, **kw):
        seen[kw.get("battle")] = True
        return "ok"

    for name, call in [
        ("walk", lambda: r.walk(1, {(0, 0)})),
        ("drive_to", lambda: r.drive(2)),
        ("through_warp", lambda: r.warp(1, 0, 0)),
        ("cross_edge", lambda: r.cross(1, 2)),
        ("traverse_interior", lambda: r.traverse(1)),
        ("pass_gate", lambda: r.gate(1, set())),
    ]:
        monkeypatch.setattr(road_mod, name, spy)
        assert call() == "ok"
    assert list(seen) == [r.battle]  # one handler, threaded through every one of them


def test_bodies_delegates_to_the_live_sprite_table(monkeypatch):
    import road as road_mod

    # The rig passes the current map's bounds so off-map sprite slots cannot become blockers.
    seen = {}

    def fake(io, bounds=None):
        seen["bounds"] = bounds
        return {(1, 2)}

    monkeypatch.setattr(road_mod, "live_bodies", fake)
    r = _reader_rig({0xD35E: 208, 0xD362: 26, 0xD361: 1}, {"maps": {"208": {"width": 30, "height": 18}}})
    assert r.bodies() == {(1, 2)}
    assert seen["bounds"] == (30, 18)  # the floor we are standing on, so off-map slots are dropped


def test_window_row_decodes_the_layer_menus_render_to():
    r = _reader_rig()

    class Tile:
        def tile_identifier(self, x, y):
            return (0x80 + x) if y == 4 and x < 3 else 0x7F

    class PB:
        tilemap_window = Tile()

    r.pb = PB()
    assert r.window_row(4) == "ABC"
    assert r.elevator_floors()[1] == ""


def test_settle_succeeds_once_a_b_press_frees_the_world():
    """The probe fails, B closes what was open, and the second probe proves it."""
    r = _stub_rig(parked=1)
    assert r.settle() is True
    assert "b" in r.io.presses


def test_settle_returns_immediately_when_the_world_already_moves():
    r = _stub_rig(parked=0)
    assert r.settle() is True
    assert "b" not in r.io.presses  # nothing was blocking, so nothing was pressed at it
