"""The quartermaster: purchase planning, catch policy, and RAM-verified errand driving.

Every driver test simulates the engine through a FakeIO whose presses mutate the same registers
the real errands read — the phases are verification-driven, so the fakes model *signals*, not
timings. The live gates behind these tests: the 2026-08-26 Cerulean errand (6 balls + 3 potions
bought, party healed to 63/63) and the first catch in project history (wild L10 Spearow, one
ball, party of two)."""

import json
import sys
import types

import pytest
import quartermaster as qm


class FakeIO:
    def __init__(self, mem=None, on_press=None):
        self.mem = dict(mem or {})
        self.pressed = []
        self.on_press = on_press

    def press(self, btn, hold=8, release=8):
        self.pressed.append(btn)
        if self.on_press:
            self.on_press(self, btn)

    def wait(self, frames=30):
        pass

    def read(self, addr):
        return self.mem.get(addr, 0)


def set_pos(io, mp, x, y):
    io.mem[qm.ADDR_MAP], io.mem[qm.ADDR_X], io.mem[qm.ADDR_Y] = mp, x, y


def set_money(io, amount):
    s = f"{amount:06d}"
    for k in range(3):
        io.mem[qm.ADDR_MONEY + k] = int(s[2 * k : 2 * k + 2], 16)


def set_bag(io, items):
    io.mem[qm.ADDR_BAG_COUNT] = len(items)
    for i, (item, qty) in enumerate(items):
        io.mem[qm.ADDR_BAG_ITEMS + 2 * i] = item
        io.mem[qm.ADDR_BAG_ITEMS + 2 * i + 1] = qty


def set_party(io, mons):
    io.mem[qm.ADDR_PARTY_COUNT] = len(mons)
    for i, (species, level, hp, max_hp) in enumerate(mons):
        base = qm.ADDR_PARTY_STRUCTS + qm.PARTY_STRUCT_SIZE * i
        io.mem[base] = species
        io.mem[base + 1], io.mem[base + 2] = hp >> 8, hp & 0xFF
        io.mem[base + 33] = level
        io.mem[base + 34], io.mem[base + 35] = max_hp >> 8, max_hp & 0xFF


# --------------------------------------------------------------------------- readers + adapter


def test_readers_decode_pos_money_bag_party():
    io = FakeIO()
    set_pos(io, 3, 19, 18)
    set_money(io, 2467)
    set_bag(io, [(qm.POKE_BALL, 6), (qm.POTION, 3)])
    set_party(io, [(0xB2, 22, 25, 63)])
    assert qm.read_pos(io) == (3, 19, 18)
    assert qm.read_money(io) == 2467
    assert qm.read_bag(io) == [(qm.POKE_BALL, 6), (qm.POTION, 3)]
    assert qm.read_party(io) == [{"species": 0xB2, "hp": 25, "level": 22, "max_hp": 63}]
    io.mem[qm.ADDR_MENU_CUR], io.mem[qm.ADDR_MENU_MAX], io.mem[qm.ADDR_TEXT_ID] = 1, 2, 14
    assert qm.menu_state(io) == (1, 2, 14)


def test_emuio_presses_and_reads_through_pyboy():
    class FakePyBoy:
        def __init__(self):
            self.ticks = 0
            self.buttons = []
            self.memory = {7: 42}

        def tick(self):
            self.ticks += 1

        def button_press(self, b):
            self.buttons.append(("+", b))

        def button_release(self, b):
            self.buttons.append(("-", b))

    pb = FakePyBoy()
    io = qm.EmuIO(pb)
    io.press("a", hold=2, release=3)
    io.wait(4)
    assert pb.buttons == [("+", "a"), ("-", "a")]
    assert pb.ticks == 2 + 3 + 4
    assert io.read(7) == 42


# --------------------------------------------------------------------------- pure policy


