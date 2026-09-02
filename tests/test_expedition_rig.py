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


def test_step_off_targets_prefers_floor_and_never_another_door():
    """A Pokemon Center has two exit mats side by side. Banking on one and "stepping off" onto
    the other leaves the baton in the doorway, and booting it settles straight out of the
    building — which is exactly what Saffron's (182,3,7) baton did, costing a leg its ladder
    trying to get back in."""
    r = _reader_rig(
        {0xD35E: 182, 0xD362: 3, 0xD361: 7},
        {"maps": {"182": {"width": 6, "height": 8, "grid": ["111111"] * 8, "warps": [[3, 7, 10, 0], [4, 7, 10, 0]]}}},
    )
    moves = r.step_off_targets(182, 3, 7)
    assert ("up", (3, 6)) in moves  # into the building
    assert all(cell != (4, 7) for _d, cell in moves)  # never the mat next door
    assert moves[0][0] == "up"  # and the interior is tried first


class _MenuRig:
    """Enough Rig to exercise menu selection: a window layer and a cursor register."""

    def __init__(self, rows, cursor=0):
        self._rows = rows
        self.mem = {rig.qm.ADDR_MENU_CUR: cursor, rig.ADDR_LIST_SCROLL: 0}
        self.presses = []

        class Ctl:
            def __init__(self, outer):
                self.outer = outer

            def press(self, button, *a, **kw):
                self.outer.presses.append(button)
                cur = self.outer.mem[rig.qm.ADDR_MENU_CUR]
                if button == "down":
                    self.outer.mem[rig.qm.ADDR_MENU_CUR] = cur + 1
                elif button == "up":
                    self.outer.mem[rig.qm.ADDR_MENU_CUR] = max(0, cur - 1)

            def wait(self, frames=30):
                pass

        self.ctl = Ctl(self)

    def window_row(self, row):
        return self._rows.get(row, "")

    def menu_rows(self, first=0, last=14):
        return rig.Rig.menu_rows(self, first, last)

    def dialogue(self):
        return ""

    def list_index(self):
        return rig.Rig.list_index(self)


def test_menu_choose_selects_by_text_not_by_position():
    """The PC menu lists WITHDRAW, DEPOSIT, RELEASE and CHANGE BOX. Choosing by index would one
    day release a party member because a menu shifted, so entries are matched by decoded text and
    the cursor register is the ground truth for where the cursor sits."""
    menu = _MenuRig({2: "WITHDRAW", 4: "DEPOSIT", 6: "RELEASE", 8: "CHANGE BOX", 10: "SEE YA!"})
    assert rig.Rig.menu_choose(menu, "DEPOSIT") is True
    assert menu.mem[rig.qm.ADDR_MENU_CUR] == 1  # entries render every other row
    assert menu.presses[-1] == "a"
    assert "RELEASE" not in menu.presses


def test_menu_choose_reports_a_miss_rather_than_pressing_a():
    menu = _MenuRig({2: "WITHDRAW", 4: "DEPOSIT"})
    assert rig.Rig.menu_choose(menu, "SURF") is False
    assert "a" not in menu.presses


def test_menu_choose_walks_the_cursor_back_up():
    menu = _MenuRig({2: "WITHDRAW", 4: "DEPOSIT", 6: "RELEASE"}, cursor=2)
    assert rig.Rig.menu_choose(menu, "WITHDRAW") is True
    assert menu.mem[rig.qm.ADDR_MENU_CUR] == 0
    assert menu.presses.count("up") == 2


def test_the_pc_is_a_template_cell_like_the_nurses_counter():
    center = _reader_rig(
        {0xD35E: 64, 0xD362: 3, 0xD361: 7},
        {"maps": {"64": {"width": 14, "height": 8, "tileset": 6, "sprites": [{"kind": "npc", "x": 3, "y": 1}]}}},
    )
    assert center.center_pc(64) == ((13, 4), "up")
    plain = _reader_rig({}, {"maps": {"9": {"width": 10, "height": 9, "tileset": 0, "sprites": []}}})
    assert plain.center_pc(9) is None


def test_menu_shows_never_presses_anything_while_it_looks():
    """A advances a text box, but inside a list it CONFIRMS the highlighted entry — that is how
    Charizard and then Dugtrio ended up in a box. Looking must never press."""
    menu = _MenuRig({2: "CHARIZARD", 4: "DUGTRIO", 6: "HYPNO"})
    assert rig.Rig.menu_shows(menu, "DEPOSIT", tries=2) is False
    assert menu.presses == []
    assert rig.Rig.menu_shows(menu, "DUGTRIO", tries=2) is True
    assert menu.presses == []