def test_plan_purchases_tops_up_and_respects_budget():
    # Bag already holds 4 balls: top up to 6, then potions with what's left of the budget.
    plan = qm.plan_purchases(2467, [(qm.POKE_BALL, 4)], balls=6, potions=4, reserve=100)
    assert plan == [(qm.POKE_BALL, 2), (qm.POTION, 4)]  # 400 + 1200 <= 2367
    # Tight money clamps quantities; a zero-qty want is dropped entirely.
    plan = qm.plan_purchases(500, [], balls=6, potions=4, reserve=100)
    assert plan == [(qm.POKE_BALL, 2)]
    assert qm.plan_purchases(10_000, [(qm.POKE_BALL, 6), (qm.POTION, 4)]) == []


def test_find_ball_prefers_the_cheapest():
    bag = [(qm.GREAT_BALL, 1), (qm.POKE_BALL, 2)]
    assert qm.find_ball(bag) == (1, qm.POKE_BALL)
    assert qm.find_ball([(qm.GREAT_BALL, 1)]) == (0, qm.GREAT_BALL)
    assert qm.find_ball([(qm.POKE_BALL, 0), (qm.POTION, 3)]) is None


class Wild:
    def __init__(self, species=0x05, hp=29, max_hp=29, battle_type=1):
        self.battle_type = battle_type
        self.enemy_species = species
        self.enemy_hp = hp
        self.enemy_max_hp = max_hp


def test_should_catch_throws_at_a_wanted_wild():
    bag = [(qm.POTION, 2), (qm.POKE_BALL, 5)]
    assert qm.should_catch(Wild(), [0xB2], bag, {0x05}) == (1, qm.POKE_BALL)


@pytest.mark.parametrize(
    "battle,party,bag,wanted,ratio",
    [
        (Wild(battle_type=2), [0xB2], [(qm.POKE_BALL, 1)], {0x05}, 1.0),  # trainer battle
        (Wild(), [0xB2], [(qm.POKE_BALL, 1)], {0x60}, 1.0),  # not wanted
        (Wild(), [0xB2, 0x05], [(qm.POKE_BALL, 1)], {0x05}, 1.0),  # already caught
        (Wild(), [1, 2, 3, 4, 6, 7], [(qm.POKE_BALL, 1)], {0x05}, 1.0),  # party full
        (Wild(hp=29), [0xB2], [(qm.POKE_BALL, 1)], {0x05}, 0.45),  # not weakened enough
        (Wild(), [0xB2], [(qm.POTION, 2)], {0x05}, 1.0),  # no ball
    ],
)
def test_should_catch_declines(battle, party, bag, wanted, ratio):
    assert qm.should_catch(battle, party, bag, wanted, hp_ratio_max=ratio) is None


def test_parse_catch_names_and_ids():
    assert qm.parse_catch("Oddish, spearow,5") == {0xB9, 0x05, 5}
    assert qm.parse_catch("") == set()
    with pytest.raises(SystemExit, match="unknown species"):
        qm.parse_catch("MissingNo")


def test_parse_buy_names():
    assert qm.parse_buy("poke_ball=6,potion=4") == [(qm.POKE_BALL, 6), (qm.POTION, 4)]
    assert qm.parse_buy("potion") == [(qm.POTION, 1)]
    assert qm.parse_buy("") == []
    with pytest.raises(SystemExit, match="unknown item"):
        qm.parse_buy("master_sword=1")


# --------------------------------------------------------------------------- verified driving


def test_settle_repeats_until_predicate_and_caps():
    io = FakeIO()
    state = {"n": 0}

    def action():
        state["n"] += 1

    qm.settle(io, lambda: state["n"] >= 3, action, cap=10, label="x")
    assert state["n"] == 3
    with pytest.raises(qm.QuartermasterError, match="no progress"):
        qm.settle(io, lambda: False, action, cap=2, label="x")