def test_menu_cursor_to_counts_the_scroll_not_just_the_cursor():
    """The deposit roster shows three rows: 0xCC26 caps at 2 while 0xCC36 counts how far the list
    has scrolled, so the highlight is cursor + scroll. Reading only the cursor deposits the wrong
    member for anything past the third slot — measured on Cerulean's PC."""
    menu = _MenuRig({2: "AAAAAAAAAA", 4: "DUGTRIO", 6: "GLOOM"}, cursor=0)
    menu.mem[rig.ADDR_LIST_SCROLL] = 0

    def press(button, *a, **kw):  # the window caps at 2 and then the list scrolls under it
        menu.presses.append(button)
        if button == "down":
            if menu.mem[rig.qm.ADDR_MENU_CUR] < 2:
                menu.mem[rig.qm.ADDR_MENU_CUR] += 1
            else:
                menu.mem[rig.ADDR_LIST_SCROLL] += 1

    menu.ctl.press = press
    assert rig.Rig.menu_cursor_to(menu, 4) is True
    assert rig.Rig.list_index(menu) == 4
    assert menu.mem[rig.qm.ADDR_MENU_CUR] == 2 and menu.mem[rig.ADDR_LIST_SCROLL] == 2
    assert "a" not in menu.presses  # walked, never confirmed


def test_menu_choose_indexes_within_the_block_when_menus_overlay():
    """Choosing DEPOSIT renders the party list on top of the box menu, and the follow-up
    DEPOSIT/STATS/CANCEL renders on top of that. Measured rows from Cerulean's PC — the cursor
    index must be counted from the block the match is in, not from the first row on screen."""
    overlaid = _MenuRig(
        {2: "WI", 4: "DEDUGTRIO", 5: "99", 6: "RE GLOOM", 7: "99", 8: "CH PRIMEAPE", 12: "DEPOSIT", 14: "CANCEL"}
    )
    assert rig.Rig.menu_choose(overlaid, "DEPOSIT") is True
    assert overlaid.mem[rig.qm.ADDR_MENU_CUR] == 0  # first entry of ITS OWN block, not the fifth


def test_grass_lanes_are_the_rom_s_own_extremes():
    """Where to roam comes from the extracted grass tiles, not from lore — and pacing the
    extremes keeps crossing fresh tiles instead of rolling the same one. (Reachability is
    filtered only when the rig is standing on that map; see the next test.)"""
    # Standing on a different map, so the reachability filter does not apply.
    r = _reader_rig(
        {0xD35E: 99, 0xD362: 0, 0xD361: 0},
        {"maps": {"33": {"grass": [[5, 9], [2, 3], [7, 3], [2, 9]]}, "1": {"grass": []}}},
    )
    assert r.grass_lanes(33) == [(2, 3), (5, 9)]
    assert r.grass_lanes(1) == []  # a map with no grass has no lane to pace
    assert r.grass_lanes(999) == []  # and neither has one we do not model


def test_grass_lanes_only_offers_grass_we_can_stand_on(monkeypatch):
    """Route 2's 84 grass cells all sit outside the 144-cell region a leg arriving from Diglett's
    Cave can reach. Aimed at them, the roam walked nowhere and rolled no encounters at all —
    twelve thousand laps with a level-5 Magikarp still level 5."""
    import road as road_mod

    truth = {"maps": {"13": {"grass": [[0, 2], [9, 51]], "width": 20, "height": 72}}}
    r = _reader_rig({0xD35E: 13, 0xD362: 12, 0xD361: 10}, truth)
    r.bodies = lambda: set()
    monkeypatch.setattr(road_mod, "walkable", lambda *a, **k: {(12, 10), (12, 11)})
    assert r.grass_lanes(13) == []  # none of the map's grass is in our region
    monkeypatch.setattr(road_mod, "walkable", lambda *a, **k: {(12, 10), (0, 2), (9, 51)})
    assert r.grass_lanes(13) == [(0, 2), (9, 51)]


# --------------------------------------------------------------------------- healing at a Center

_CENTER_MAP = {"width": 14, "height": 8, "tileset": 6, "sprites": [{"kind": "npc", "x": 3, "y": 1}]}


def test_heal_at_center_refuses_a_map_that_is_not_a_center(capsys):
    """The grind leg that crashed here (run 20260901-164132-3962) had driven to map 89 and then
    called a method that did not exist; the honest failure on a wrong map is False, said aloud."""
    r = _reader_rig({0xD35E: 157, 0xD362: 3, 0xD361: 3}, {"maps": {"157": {"width": 10, "height": 9, "tileset": 0}}})
    assert r.heal_at_center() is False
    assert "not a Center" in capsys.readouterr().out


def test_heal_at_center_is_a_no_op_when_the_party_already_reads_full(monkeypatch):
    r = _reader_rig({0xD35E: 182, 0xD362: 5, 0xD361: 5}, {"maps": {"182": _CENTER_MAP}})
    monkeypatch.setattr(rig.qm, "read_party", lambda io: [{"hp": 63, "max_hp": 63}])
    r.approach = lambda cells: (_ for _ in ()).throw(AssertionError("walked for nothing"))
    assert r.heal_at_center() is True


def test_heal_at_center_talks_the_template_cell_until_the_party_reads_full(monkeypatch):
    r = _reader_rig({0xD35E: 182, 0xD362: 5, 0xD361: 5}, {"maps": {"182": _CENTER_MAP}})
    world = {"healed": False, "stood": None}
    monkeypatch.setattr(rig.qm, "read_party", lambda io: [{"hp": 63 if world["healed"] else 12, "max_hp": 63}])

    def approach(cells):
        world["stood"] = cells
        return True

    def nurse(io, face):
        assert face == "up"  # the counter template: player at (3,3) facing the nurse at (3,1)
        world["healed"] = True

    r.approach = approach
    monkeypatch.setattr(rig.qm, "heal", nurse)
    assert r.heal_at_center() is True
    assert world["stood"] == {(3, 3)}


def test_heal_at_center_reports_an_unreachable_counter(monkeypatch, capsys):
    r = _reader_rig({0xD35E: 182, 0xD362: 5, 0xD361: 5}, {"maps": {"182": _CENTER_MAP}})
    monkeypatch.setattr(rig.qm, "read_party", lambda io: [{"hp": 12, "max_hp": 63}])
    r.approach = lambda cells: False
    assert r.heal_at_center() is False
    assert "could not reach" in capsys.readouterr().out


def test_heal_at_center_gives_up_honestly_when_the_nurse_never_heals(monkeypatch):
    r = _reader_rig({0xD35E: 182, 0xD362: 5, 0xD361: 5}, {"maps": {"182": _CENTER_MAP}})
    monkeypatch.setattr(rig.qm, "read_party", lambda io: [{"hp": 12, "max_hp": 63}])
    r.approach = lambda cells: True
    calls = {"n": 0}

    def refuses(io, face):
        calls["n"] += 1
        raise rig.qm.QuartermasterError("nurse heal")

    monkeypatch.setattr(rig.qm, "heal", refuses)
    assert r.heal_at_center() is False
    assert calls["n"] == 3  # it retried, then told the truth instead of spinning


class _Recorder:
    """A controller that only remembers what was pressed — menus are stubbed per test."""

    def __init__(self):
        self.presses: list[str] = []

    def press(self, button, *a, **kw):
        self.presses.append(button)

    def wait(self, frames=30):
        pass


def test_a_failed_lead_swap_closes_the_menus_it_opened():
    """Measured on the karp grind: a silent failure here left the START menu up, every step after
    was swallowed, and the heal trip's first hop reported "refused" against a clear road."""
    r = rig.Rig.__new__(rig.Rig)
    r.party = lambda: [("MAGIKARP", 16, 5), ("HYPNO", 99, 341)]
    r.ctl = _Recorder()
    r.menu_choose = lambda wanted: False  # the start menu never showed POKeMON
    assert r.lead_swap(1) is False
    opened = r.ctl.presses.index("start")
    assert r.ctl.presses[opened + 1 :].count("b") >= 8  # what it opened, it closed