def test_flee_battle_runs_until_the_flag_clears():
    def on_press(io, btn):
        if btn == "a":  # each RUN confirm attempt decrements the scripted escape counter
            io.mem["tries"] = io.mem.get("tries", 0) + 1
            if io.mem["tries"] >= 2:
                io.mem[qm.ADDR_IN_BATTLE] = 0

    io = FakeIO({qm.ADDR_IN_BATTLE: 1}, on_press)
    qm.flee_battle(io)
    assert io.mem["tries"] == 2
    io2 = FakeIO({qm.ADDR_IN_BATTLE: 1})
    with pytest.raises(qm.QuartermasterError, match="still in battle"):
        qm.flee_battle(io2, cap=3)


OPEN_MAP = {
    "maps": {
        "5": {
            "width": 4,
            "height": 1,
            "tileset": 0,
            "grid": ["1111"],
            "tiles": ["2c2c2c2c"],
            "sprites": [],
        }
    }
}


def _walking_io(mp=5, x=0, y=0, warp_at=None, turn_first=False, refuse=None):
    """Presses move the position on the fake map; a warp flips the map id."""

    state = {"facing": None}

    def on_press(io, btn):
        if btn not in ("up", "down", "left", "right"):
            return
        if turn_first and state["facing"] != btn:
            state["facing"] = btn
            return
        dx = {"right": 1, "left": -1}.get(btn, 0)
        nx = io.mem[qm.ADDR_X] + dx
        if refuse and (nx, io.mem[qm.ADDR_Y]) == refuse:
            return
        io.mem[qm.ADDR_X] = nx
        if warp_at and (nx, io.mem[qm.ADDR_Y]) == warp_at:
            io.mem[qm.ADDR_MAP] = 99

    io = FakeIO(on_press=on_press)
    set_pos(io, mp, x, y)
    return io


def test_walk_to_reaches_the_target():
    io = _walking_io()
    qm.walk_to(io, OPEN_MAP, set(), 5, (3, 0))
    assert qm.read_pos(io) == (5, 3, 0)


def test_walk_to_returns_on_map_change():
    io = _walking_io(warp_at=(2, 0))
    qm.walk_to(io, OPEN_MAP, set(), 5, (3, 0))
    assert qm.read_pos(io)[0] == 99


def test_walk_to_retries_a_turn_in_place():
    io = _walking_io(turn_first=True)
    qm.walk_to(io, OPEN_MAP, set(), 5, (2, 0))
    assert qm.read_pos(io) == (5, 2, 0)


def test_walk_to_flees_a_battle_first():
    io = _walking_io()
    io.mem[qm.ADDR_IN_BATTLE] = 1
    orig = qm.flee_battle

    def clear(io_, cap=25):
        io_.mem[qm.ADDR_IN_BATTLE] = 0

    qm.flee_battle = clear
    try:
        qm.walk_to(io, OPEN_MAP, set(), 5, (1, 0))
    finally:
        qm.flee_battle = orig
    assert qm.read_pos(io) == (5, 1, 0)


def test_walk_to_raises_on_no_path_and_wedge_and_cap():
    blocked_map = {
        "maps": {"5": {"width": 4, "height": 1, "tileset": 0, "grid": ["1011"], "tiles": ["2c2c2c2c"], "sprites": []}}
    }
    with pytest.raises(qm.QuartermasterError, match="no path"):
        qm.walk_to(_walking_io(), blocked_map, set(), 5, (3, 0))
    # A persistently refused step is VETOED (a parked body), and a 1-row map has no detour:
    with pytest.raises(qm.QuartermasterError, match="no path"):
        qm.walk_to(_walking_io(refuse=(1, 0)), OPEN_MAP, set(), 5, (3, 0))
    bouncy = _walking_io(warp_at=None)

    def bounce(io, btn):  # moves, but never closer: position oscillates via the refuse hack
        io.mem[qm.ADDR_X] = 1 - io.mem[qm.ADDR_X]

    bouncy.on_press = bounce
    with pytest.raises(qm.QuartermasterError, match="steps without reaching"):
        qm.walk_to(bouncy, OPEN_MAP, set(), 5, (3, 0), cap=5)