def test_say_puts_what_the_game_said_into_the_sink(tmp_path):
    """The Rig read a guru naming his rod, a boss conceding Silph and every card-key door, and
    only ever printed them — a search across every captured event for SURF, HM or SOULBADGE
    returned nothing while all of it had been on screen."""
    r = rig.Rig.__new__(rig.Rig)
    r.mem = {0xD35E: 163, 0xD362: 2, 0xD361: 5}
    r.run_id = "t"
    r.telemetry_root = tmp_path
    r.say("I'm the FISHING GURU! I simply love fishing!")
    r.say("   ")  # nothing said is nothing to record
    lines = [json.loads(x) for x in rig.telemetry_path(root=tmp_path).read_text().splitlines()]
    assert len(lines) == 1
    assert lines[0]["event"] == "discovery"
    assert lines[0]["map"] == 163 and (lines[0]["x"], lines[0]["y"]) == (2, 5)
    assert "FISHING GURU" in lines[0]["text"] and lines[0]["kind"] == "dialogue"


def test_ball_contents_names_what_each_ball_holds():
    """The lookup that ended the CARD KEY hunt: a ball's contents are in the cartridge."""
    r = _reader_rig(
        {},
        {
            "items": {"48": "CARD KEY", "20": "SUPER POTION"},
            "maps": {
                "210": {
                    "sprites": [
                        {"kind": "item", "x": 21, "y": 16, "item": 48},
                        {"kind": "item", "x": 2, "y": 13, "item": 20},
                        {"kind": "trainer", "x": 8, "y": 3},
                    ]
                }
            },
        },
    )
    assert r.ball_contents(210) == {(21, 16): "CARD KEY", (2, 13): "SUPER POTION"}
    assert r.ball_contents(999) == {}


def test_unlock_gates_drops_the_doors_the_bag_can_open():
    """A locked door is only a wall while the key is missing — and the leg that took the CARD KEY
    then planned its next hop as though it had not."""
    truth = {
        "items": {"48": "CARD KEY"},
        "maps": {
            "208": {"gates": {"11,11,left": "Darn! It needs a CARD KEY!", "3,3,up": "The door is locked..."}},
            "210": {"gates": {}},
            "1": {},
        },
    }
    r = _reader_rig({}, truth)
    r.bag_named = lambda: [("CARD KEY", 1), ("POTION", 3)]
    assert r.unlock_gates() == 1
    assert truth["maps"]["208"]["gates"] == {"3,3,up": "The door is locked..."}
    r.bag_named = lambda: []
    assert r.unlock_gates() == 0  # an empty bag opens nothing


def test_advance_text_stops_at_the_roster_rather_than_pressing_into_it():
    """A stops a text box and CONFIRMS inside a list. Recognise the roster by its own contents."""

    class Roster(_MenuRig):
        def party(self):
            return [("GLOOM", 99, 313), ("DUGTRIO", 100, 259)]

    menu = Roster({2: "DE GLOOM", 4: "RE DUGTRIO"})
    assert rig.Rig.advance_text(menu, "DEPOSIT") is False
    assert menu.presses == []


def test_advance_text_presses_through_a_box_until_the_menu_it_wants():
    class Box(_MenuRig):
        def __init__(self):
            super().__init__({2: "BILL's PC"})
            self.seen = 0

        def party(self):
            return [("GLOOM", 99, 313)]

        def menu_rows(self, first=0, last=18):
            self.seen += 1
            return [(2, "DEPOSIT")] if self.seen > 1 else [(2, "BILL's PC")]

    box = Box()
    assert rig.Rig.advance_text(box, "DEPOSIT") is True
    assert box.presses.count("a") >= 1


def test_advance_text_gives_up_after_its_budget():
    """A box that never changes is not a menu we can reach; say so rather than press forever."""

    class Stuck(_MenuRig):
        def party(self):
            return [("GLOOM", 99, 313)]

    stuck = Stuck({2: "BILL's PC"})
    assert rig.Rig.advance_text(stuck, "DEPOSIT", tries=3) is False
    assert stuck.presses.count("a") == 3


def test_menu_cursor_to_reports_failure_when_the_cursor_will_not_move():
    class Frozen(_MenuRig):
        def __init__(self):
            super().__init__({2: "A", 4: "B"})
            self.ctl.press = lambda *a, **k: self.presses.append(a[0] if a else "?")

    frozen = Frozen()
    assert rig.Rig.menu_cursor_to(frozen, 3, presses=4) is False


def test_menu_choose_and_center_lookups_refuse_what_they_cannot_find():
    menu = _MenuRig({})
    assert rig.Rig.menu_choose(menu, "DEPOSIT") is False  # nothing on screen
    plain = _reader_rig({}, {"maps": {"9": {"width": 10, "height": 9, "tileset": 0, "sprites": []}}})
    assert plain.center_counter(9) is None
    assert plain.step_off_targets(404, 0, 0) == []  # a map we do not model
    assert plain.grass_lanes(9) == []  # no grass listed


def test_menu_choose_refuses_when_the_cursor_will_not_reach_the_entry():
    """Reporting a miss beats pressing A somewhere we did not aim — the PC menu holds RELEASE."""

    class Stuck(_MenuRig):
        def __init__(self):
            super().__init__({2: "WITHDRAW", 4: "DEPOSIT"})
            self.ctl.press = lambda *a, **k: self.presses.append(a[0] if a else "?")  # cursor frozen

    stuck = Stuck()
    assert rig.Rig.menu_choose(stuck, "DEPOSIT") is False
    assert "a" not in stuck.presses


def test_center_counter_needs_the_nurse_tile_not_just_the_shell():
    """A room the same size and tileset as a Center is not a Center without the nurse at (3,1)."""
    shell = _reader_rig(
        {}, {"maps": {"64": {"width": 14, "height": 8, "tileset": 6, "sprites": [{"kind": "npc", "x": 7, "y": 4}]}}}
    )
    assert shell.center_counter(64) is None


def test_step_off_targets_skips_cells_a_tile_pair_refuses(monkeypatch):
    """Both cells walkable is not enough — the engine refuses some moves between them."""
    import rom_truth as rt_mod

    truth = {"maps": {"1": {"width": 3, "height": 3, "grid": ["111"] * 3, "warps": [[1, 1, 9, 0]]}}}
    r = _reader_rig({0xD35E: 1, 0xD362: 1, 0xD361: 1}, truth)
    r.pairs = set()
    monkeypatch.setattr(rt_mod, "passable", lambda *a, **k: False)
    assert r.step_off_targets(1, 1, 1) == []


def test_the_bag_spells_a_machine_out():
    """ "HM03" tells an operator nothing. The cartridge knows it teaches SURF, so the bag can say
    so — this is the answer to "tell me what the item is" that the number was hiding."""
    r = _bag_rig([(198, 1), (60, 2)], items={"198": "HM03", "60": "FRESH WATER"})
    r.truth["machines"] = {"HM03": "SURF", "TM26": "EARTHQUAKE"}
    assert r.bag_named() == [("HM03", 1), ("FRESH WATER", 2)]
    assert r.bag_named(full=True) == [("HM03 SURF", 1), ("FRESH WATER", 2)]
    assert r.item_full_name("TM26") == "TM26 EARTHQUAKE"
    assert r.item_full_name("POKe FLUTE") == "POKe FLUTE"  # not a machine: unchanged


def test_cross_routes_a_failed_cross_to_surf_only_when_the_edge_is_water(monkeypatch):
    import road as road_mod

    def make():
        r = _reader_rig()
        r.battle = lambda io=None: None
        return r

    # a water edge: the cross fails and the edge has no modelled floor -> surf across it
    monkeypatch.setattr(road_mod, "cross_edge", lambda *a, **k: "stuck-on-edge")
    monkeypatch.setattr(road_mod, "edge_cells", lambda *a: (set(), "left"))
    monkeypatch.setattr(road_mod, "surf_cross", lambda *a, **k: "surfed")
    assert make().cross(1, 2) == "surfed"

    # a land edge that still fails is a real block, not water -> surf must not swallow it
    monkeypatch.setattr(road_mod, "edge_cells", lambda *a: ({(0, 0)}, "left"))
    assert make().cross(1, 2) == "stuck-on-edge"

    # the connection isn't modelled -> the water verdict was a guess, keep the land failure
    def no_map(*a):
        raise KeyError("1")

    monkeypatch.setattr(road_mod, "edge_cells", no_map)
    assert make().cross(1, 2) == "stuck-on-edge"

    # a no-path water edge also routes to surf
    monkeypatch.setattr(road_mod, "cross_edge", lambda *a, **k: "no-path")
    monkeypatch.setattr(road_mod, "edge_cells", lambda *a: (set(), "left"))
    monkeypatch.setattr(road_mod, "surf_cross", lambda *a, **k: "surfed")
    assert make().cross(1, 2) == "surfed"