def test_leave_interior_steps_down_off_the_mat():
    def on_press(io, btn):
        if btn == "down":
            io.mem[qm.ADDR_MAP] = 3

    io = FakeIO(on_press=on_press)
    set_pos(io, 67, 3, 7)
    qm.leave_interior(io, 67)
    assert qm.read_pos(io)[0] == 3
    io2 = FakeIO()
    set_pos(io2, 67, 3, 7)
    with pytest.raises(qm.QuartermasterError, match="still on map"):
        qm.leave_interior(io2, 67)


# --------------------------------------------------------------------------- the shop counter


class FakeShopIO(FakeIO):
    """A Gen 1 mart in five registers: A opens the greeting then the shop menu; in the item
    list the cursor obeys up/down; A enters quantity mode (up = +1), then a confirm A moves the
    money and the bag — the exact signal order the live probe measured."""

    def __init__(self, stock, prices):
        super().__init__()
        self.stock, self.prices = stock, prices
        self.phase = "closed"
        self.qty = 1
        set_pos(self, 67, 2, 5)
        set_money(self, 2467)
        set_bag(self, [])
        self.bag_now = {}

    def press(self, btn, hold=8, release=8):
        self.pressed.append(btn)
        cur = self.mem.get(qm.ADDR_MENU_CUR, 0)
        if self.phase == "closed" and btn == "a":
            self.phase = "greeting"
        elif self.phase == "greeting" and btn == "a":
            self.phase = "shop_menu"
            self.mem[qm.ADDR_MENU_CUR], self.mem[qm.ADDR_MENU_MAX], self.mem[qm.ADDR_TEXT_ID] = 0, 2, 14
        elif self.phase == "shop_menu":
            if btn == "a":
                self.phase = "item_list"
                self.mem[qm.ADDR_MENU_CUR], self.mem[qm.ADDR_TEXT_ID] = 0, 13
            elif btn == "b":
                self.phase = "closed"
                self.mem[qm.ADDR_TEXT_ID] = 1  # this fake's clerk resets it; the real one lies
        elif self.phase == "item_list":
            if btn == "down":
                self.mem[qm.ADDR_MENU_CUR] = min(len(self.stock) - 1, cur + 1)
            elif btn == "up":
                self.mem[qm.ADDR_MENU_CUR] = max(0, cur - 1)
            elif btn == "a":
                self.phase = "quantity"
                self.qty = 1
            elif btn == "b":
                self.phase = "shop_menu"
                self.mem[qm.ADDR_TEXT_ID] = 14
        elif self.phase == "quantity":
            if btn == "up":
                self.qty += 1
            elif btn == "a":
                self.phase = "confirm"
        elif self.phase == "confirm" and btn == "a":
            item = self.stock[self.mem.get(qm.ADDR_MENU_CUR, 0)]
            cost = self.prices[item] * self.qty
            set_money(self, qm.read_money(self) - cost)
            self.bag_now[item] = self.bag_now.get(item, 0) + self.qty
            set_bag(self, sorted(self.bag_now.items()))
            self.phase = "item_list"


CERULEAN_SHOP = qm.SHOPS[3]


def test_buy_executes_the_plan_and_reports_gains():
    io = FakeShopIO(CERULEAN_SHOP.stock, qm.PRICES)
    bought = qm.buy(io, CERULEAN_SHOP, [(qm.POKE_BALL, 6), (qm.POTION, 3)])
    assert bought == [(qm.POKE_BALL, 6), (qm.POTION, 3)]
    assert qm.read_money(io) == 2467 - 6 * 200 - 3 * 300
    assert io.pressed[0] == CERULEAN_SHOP.face  # faces the clerk before talking


def test_buy_caps_out_when_the_counter_never_answers():
    io = FakeIO()
    set_pos(io, 67, 2, 5)
    with pytest.raises(qm.QuartermasterError, match="open shop menu"):
        qm.buy(io, CERULEAN_SHOP, [(qm.POKE_BALL, 1)])


def test_heal_mashes_a_until_the_party_reads_full():
    def on_press(io, btn):
        if btn == "a":
            io.mem["a"] = io.mem.get("a", 0) + 1
            if io.mem["a"] >= 3:
                set_party(io, [(0xB2, 22, 63, 63)])

    io = FakeIO(on_press=on_press)
    set_party(io, [(0xB2, 22, 25, 63)])
    qm.heal(io, qm.CENTERS[3].face)
    assert qm.read_party(io)[0]["hp"] == 63
    io2 = FakeIO()
    set_party(io2, [(0xB2, 22, 25, 63)])
    with pytest.raises(qm.QuartermasterError, match="nurse heal"):
        qm.heal(io2, qm.CENTERS[3].face)


# --------------------------------------------------------------------------- errand composition


def test_run_errand_composes_mart_then_center(monkeypatch):
    calls = []
    monkeypatch.setattr(qm, "walk_to", lambda io, t, p, m, xy, cap=400: calls.append(("walk", m, xy)))
    monkeypatch.setattr(qm, "buy", lambda io, shop, plan: calls.append(("buy", plan)) or [(qm.POKE_BALL, 2)])
    monkeypatch.setattr(qm, "heal", lambda io, c: calls.append(("heal",)))
    monkeypatch.setattr(qm, "leave_interior", lambda io, m: calls.append(("leave", m)))
    io = FakeIO()
    set_pos(io, 3, 0, 19)
    set_money(io, 367)
    set_bag(io, [(qm.POKE_BALL, 6)])
    set_party(io, [(0xB2, 22, 63, 63)])
    report = qm.run_errand(io, {"maps": {}, "tile_pairs": []}, [(qm.POKE_BALL, 2)], True)
    shop, center = qm.SHOPS[3], qm.CENTERS[3]
    assert calls == [
        ("walk", 3, shop.door_xy),
        ("walk", 67, shop.counter_xy),
        ("buy", [(qm.POKE_BALL, 2)]),
        ("walk", 67, shop.exit_mats),
        ("leave", 67),
        ("walk", 3, center.door_xy),
        ("walk", 64, center.counter_xy),
        ("heal",),
        ("walk", 64, center.exit_mats),
        ("leave", 64),
    ]
    assert report["bought"] == [(qm.POKE_BALL, 2)] and report["healed"] and report["money"] == 367


def test_run_errand_refuses_unknown_cities():
    io = FakeIO()
    set_pos(io, 42, 0, 0)
    with pytest.raises(qm.QuartermasterError, match="no known mart"):
        qm.run_errand(io, {"maps": {}, "tile_pairs": []}, [(qm.POKE_BALL, 1)], False)
    with pytest.raises(qm.QuartermasterError, match="no known center"):
        qm.run_errand(io, {"maps": {}, "tile_pairs": []}, None, True)


def test_run_errand_skips_phases_not_asked_for(monkeypatch):
    monkeypatch.setattr(qm, "walk_to", lambda *a, **k: (_ for _ in ()).throw(AssertionError("walked")))
    io = FakeIO()
    set_pos(io, 3, 0, 19)
    report = qm.run_errand(io, {"maps": {}, "tile_pairs": []}, None, False)
    assert report["bought"] == [] and not report["healed"]


# --------------------------------------------------------------------------- cli


def test_main_runs_an_errand_end_to_end(tmp_path, monkeypatch, capsys):
    saved = {}

    class FakePyBoy:
        def __init__(self, rom, window=None):
            import collections

            self.memory = collections.defaultdict(int)

        def load_state(self, f):
            f.read()

        def save_state(self, f):
            f.write(b"out")
            saved["ok"] = True

        def stop(self):
            saved["stopped"] = True

    monkeypatch.setitem(sys.modules, "pyboy", types.SimpleNamespace(PyBoy=FakePyBoy))
    import rom_truth

    monkeypatch.setattr(rom_truth, "load_truth", lambda *a, **k: {"maps": {}, "tile_pairs": []})
    monkeypatch.setattr(
        qm,
        "run_errand",
        lambda io, truth, plan, do_heal: {
            "bought": plan,
            "healed": do_heal,
            "money": 367,
            "party": [{"species": 0xB2, "level": 22, "hp": 63, "max_hp": 63}],
            "bag": [],
        },
    )
    state = tmp_path / "in.state"
    state.write_bytes(b"x")
    out = tmp_path / "out.state"
    rc = qm.main(["errand", "--state", str(state), "--out", str(out), "--buy", "poke_ball=6", "--heal"])
    assert rc == 0 and saved == {"ok": True, "stopped": True}
    assert out.read_bytes() == b"out"
    text = capsys.readouterr().out
    assert "healed True" in text and "(178, 22, 63, 63)" in text


def test_main_saves_the_state_even_when_the_errand_dies(tmp_path, monkeypatch):
    class FakePyBoy:
        def __init__(self, rom, window=None):
            self.memory = {}

        def load_state(self, f):
            f.read()

        def save_state(self, f):
            f.write(b"partial")

        def stop(self):
            pass

    monkeypatch.setitem(sys.modules, "pyboy", types.SimpleNamespace(PyBoy=FakePyBoy))
    import rom_truth

    monkeypatch.setattr(rom_truth, "load_truth", lambda *a, **k: {"maps": {}, "tile_pairs": []})

    def boom(*a, **k):
        raise qm.QuartermasterError("wedged")

    monkeypatch.setattr(qm, "run_errand", boom)
    state = tmp_path / "in.state"
    state.write_bytes(b"x")
    out = tmp_path / "out.state"
    with pytest.raises(qm.QuartermasterError):
        qm.main(["errand", "--state", str(state), "--out", str(out)])
    assert out.read_bytes() == b"partial"  # the wreck is saved for diagnosis


def test_shop_and_center_tables_are_coherent():
    for city, shop in qm.SHOPS.items():
        assert shop.city_map == city and shop.stock and shop.face in ("up", "down", "left", "right")
    for city, center in qm.CENTERS.items():
        assert center.city_map == city and center.face in ("up", "down", "left", "right")
    json.dumps({"shops": len(qm.SHOPS), "centers": len(qm.CENTERS)})  # tables stay serializable


def test_walk_to_reroutes_around_a_parked_body():
    """A customer parked on one of the mart's two exit mats (live-measured): the blocked
    TARGET is dropped after six stalls, the tile is vetoed, and the walk detours over the
    second row to the free mat."""
    two_row = {
        "maps": {
            "5": {
                "width": 4,
                "height": 2,
                "tileset": 0,
                "grid": ["1111", "1111"],
                "tiles": ["2c2c2c2c", "2c2c2c2c"],
                "sprites": [],
            }
        }
    }

    state = {"facing": None}

    def on_press(io, btn):
        d = {"right": (1, 0), "left": (-1, 0), "down": (0, 1), "up": (0, -1)}.get(btn)
        if not d:
            return
        nx, ny = io.mem[qm.ADDR_X] + d[0], io.mem[qm.ADDR_Y] + d[1]
        if (nx, ny) == (2, 0):
            return  # the body
        io.mem[qm.ADDR_X], io.mem[qm.ADDR_Y] = nx, ny

    io = FakeIO(on_press=on_press)
    set_pos(io, 5, 0, 0)
    qm.walk_to(io, two_row, set(), 5, {(2, 0), (3, 0)})
    assert qm.read_pos(io) == (5, 3, 0)
    _ = state


def test_run_errand_leaves_a_known_interior_first(monkeypatch):
    calls = []
    monkeypatch.setattr(qm, "walk_to", lambda io, t, p, m, xy, cap=400: calls.append(("walk", m, xy)))
    monkeypatch.setattr(qm, "leave_interior", lambda io, m: (calls.append(("leave", m)), set_pos(io, 3, 25, 26)))
    monkeypatch.setattr(qm, "heal", lambda io, c: calls.append(("heal",)))
    io = FakeIO()
    set_pos(io, 67, 3, 6)  # a wedge save left us INSIDE the mart
    set_party(io, [(0xB2, 27, 76, 76)])
    report = qm.run_errand(io, {"maps": {}, "tile_pairs": []}, None, True)
    assert calls[0] == ("walk", 67, qm.SHOPS[3].exit_mats) and calls[1] == ("leave", 67)
    assert report["healed"]


def test_battle_through_fights_until_the_flag_clears():
    def on_press(io, btn):
        if btn == "a":
            io.mem["hits"] = io.mem.get("hits", 0) + 1
            if io.mem["hits"] >= 3:
                io.mem[qm.ADDR_IN_BATTLE] = 0

    io = FakeIO({qm.ADDR_IN_BATTLE: 2}, on_press)
    qm.battle_through(io)
    assert io.mem["hits"] == 3
    with pytest.raises(qm.QuartermasterError, match="still fighting"):
        qm.battle_through(FakeIO({qm.ADDR_IN_BATTLE: 2}), cap=3)


def test_walk_to_fights_trainers_and_stubborn_wilds(monkeypatch):
    io = _walking_io()
    io.mem[qm.ADDR_IN_BATTLE] = 2  # a trainer: cannot be fled
    fought = {}
    monkeypatch.setattr(
        qm, "battle_through", lambda i, cap=150: (fought.setdefault("t", True), i.mem.__setitem__(qm.ADDR_IN_BATTLE, 0))
    )
    qm.walk_to(io, OPEN_MAP, set(), 5, (1, 0))
    assert fought.get("t")
    io2 = _walking_io()
    io2.mem[qm.ADDR_IN_BATTLE] = 1  # a wild that will not let go: flee raises, fight wins
    monkeypatch.setattr(qm, "flee_battle", lambda i, cap=25: (_ for _ in ()).throw(qm.QuartermasterError("flee")))
    monkeypatch.setattr(qm, "battle_through", lambda i, cap=150: i.mem.__setitem__(qm.ADDR_IN_BATTLE, 0))
    qm.walk_to(io2, OPEN_MAP, set(), 5, (1, 0))
    assert qm.read_pos(io2) == (5, 1, 0)


def test_walk_to_can_press_through_sprites(monkeypatch):
    called = {}
    import rom_truth as rt

    real = rt.path_on_map

    def spy(truth, pairs, mid, start, targets, blocked=None):
        called["blocked"] = set(blocked or ())
        return real(truth, pairs, mid, start, targets, blocked=blocked)

    monkeypatch.setattr(rt, "path_on_map", spy)
    io = _walking_io()
    spr_map = {"maps": {"5": dict(OPEN_MAP["maps"]["5"], sprites=[{"kind": "npc", "x": 3, "y": 0}])}}
    qm.walk_to(io, spr_map, set(), 5, (1, 0), block_sprites=False)
    assert (3, 0) not in called["blocked"]  # bodies are not walls on a journey


def _journey_truth():
    return {
        "maps": {
            "3": {"width": 2, "height": 2, "grid": ["11", "11"], "warps": [[1, 0, 62, 0]]},
            "62": {"width": 2, "height": 2, "grid": ["11", "11"], "warps": [[1, 0, 255, 7]]},
            "17": {"width": 2, "height": 2, "grid": ["11", "11"], "warps": []},
        },
        "tile_pairs": [],
    }


def test_journey_step_kinds(monkeypatch):
    io = FakeIO()
    calls = []
    monkeypatch.setattr(qm, "walk_to", lambda i, t, p, m, xy, cap=400, block_sprites=True: calls.append((m, xy)))
    monkeypatch.setattr(qm, "leave_interior", lambda i, m: calls.append(("leave", m)))
    truth = _journey_truth()
    pairs = set()
    chain = {3: ("cerulean-south", 16), 62: ("back-door", 3), 17: ("edge-south", 5), 74: ("mats-out", 17)}
    set_pos(io, 62, 0, 0)
    assert qm.journey_step(io, truth, pairs, chain)
    assert calls[-1] == (62, {(3, 0)})
    set_pos(io, 17, 0, 0)
    assert qm.journey_step(io, truth, pairs, chain)
    truth["maps"]["74"] = truth["maps"]["62"]
    set_pos(io, 74, 0, 0)
    assert qm.journey_step(io, truth, pairs, chain)
    assert calls[-1] == ("leave", 74)
    set_pos(io, 99, 0, 0)
    assert not qm.journey_step(io, truth, pairs, chain)  # off the chain


def test_journey_step_cerulean_falls_back_to_the_house(monkeypatch):
    io = FakeIO()
    seen = []

    def wt(i, t, p, m, xy, cap=400, block_sprites=True):
        seen.append(xy)
        if len(seen) == 1:
            raise qm.QuartermasterError("no path")

    monkeypatch.setattr(qm, "walk_to", wt)
    set_pos(io, 3, 0, 0)
    assert qm.journey_step(io, FakeIO and _journey_truth(), set(), {3: ("cerulean-south", 16)})
    assert seen[1] == {(1, 0)}  # the door to 62


def test_journey_arrives_or_raises(monkeypatch):
    io = FakeIO()
    set_pos(io, 5, 0, 0)
    qm.journey(io, _journey_truth(), 5, {})  # already there
    set_pos(io, 99, 0, 0)
    with pytest.raises(qm.QuartermasterError, match="not on the chain"):
        qm.journey(io, _journey_truth(), 5, {})
    hops = {"n": 0}

    def step(i, t, p, c):
        hops["n"] += 1
        return True

    monkeypatch.setattr(qm, "journey_step", step)
    set_pos(io, 3, 0, 0)
    with pytest.raises(qm.QuartermasterError, match="hops without"):
        qm.journey(io, _journey_truth(), 5, {3: ("edge-south", 16)}, max_hops=3)
    assert hops["n"] == 3


def test_journey_step_warp_and_step_off_breaks(monkeypatch):
    calls = []
    monkeypatch.setattr(qm, "walk_to", lambda i, t, p, m, xy, cap=400, block_sprites=True: calls.append((m, xy)))
    truth = _journey_truth()
    io = FakeIO(on_press=lambda i, b: set_pos(i, 16, 0, 0))  # the first step-off press hands over
    set_pos(io, 3, 0, 1)
    assert qm.journey_step(io, truth, set(), {3: ("edge-south", 16)})
    assert io.pressed == ["down"]  # broke out after the map changed
    io2 = FakeIO()
    set_pos(io2, 3, 0, 0)
    assert qm.journey_step(io2, truth, set(), {3: ("warp-to", 62)})
    assert calls[-1] == (3, {(1, 0)})  # the extracted door tile for dest 62
    io3 = FakeIO(on_press=lambda i, b: set_pos(i, 3, 27, 9))
    set_pos(io3, 62, 3, 0)
    assert qm.journey_step(io3, truth, set(), {62: ("back-door", 3)})
    assert io3.pressed == ["up"]


def test_cli_go_vermilion(tmp_path, monkeypatch, capsys):
    class FakePyBoy:
        def __init__(self, rom, window=None):
            import collections

            self.memory = collections.defaultdict(int)

        def load_state(self, f):
            f.read()

        def save_state(self, f):
            f.write(b"out")

        def stop(self):
            pass

    monkeypatch.setitem(sys.modules, "pyboy", types.SimpleNamespace(PyBoy=FakePyBoy))
    import rom_truth

    monkeypatch.setattr(rom_truth, "load_truth", lambda *a, **k: {"maps": {}, "tile_pairs": []})
    monkeypatch.setattr(
        qm, "run_errand", lambda io, t, p, h: {"bought": [], "healed": False, "money": 0, "party": [], "bag": []}
    )
    seen = {}
    monkeypatch.setattr(qm, "journey", lambda io, t, d, c: seen.update(dest=d))
    state = tmp_path / "in.state"
    state.write_bytes(b"x")
    out = tmp_path / "out.state"
    assert qm.main(["errand", "--state", str(state), "--out", str(out), "--go", "vermilion"]) == 0
    assert seen["dest"] == qm.VERMILION_CITY_MAP
