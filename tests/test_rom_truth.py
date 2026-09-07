"""ROM-truth parser against a synthetic mini-ROM with the real Gen-1 layout.

The synthetic image places every table at its true offset (header banks/pointers, tilesets) so
the parser exercised here is byte-for-byte the one that runs on the real ROM — which was
validated against live-measured ground truth (Pewter's seven warps, the gym's LAST_MAP mats,
Route 3's empty table, 465/465 learned-cell agreement on map 2)."""

import hashlib
import json

import pytest
import rom_truth
from rom_truth import (
    LAST_MAP,
    MAP_HEADER_BANKS,
    MAP_HEADER_POINTERS,
    TILESETS,
    describe_route,
    load_truth,
    parse_map,
    parse_rom,
    route,
    seed_worldmap,
)
from world_map import WorldMap

WALK, WALL, GRASS, LIP, LEDGE = 0x00, 0x01, 0x52, 0x03, 0x05
LEDGES_OFF = 0x0D00
STATS_OFF, DEX_OFF, NAMES_OFF = 0x8000, 0x9800, 0xA000
ITEMS_OFF = 0xB000  # the item-name list; found by content signature (it opens with MASTER BALL)
MOVES_OFF = 0xB400  # the move-name list; found by POUND at id 1
MACHINES_OFF = 0xBC00  # 50 TM move ids then the five HM ids
WILD_PTRS, WILD_BLOCK = 0x4600, 0x4800
EVOS_PTRS, EVOS_BLOCK, EVOS_BLOCK2 = 0x5000, 0x5200, 0x5220  # bank 1: addr == file offset
TYPECHART_OFF = 0x0A00

# Home-bank layout for the synthetic image (all pointers < 0x4000 so bank math stays simple;
# _faddr's banked branch is covered by the >= 0x4000 blockset pointer below).
COLL = 0x0F00
BLOCKS = 0x14000  # bank 5, addr 0x4000 — exercises the banked-address branch
HDR0, HDR1, HDR2, HDR3 = 0x2000, 0x2100, 0x2200, 0x2300
OBJ0, OBJ1, OBJ2 = 0x2050, 0x2150, 0x2250
DATA0, DATA1, DATA2 = 0x3000, 0x3010, 0x3020


def _u16(v):
    return [v & 0xFF, v >> 8]


def build_rom() -> bytearray:
    rom = bytearray(0x18000)  # 6 banks
    # Tileset 0: bank 5 blockset (addr 0x4000), home-bank collision list, grass tile 0x52.
    rom[TILESETS : TILESETS + 12] = bytes([5, *_u16(0x4000), 0, 0, *_u16(COLL), 0, 0, 0, GRASS, 0])
    rom[COLL : COLL + 4] = bytes([WALK, GRASS, LIP, 0xFF])
    # Block 0: all walkable. Block 1: all wall. Block 2: bottom-left tiles grass. Block 3: lip.
    rom[BLOCKS : BLOCKS + 16] = bytes([WALK] * 16)
    rom[BLOCKS + 16 : BLOCKS + 32] = bytes([WALL] * 16)
    b2 = [WALK] * 16
    for idx in (4, 6, 12, 14):  # the bottom-left tile of each 2x2 quad
        b2[idx] = GRASS
    rom[BLOCKS + 32 : BLOCKS + 48] = bytes(b2)
    rom[BLOCKS + 48 : BLOCKS + 64] = bytes([LIP] * 16)
    # TilePairCollisionsLand: WALK <-> LIP is refused on tileset 0 even though both are walkable.
    rom[rom_truth.TILE_PAIR_COLLISIONS_LAND : rom_truth.TILE_PAIR_COLLISIONS_LAND + 4] = bytes([0, WALK, LIP, 0xFF])
    # LedgeTiles at its real shape (facing, standing, ledge, input; facing must agree with input,
    # which is what ledge_hops scans for). Five records so the fixture's is the longest table.
    rom[LEDGES_OFF : LEDGES_OFF + 21] = bytes(
        [0x00, WALK, LEDGE, 0x80]  # down
        + [0x00, GRASS, LEDGE, 0x80]  # down, from grass
        + [0x08, WALK, 0x06, 0x20]  # left
        + [0x0C, WALK, 0x07, 0x10]  # right
        + [0x00, WALK, 0x06, 0x80]  # down over the left-ledge tile
        + [0xFF]
    )

    # Wild-encounter data at its real shape: a per-map pointer table (bank 1) where every map
    # shares one grass block — ten (level, Rhydon) pairs at rate 8, no water table.
    rom[WILD_BLOCK : WILD_BLOCK + 22] = bytes([8] + [3, 1] * 10 + [0])
    for i in range(248):
        rom[WILD_PTRS + 2 * i : WILD_PTRS + 2 * i + 2] = bytes([0x00, 0x48])

    # TypeEffects at its real shape: (attacker, defender, mult*10) triples, 0xFF-terminated.
    # 20=fire 21=water 22=grass 17=electric 04=ground; fire->grass 2x, electric->ground 0x.
    tc = []
    for a, d, e in (
        (0x14, 0x16, 0x14),
        (0x15, 0x14, 0x14),
        (0x16, 0x15, 0x14),
        (0x17, 0x04, 0x00),
        (0x14, 0x15, 0x05),
        (0x15, 0x16, 0x05),
    ) * 6:
        tc += [a, d, e]
    rom[TYPECHART_OFF : TYPECHART_OFF + len(tc)] = bytes(tc)
    rom[TYPECHART_OFF + len(tc)] = 0xFF

    # Evolutions/learnsets at their real shape: 190 same-bank pointers, one block per species —
    # a level evolution + learnset shared by ids 1..189, and an item + trade pair for id 190.
    rom[EVOS_BLOCK : EVOS_BLOCK + 9] = bytes([1, 16, 2, 0, 9, 52, 15, 43, 0])
    rom[EVOS_BLOCK2 : EVOS_BLOCK2 + 9] = bytes([2, 10, 1, 5, 3, 1, 6, 0, 0])
    for i in range(190):
        p = EVOS_BLOCK2 if i == 189 else EVOS_BLOCK
        rom[EVOS_PTRS + 2 * i : EVOS_PTRS + 2 * i + 2] = bytes(_u16(p))

    # Species tables, at their real shapes, found by the same content signatures as on the real
    # ROM: base stats open with Bulbasaur's row, the dex-order table opens with Rhydon's 112, and
    # the name table is found via RHYDON at internal id 1. Only id 1 resolves to a name here.
    rom[STATS_OFF : STATS_OFF + 10] = bytes([1, 45, 49, 49, 45, 65, 0x16, 0x03, 45, 64])
    rom[DEX_OFF : DEX_OFF + 9] = bytes([112, 115, 32, 35, 21, 100, 34, 80, 2])
    name = bytes(0x80 + ord(c) - ord("A") for c in "RHYDON") + bytes([0x50] * 4)
    rom[NAMES_OFF : NAMES_OFF + 10] = name
    # Id 2 exercises the special-character branch: NIDORAN + the male symbol (0xEF).
    nido = bytes(0x80 + ord(c) - ord("A") for c in "NIDORAN") + bytes([0xEF, 0x50, 0x50])
    rom[NAMES_OFF + 10 : NAMES_OFF + 20] = nido

    # Item names, at their real shape: a 0x50-terminated list opening with MASTER BALL, which is
    # the signature `item_names` finds it by. Without it the synthetic image has no item table and
    # the extraction's whole naming path goes unexercised wherever the real ROM is absent — which
    # is CI, where rom/ does not ship.
    def item_bytes(name: str) -> bytes:
        out = bytearray()
        for ch in name:
            out.append(0x7F if ch == " " else 0x80 + ord(ch) - ord("A"))
        out.append(0x50)
        return bytes(out)

    blob = b"".join(item_bytes(n) for n in ("MASTER BALL", "ULTRA BALL", "GREAT BALL")) + bytes([0x50])
    rom[ITEMS_OFF : ITEMS_OFF + len(blob)] = blob

    # Move names at their real shape (POUND is id 1), with the five field moves at the ids the
    # machine table points at, and the machine table itself: 50 TM ids then the HM ids. The HM run
    # is the signature `machine_moves` finds the table by.
    field = {15: "CUT", 19: "FLY", 57: "SURF", 70: "STRENGTH", 148: "FLASH"}
    moves = b""
    for mid in range(1, 149):
        name = "POUND" if mid == 1 else field.get(mid, f"MOVE{chr(65 + mid % 26)}{chr(65 + mid // 26)}")
        moves += item_bytes(name)
    rom[MOVES_OFF : MOVES_OFF + len(moves)] = moves
    machines = bytes([(i % 140) + 1 for i in range(50)]) + bytes([15, 19, 57, 70, 148])
    rom[MACHINES_OFF : MACHINES_OFF + len(machines)] = machines

    for mid, hdr in ((0, HDR0), (1, HDR1), (2, HDR2), (3, HDR3)):
        rom[MAP_HEADER_BANKS + mid] = 0
        rom[MAP_HEADER_POINTERS + 2 * mid : MAP_HEADER_POINTERS + 2 * mid + 2] = bytes(_u16(hdr))

    # Map 0 — indoor 4x4: door mats to LAST_MAP, one sign, npc + trainer + item sprites.
    rom[HDR0 : HDR0 + 10] = bytes([0, 2, 2, *_u16(DATA0), 0, 0, 0, 0, 0])  # no connections
    rom[HDR0 + 10 : HDR0 + 12] = bytes(_u16(OBJ0))
    rom[DATA0 : DATA0 + 4] = bytes([0, 0, 0, 0])  # all-walkable blocks
    rom[OBJ0 : OBJ0 + 2] = bytes([0, 2])  # border, 2 warps
    rom[OBJ0 + 2 : OBJ0 + 10] = bytes([3, 1, 0, LAST_MAP, 3, 2, 0, LAST_MAP])  # (y,x,dwarp,dmap)
    rom[OBJ0 + 10] = 1  # one sign
    rom[OBJ0 + 11 : OBJ0 + 14] = bytes([1, 1, 7])
    rom[OBJ0 + 14] = 3  # sprites: npc, trainer, item
    rom[OBJ0 + 15 : OBJ0 + 21] = bytes([1, 2 + 4, 1 + 4, 0, 0, 0x02])
    rom[OBJ0 + 21 : OBJ0 + 29] = bytes([2, 3 + 4, 0 + 4, 0, 0, 0x41, 9, 9])
    rom[OBJ0 + 29 : OBJ0 + 36] = bytes([3, 0 + 4 - 4, 0 + 4, 0, 0, 0x81, 5])  # y-4 -> -4: off-map

    # Map 1 — outdoor 4x4: east connection to map 2, a warp into map 0, a grass/wall mix.
    rom[HDR1 : HDR1 + 10] = bytes([0, 2, 2, *_u16(DATA1), 0, 0, 0, 0, 0x01])  # east
    rom[HDR1 + 10 : HDR1 + 21] = bytes([2, 0, 0, 0, 0, 0, 0, 8, 0, 0, 0])  # east -> map 2, rows +8
    rom[HDR1 + 21 : HDR1 + 23] = bytes(_u16(OBJ1))
    rom[DATA1 : DATA1 + 4] = bytes([0, 1, 2, 0])  # walk, wall, grass, walk
    rom[OBJ1 : OBJ1 + 2] = bytes([0, 1])
    rom[OBJ1 + 2 : OBJ1 + 6] = bytes([0, 0, 0, 0])  # (0,0) -> map 0
    rom[OBJ1 + 6] = 0  # signs
    rom[OBJ1 + 7] = 0  # sprites

    # Map 2 — outdoor: west connection to 1, plus a warp to an absent map (filtered from routing).
    rom[HDR2 : HDR2 + 10] = bytes([0, 2, 2, *_u16(DATA2), 0, 0, 0, 0, 0x02])  # west
    rom[HDR2 + 10 : HDR2 + 21] = bytes([1, 0, 0, 0, 0, 0, 0, 248, 0, 0, 0])  # west -> map 1, rows -8
    rom[HDR2 + 21 : HDR2 + 23] = bytes(_u16(OBJ2))
    rom[DATA2 : DATA2 + 4] = bytes([0, 3, 0, 0])  # lip blocks top-right: a walkable pair-collision
    rom[OBJ2 : OBJ2 + 2] = bytes([0, 1])
    rom[OBJ2 + 2 : OBJ2 + 6] = bytes([1, 1, 0, 200])  # dest map 200: not extracted
    rom[OBJ2 + 6] = 0
    rom[OBJ2 + 7] = 0

    # Map 3 — degenerate header (zero-width): parse_map returns None.
    rom[HDR3 : HDR3 + 3] = bytes([0, 0, 0])
    return rom


@pytest.fixture()
def rom(tmp_path):
    data = build_rom()
    p = tmp_path / "mini.gb"
    p.write_bytes(data)
    return p, bytes(data)


def test_evolutions_table_found_by_signature(rom):
    """The pointer-run scan lands on the true table start (windows shifted into the run lose
    their tail to block data), and all three evolution methods decode."""
    _, data = rom
    evo = rom_truth.evolutions_table(data)
    assert len(evo) == 190
    assert evo["1"] == {"evolutions": [["level", 16, 2]], "learnset": [[9, 52], [15, 43]]}
    assert evo["190"] == {"evolutions": [["item", 10, 5], ["trade", 1, 6]], "learnset": []}


def test_type_chart_found_by_signature(rom):
    _, data = rom
    chart = rom_truth.type_chart(data)
    assert chart["fire"]["grass"] == 2.0
    assert chart["electric"]["ground"] == 0.0
    assert chart["fire"]["water"] == 0.5
    assert "rock" not in chart.get("fire", {})  # absent pairs stay neutral


def test_type_chart_missing_raises():
    with pytest.raises(ValueError, match="type-effectiveness"):
        rom_truth.type_chart(bytes(0x4000))


def test_evolutions_table_missing_raises():
    with pytest.raises(ValueError, match="evolutions table"):
        rom_truth.evolutions_table(bytes(0x8000))


def test_evolutions_table_rejects_malformed_blocks():
    """Near-miss pointer runs are refused by shape: too many evolution entries, an
    out-of-range move id, and a learnset longer than any real species carries."""
    rom = bytearray(0x8000)
    bad1, bad2, bad3 = 0x6000, 0x6100, 0x6200
    rom[bad1 : bad1 + 13] = bytes([1, 16, 2] * 4 + [0])  # four evolutions: more than real
    rom[bad2 : bad2 + 4] = bytes([0, 9, 250, 0])  # move id 250: out of range
    rom[bad3 : bad3 + 2 * 26 + 2] = bytes([0] + [9, 52] * 26 + [0])  # 26 learn pairs
    for run, target in ((0x4400, bad1), (0x4800, bad2), (0x4C00, bad3)):
        for i in range(190):
            rom[run + 2 * i : run + 2 * i + 2] = bytes(_u16(target))
    with pytest.raises(ValueError, match="evolutions table"):
        rom_truth.evolutions_table(bytes(rom))


def test_parse_map_reads_dims_warps_connections_and_sprites(rom):
    _, data = rom
    m0 = parse_map(data, 0)
    assert (m0["width"], m0["height"]) == (4, 4)
    assert m0["warps"] == [[1, 3, LAST_MAP, 0], [2, 3, LAST_MAP, 0]]  # (x, y, dmap, dwarp)
    assert m0["signs"] == [[1, 1]]  # (x, y); text is read live, never extracted
    assert m0["connections"] == {}
    kinds = [(s["kind"], s["x"], s["y"]) for s in m0["sprites"]]
    assert kinds == [("npc", 1, 2), ("trainer", 0, 3), ("item", 0, -4)]
    # An item ball's extra byte is the item id it holds — the fact that turns "where is the
    # CARD KEY" into a lookup. Only item balls carry it.
    assert [s.get("item") for s in m0["sprites"]] == [None, None, 5]
    assert m0["grid"] == ["1111", "1111", "1111", "1111"]
    m1 = parse_map(data, 1)
    assert m1["connections"] == {"east": 2}
    assert m1["connection_offsets"] == {"east": 8}  # the far map's row is ours + 8
    assert parse_map(data, 2)["connection_offsets"] == {"west": -8}  # and back: signed
    assert m0["connection_offsets"] == {}
    assert m1["grid"] == ["1100", "1100", "1111", "1111"]  # block 1 (wall) top-right
    assert [0, 2] in m1["grass"] and [1, 3] in m1["grass"]


def test_tile_pair_collisions_block_moves_between_two_walkable_cells(rom):
    """The engine refuses some moves between cells that are BOTH walkable — pokered's
    TilePairCollisionsLand. On the real ROM this is what closes Mt. Moon B2F's row-11 -> row-12
    boundary (CAVERN 0x20/0x05, measured live at (25,11)->(25,12)); a per-cell grid cannot say
    it, so ``grid`` alone over-reports connectivity."""
    _, data = rom
    pairs = rom_truth.tile_pairs(data)
    assert (0, WALK, LIP) in pairs and (0, LIP, WALK) in pairs  # recorded both directions
    m2 = parse_map(data, 2)
    assert m2["grid"][0][1] == "1" and m2["grid"][0][2] == "1"  # both cells walkable...
    assert not rom_truth.passable(m2, pairs, 1, 0, 2, 0)  # ...but the move between them is not
    assert not rom_truth.passable(m2, pairs, 2, 0, 1, 0)  # refused from the other side too
    assert rom_truth.passable(m2, pairs, 0, 0, 1, 0)  # walk -> walk is fine
    assert rom_truth.passable(m2, pairs, 2, 0, 3, 0)  # lip -> lip is fine
    assert not rom_truth.passable(m2, pairs, 0, 0, -1, 0)  # off-map
    assert not rom_truth.passable(parse_map(data, 1), pairs, 1, 0, 2, 0)  # into a wall cell
    assert rom_truth.passable({**m2, "tiles": None}, pairs, 1, 0, 2, 0)  # no tiles: grid-only


def test_extract_carries_the_tile_pair_table(rom):
    truth = parse_rom(rom[0], map_ids=[2])
    assert [0, WALK, LIP] in truth["tile_pairs"]
    assert truth["maps"]["2"]["tiles"][0][:8] == f"{WALK:02x}{WALK:02x}{LIP:02x}{LIP:02x}"


def test_degenerate_map_is_skipped(rom):
    _, data = rom
    assert parse_map(data, 3) is None
    truth = parse_rom(rom[0], map_ids=[0, 1, 2, 3])
    assert set(truth["maps"]) == {"0", "1", "2"}


def test_route_uses_mats_edges_and_filters_absent_maps(rom):
    truth = parse_rom(rom[0], map_ids=[0, 1, 2, 3])
    chain = route(truth, 0, 2)
    assert [h["via"] for h in chain] == ["mat", "edge"]
    assert chain[0]["to"] == 1 and chain[1]["edge"] == "east"
    text = describe_route(chain)
    assert "door mat" in text and "east edge" in text
    warp_chain = route(truth, 1, 0)
    assert warp_chain == [{"from": 1, "to": 0, "via": "warp", "x": 0, "y": 0, "dest_warp": 0}]
    assert "warp (0,0)" in describe_route(warp_chain)
    assert route(truth, 0, 200) is None  # absent destination
    assert route(truth, 0, 0) == []  # already there


def test_route_unreachable_returns_none(rom):
    truth = parse_rom(rom[0], map_ids=[0, 1, 2, 3])
    del truth["maps"]["1"]  # sever the world: 0's only links ran through 1
    assert route(truth, 0, 2) is None


def test_seed_worldmap_stamps_grid_bounds_sprites_and_grass(rom):
    truth = parse_rom(rom[0], map_ids=[0, 1])
    wm = seed_worldmap(truth, [0, 1])
    assert wm.bounds[0] == (4, 4) and wm.bounds[1] == (4, 4)
    assert wm.cells[1][(2, 0)] == 0 and wm.cells[1][(0, 0)] == 1
    assert (1, 2) in wm.blocked[0] and (0, 3) in wm.blocked[0]  # npc + trainer hard-blocked
    assert (0, -4) not in wm.blocked.get(0, {})  # off-map sprite skipped
    assert wm.is_encounter_tile(1, 0, 2)


def test_load_truth_enforces_rom_sha(rom, tmp_path):
    p, data = rom
    truth_path = tmp_path / "truth.json"
    truth_path.write_text(json.dumps({"rom_sha256": hashlib.sha256(data).hexdigest(), "maps": {}}))
    assert load_truth(truth_path, rom_path=p)["maps"] == {}
    assert load_truth(truth_path, rom_path=tmp_path / "absent.gb")["maps"] == {}  # no ROM: no check
    truth_path.write_text(json.dumps({"rom_sha256": "0" * 64, "maps": {}}))
    with pytest.raises(ValueError, match="different ROM"):
        load_truth(truth_path, rom_path=p)


def test_cli_extract_route_and_seed(rom, tmp_path, capsys):
    p, _ = rom
    out = tmp_path / "truth.json"
    assert rom_truth.main(["extract", "--rom", str(p), "--out", str(out)]) == 0
    assert "maps ->" in capsys.readouterr().out
    assert rom_truth.main(["route", "0", "2", "--truth", str(out)]) == 0
    assert "east edge" in capsys.readouterr().out
    assert rom_truth.main(["route", "0", "200", "--truth", str(out)]) == 1
    assert "no route" in capsys.readouterr().out
    wm_path = tmp_path / "seed.worldmap"
    assert rom_truth.main(["seed-worldmap", "0", "1", "--out", str(wm_path), "--truth", str(out)]) == 0
    assert WorldMap.load(wm_path).bounds[0] == (4, 4)


# ---- exit targets / on-map pathing ---------------------------------------------------------


def test_exit_targets_warp_is_the_mat_and_edge_is_every_open_cell(rom):
    """An edge hop has no tile in any warp table — the engine hands the player over when they walk
    off that side — so its target is the whole open edge. Route 3 is the case that matters: its
    only way to Route 4 is the NORTH edge, which is why an east march could never leave the map."""
    p, data = rom
    truth = parse_rom(p)
    assert rom_truth.exit_targets(truth, {"from": 1, "to": 0, "via": "warp", "x": 0, "y": 0}) == {(0, 0)}
    assert rom_truth.exit_targets(truth, {"from": 1, "to": 2, "via": "mat", "x": 2, "y": 3}) == {(2, 3)}
    # Map 1's grid is 1100/1100/1111/1111 — the east column is open only on the bottom two rows.
    assert rom_truth.exit_targets(truth, {"from": 1, "to": 2, "via": "edge", "edge": "east"}) == {(3, 2), (3, 3)}
    assert rom_truth.exit_targets(truth, {"from": 1, "to": 2, "via": "edge", "edge": "north"}) == {(0, 0), (1, 0)}
    assert rom_truth.exit_targets(truth, {"from": 1, "to": 2, "via": "edge", "edge": "south"}) == {
        (0, 3),
        (1, 3),
        (2, 3),
        (3, 3),
    }
    assert rom_truth.exit_targets(truth, {"from": 1, "to": 2, "via": "edge", "edge": "west"}) == {
        (0, 0),
        (0, 1),
        (0, 2),
        (0, 3),
    }
    assert rom_truth.exit_targets(truth, {"from": 1, "to": 2, "via": "edge", "edge": "nowhere"}) == set()


def test_path_on_map_routes_to_the_nearest_target(rom):
    p, data = rom
    truth = parse_rom(p)
    pairs = rom_truth.loaded_pairs(truth)
    east = rom_truth.exit_targets(truth, {"from": 1, "to": 2, "via": "edge", "edge": "east"})
    path = rom_truth.path_on_map(truth, pairs, 1, (0, 0), east)
    assert path[0] == (0, 0) and path[-1] in east
    assert all(abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1 for a, b in zip(path, path[1:]))
    assert rom_truth.path_on_map(truth, pairs, 1, (3, 2), east) == [(3, 2)]  # already standing on it
    assert rom_truth.path_on_map(truth, pairs, 99, (0, 0), east) is None  # unknown map
    assert rom_truth.path_on_map(truth, pairs, 1, (0, 0), set()) is None  # nothing to aim at


def test_path_on_map_honours_blocked_tiles_and_tile_pairs(rom):
    """``blocked`` is what the grid cannot say: a body standing on an open tile, or a wall this
    lane has already met. Blocking one of two exits must divert to the other, not give up."""
    p, data = rom
    truth = parse_rom(p)
    pairs = rom_truth.loaded_pairs(truth)
    east = rom_truth.exit_targets(truth, {"from": 1, "to": 2, "via": "edge", "edge": "east"})
    assert rom_truth.path_on_map(truth, pairs, 1, (0, 0), east, blocked={(3, 2)})[-1] == (3, 3)
    assert rom_truth.path_on_map(truth, pairs, 1, (0, 0), east, blocked=east) is None  # every exit gone
    # A lane standing on a tile it has since learned is blocked must still route out of it.
    assert rom_truth.path_on_map(truth, pairs, 1, (0, 0), east, blocked={(0, 0)})[0] == (0, 0)
    # Map 2's lip block sits behind a tile-pair collision, so BFS must refuse that edge.
    m2 = truth["maps"]["2"]
    assert m2["grid"][0][2] == "1" and not rom_truth.passable(m2, pairs, 1, 0, 2, 0)


def test_sprite_tiles_reports_bodies_the_grid_calls_walkable(rom):
    """A defeated Gen 1 trainer keeps standing on its tile, so a route planned through one is
    blocked for the rest of the run, not just until the battle ends."""
    p, data = rom
    truth = parse_rom(p)
    assert {(1, 2), (0, 3)} <= rom_truth.sprite_tiles(truth, 0)
    assert rom_truth.sprite_tiles(truth, 1) == set()
    assert rom_truth.sprite_tiles(truth, 99) == set()


def test_loaded_pairs_reads_the_extracted_list(rom):
    p, data = rom
    truth = parse_rom(p)
    assert rom_truth.loaded_pairs(truth) == rom_truth.tile_pairs(data)
    assert rom_truth.loaded_pairs({"maps": {}}) == set()


# ---- ledges -------------------------------------------------------------------------------------


def test_ledge_hops_scans_the_table_by_structure(rom):
    _, data = rom
    hops = rom_truth.ledge_hops(data)
    assert len(hops) == 5
    assert ("down", WALK, LEDGE) in hops and ("left", WALK, 0x06) in hops and ("right", WALK, 0x07) in hops


def test_ledge_hops_raises_when_no_table_exists():
    with pytest.raises(ValueError):
        rom_truth.ledge_hops(bytes(0x8000))


def test_extract_carries_the_ledge_table(rom):
    path, _ = rom
    truth = parse_rom(path)
    assert ["down", WALK, LEDGE] in truth["ledges"]
    assert rom_truth.loaded_ledges({"ledges": truth["ledges"]}) == {tuple(t) for t in truth["ledges"]}


def _ledge_map():
    """A 1x5 column: open, open, LEDGE (solid in the grid), open, open — connected only by the hop."""
    return {
        "ledges": [["down", 0x2C, 0x37]],
        "maps": {
            "7": {
                "width": 1,
                "height": 5,
                "tileset": 0,
                "grid": ["1", "1", "0", "1", "1"],
                "tiles": ["2c", "2c", "37", "2c", "2c"],
            }
        },
    }


def test_path_on_map_crosses_a_ledge_downward_only(rom_truth_mod=rom_truth):
    truth = _ledge_map()
    path = rom_truth.path_on_map(truth, set(), 7, (0, 0), {(0, 4)})
    assert path == [(0, 0), (0, 1), (0, 3), (0, 4)]  # (0,1) -> (0,3) is the two-cell hop
    # One-way: from below, the ledge is a wall.
    assert rom_truth.path_on_map(truth, set(), 7, (0, 4), {(0, 0)}) is None


def test_ledge_hop_respects_blocked_and_tileset(rom_truth_mod=rom_truth):
    truth = _ledge_map()
    # A body on the ledge tile blocks the hop.
    assert rom_truth.path_on_map(truth, set(), 7, (0, 0), {(0, 4)}, blocked={(0, 2)}) is None
    # Ledges are an overworld-tileset behaviour: any other tileset never hops.
    truth["maps"]["7"]["tileset"] = 17
    assert rom_truth.path_on_map(truth, set(), 7, (0, 0), {(0, 4)}) is None


TRUTH_FILE = rom_truth.TRUTH_DEFAULT


@pytest.mark.skipif(not TRUTH_FILE.exists(), reason="no extracted references/rom_truth.json")
def test_route4_east_reaches_cerulean_over_ledges():
    """The first routed run's wall (benchmarks/2026-08-25-router-cerulean.md): a plain grid BFS
    reads Route 4's east road as disconnected from the cave exit; the ledge edges connect it."""
    truth = json.loads(TRUTH_FILE.read_text())
    m = truth["maps"]["15"]
    edge = {(m["width"] - 1, y) for y in range(m["height"]) if m["grid"][y][m["width"] - 1] == "1"}
    path = rom_truth.path_on_map(truth, rom_truth.loaded_pairs(truth), 15, (24, 5), edge)
    assert path is not None
    hops = [1 for a, b in zip(path, path[1:]) if abs(a[0] - b[0]) + abs(a[1] - b[1]) == 2]
    assert hops, "the east road is only connected over ledges"


def test_species_table_extracts_names_dex_types_and_catch_rate(rom):
    _, data = rom
    table = rom_truth.species_table(data)
    assert table["1"]["name"] == "Rhydon" and table["1"]["dex"] == 112
    assert table["1"]["types"] == ["normal"]  # the fixture's zeroed stats row decodes to normal
    assert table["2"]["name"] == "NidoranM"  # the male symbol decodes through _NAME_CHARS
    assert "3" not in table  # unnamed ids are MISSINGNO slots
    with pytest.raises(ValueError, match="species tables"):
        rom_truth.species_table(bytes(0x8000))


def test_wild_encounters_extracts_pools_by_structure(rom):
    _, data = rom
    wilds = rom_truth.wild_encounters(data, {1, 2})
    assert len(wilds) == 248  # every fixture map shares the one block
    assert wilds["51"]["grass_rate"] == 8
    assert wilds["51"]["grass"] == [[3, 1]] * 10
    assert wilds["51"]["water"] == []
    with pytest.raises(ValueError, match="wild encounter"):
        rom_truth.wild_encounters(bytes(0x8000), {1})


def test_extract_carries_the_wild_tables(rom):
    truth = parse_rom(rom[0], map_ids=[2])
    assert truth["wilds"]["51"]["grass_rate"] == 8


def test_wild_encounters_rejects_malformed_tables(rom):
    _, data = rom
    # Species filter: a table whose blocks name unknown species is not the table.
    with pytest.raises(ValueError):
        rom_truth.wild_encounters(data, {2})
    # An absurd rate disqualifies the block.
    bad = bytearray(data)
    bad[WILD_BLOCK] = 200
    with pytest.raises(ValueError):
        rom_truth.wild_encounters(bytes(bad), {1})
    # A block at the very last byte runs off the ROM on its water pass.
    edge = bytearray(0x8000)
    for i in range(248):
        edge[0x4600 + 2 * i : 0x4600 + 2 * i + 2] = bytes([0xFF, 0x7F])
    with pytest.raises(ValueError):
        rom_truth.wild_encounters(bytes(edge), {1})
    # A ROM shorter than its own pointer table.
    with pytest.raises(ValueError):
        rom_truth.wild_encounters(bytes(0x5000), {1})


def test_measured_gates_close_a_step_the_grid_calls_walkable(tmp_path):
    """The grid has no way to express a script gate, so a measured refusal has to override it —
    otherwise every region computed inside Silph over-reports and every route plans through a
    locked door."""
    grid = ["1111", "1111", "1111", "1111"]
    m = {"width": 4, "height": 4, "tileset": 0, "grid": grid, "warps": []}
    assert rom_truth.passable(m, set(), 1, 1, 0, 1) is True
    m["gates"] = {"1,1,left": "Darn! It needs a CARD KEY!"}
    assert rom_truth.passable(m, set(), 1, 1, 0, 1) is False
    assert rom_truth.passable(m, set(), 1, 1, 2, 1) is True  # only that one direction


def test_measured_gates_merge_and_accumulate(tmp_path):
    path = tmp_path / "measured_gates.json"
    rom_truth.merge_measured_gates({"208": {"18,8,left": "a"}}, path)
    rom_truth.merge_measured_gates({"208": {"18,9,left": "b"}, "209": {"5,13,up": "c"}}, path)
    merged = rom_truth.load_measured_gates(path)
    assert merged["208"] == {"18,8,left": "a", "18,9,left": "b"}
    assert merged["209"] == {"5,13,up": "c"}


def test_attaching_gates_reaches_the_map_dicts_passable_reads():
    truth = {"maps": {"208": {"width": 1, "height": 1, "grid": ["1"], "warps": []}}}
    rom_truth.attach_measured_gates(truth, rom_truth.MEASURED_GATES)
    assert truth["maps"]["208"].get("gates"), "the shared gate file should carry map 208"


def test_a_dead_warp_is_dropped_from_a_pocket_s_exits(tmp_path):
    """Silph 1F's (16,10) pad was measured dead early and then routed through by every planner
    since, because `measured_gates` records refused steps and a dead door is a refused warp."""
    grid = ["11", "11"]
    truth = {
        "maps": {
            "1": {"width": 2, "height": 2, "tileset": 0, "grid": grid, "warps": [[0, 0, 2, 0], [1, 0, 2, 0]]},
            "2": {"width": 2, "height": 2, "tileset": 0, "grid": grid, "warps": [[0, 0, 1, 0]]},
        }
    }
    assert len(rom_truth.pocket_exits(truth, 1, 0)) == 2
    truth["maps"]["1"]["dead_warps"] = {"0,0": "refused"}
    assert [e["from"] for e in rom_truth.pocket_exits(truth, 1, 0)] == [[1, 0]]


def test_dead_warps_merge_and_reach_the_truth():
    assert rom_truth.load_dead_warps()["181"]["16,10"]
    assert "16,10" in rom_truth.load_truth()["maps"]["181"].get("dead_warps", {})


def test_dead_warps_are_empty_when_nothing_has_been_measured(tmp_path):
    assert rom_truth.load_dead_warps(tmp_path / "absent.json") == {}


def test_dead_warps_merge_and_accumulate(tmp_path):
    path = tmp_path / "dead.json"
    rom_truth.merge_dead_warps({"181": {"16,10": "refused"}}, path)
    rom_truth.merge_dead_warps({"181": {"9,9": "also refused"}, "207": {"1,1": "x"}}, path)
    merged = rom_truth.load_dead_warps(path)
    assert merged["181"] == {"16,10": "refused", "9,9": "also refused"}
    assert merged["207"] == {"1,1": "x"}


def _two_room_truth(gates=None, dead=None):
    grid = ["1111", "1111", "1111", "1111"]

    def m(**kw):
        return {"width": 4, "height": 4, "tileset": 0, "grid": grid, "warps": [], "connections": {}, **kw}

    truth = {"maps": {"1": m(warps=[[0, 0, 2, 0], [3, 3, 2, 0]]), "2": m(warps=[[0, 0, 1, 0]])}}
    if gates:
        truth["maps"]["1"]["gates"] = gates
    if dead:
        truth["maps"]["1"]["dead_warps"] = dead
    return truth


def test_pockets_of_an_unknown_map_is_empty_not_an_error():
    assert rom_truth.pockets({"maps": {}}, 999) == []
    assert rom_truth.pocket_of({"maps": {}}, 999, (0, 0)) is None
    assert rom_truth.pocket_exits({"maps": {}}, 999, 0) == []


def test_pocket_exits_of_an_index_that_does_not_exist_is_empty():
    assert rom_truth.pocket_exits(_two_room_truth(), 1, 7) == []


def test_pocket_exits_resolve_the_landing_pocket():
    exits = rom_truth.pocket_exits(_two_room_truth(), 1, 0)
    assert {tuple(e["from"]) for e in exits} == {(0, 0), (3, 3)}
    assert all(e["to_map"] == 2 and e["to_pocket"] == 0 for e in exits)


def test_route_pockets_finds_a_chain_and_reports_none_when_there_is_not_one():
    truth = _two_room_truth()
    assert rom_truth.route_pockets(truth, (1, 0), (1, 0)) == []
    chain = rom_truth.route_pockets(truth, (1, 0), (2, 0))
    assert len(chain) == 1 and chain[0]["to_map"] == 2
    truth["maps"]["1"]["dead_warps"] = {"0,0": "x", "3,3": "x"}
    assert rom_truth.route_pockets(truth, (1, 0), (2, 0)) is None


def test_a_gate_splits_a_room_into_two_pockets():
    truth = _two_room_truth(gates={f"{x},1,down": "shut" for x in range(4)})
    sizes = sorted(len(p) for p in rom_truth.pockets(truth, 1))
    assert sizes == [8, 8]


def test_route_pockets_skips_an_exit_whose_landing_pocket_is_unknown():
    truth = _two_room_truth()
    truth["maps"]["1"]["warps"] = [[0, 0, 2, 9]]  # dest warp index past the end of map 2's table
    assert rom_truth.pocket_exits(truth, 1, 0)[0]["to_pocket"] is None
    assert rom_truth.route_pockets(truth, (1, 0), (2, 0)) is None


def test_route_pockets_returns_a_multi_hop_chain():
    grid = ["11", "11"]

    def m(**kw):
        return {"width": 2, "height": 2, "tileset": 0, "grid": grid, "warps": [], "connections": {}, **kw}

    truth = {
        "maps": {
            "1": m(warps=[[0, 0, 2, 0]]),
            "2": m(warps=[[0, 0, 1, 0], [1, 1, 3, 0]]),
            "3": m(warps=[[0, 0, 2, 1]]),
        }
    }
    chain = rom_truth.route_pockets(truth, (1, 0), (3, 0))
    assert [h["to_map"] for h in chain] == [2, 3]


def test_a_dead_warp_is_skipped_while_its_neighbours_are_kept():
    truth = _two_room_truth(dead={"0,0": "measured refused"})
    assert [tuple(e["from"]) for e in rom_truth.pocket_exits(truth, 1, 0)] == [(3, 3)]


def test_pocket_exits_skip_a_door_mat_and_a_warp_outside_the_pocket():
    """LAST_MAP mats are the return leg of the warp that entered, not a forward edge."""
    truth = _two_room_truth()
    truth["maps"]["1"]["warps"] = [[0, 0, rom_truth.LAST_MAP, 0], [1, 1, 999, 0], [3, 3, 2, 0]]
    exits = rom_truth.pocket_exits(truth, 1, 0)
    assert [tuple(e["from"]) for e in exits] == [(3, 3)]  # the mat and the unknown map both drop


def test_a_gate_is_a_door_only_when_the_sentence_is_a_lock():
    """The survey records every refusal it meets; only some of them are doors.

    Silph 5F's (9,16) was written down carrying "I heard a kid was wandering around." — a
    wandering NPC's small talk, kept as a permanent wall and applied from both sides ever after.
    It sat on the one tile between the 9F landing and the CARD KEY, so every route to the key was
    pruned before it was planned. Across the measured file, 106 of 130 entries were bodies.
    """
    assert rom_truth.is_door_text("Darn! It needs a CARD KEY!")
    assert rom_truth.is_door_text("The door is locked...")
    assert not rom_truth.is_door_text("I heard a kid was wandering around.")
    assert not rom_truth.is_door_text("AAAAAAA got 1400 for winning!")
    assert not rom_truth.is_door_text("")


def test_door_gates_keeps_silent_refusals_and_drops_chatter():
    """A silent refusal is terrain the grid failed to express — nothing spoke, so nothing was
    standing there. A refusal that came with a sentence about ROCKET BROTHERS is a sprite."""
    entries = {
        "8,4,left": "Darn! It needs a CARD KEY!",
        "9,16,right": "I heard a kid was wandering around.",
        "3,3,up": "",
    }
    assert rom_truth.door_gates(entries) == {"8,4,left": "Darn! It needs a CARD KEY!", "3,3,up": ""}


def test_attach_measured_gates_hangs_only_the_doors(tmp_path):
    path = tmp_path / "gates.json"
    path.write_text(
        json.dumps({"1": {"1,1,up": "Darn! It needs a CARD KEY!", "2,2,left": "Hey kid! What are you doing here?"}})
    )
    truth = {"maps": {"1": {"width": 4, "height": 4, "grid": ["1111"] * 4}}}
    rom_truth.attach_measured_gates(truth, path)
    assert truth["maps"]["1"]["gates"] == {"1,1,up": "Darn! It needs a CARD KEY!"}


def test_a_door_stops_being_a_wall_once_its_key_is_in_the_bag():
    """The door says what it wants, so the bag answers it. Without this the leg that took the
    CARD KEY on 5F planned its next hop as though it had not: `no-path` on 3F -> 7F, our own
    model refusing a route the world would have allowed."""
    entries = {
        "11,11,left": "Darn! It needs a CARD KEY!",
        "3,3,up": "The door is locked...",
    }
    assert rom_truth.gates_the_bag_opens(entries, set()) == entries
    assert rom_truth.gates_the_bag_opens(entries, {"CARD KEY"}) == {"3,3,up": "The door is locked..."}
    assert rom_truth.gates_the_bag_opens(entries, {"card key", "LIFT KEY"}) == {"3,3,up": "The door is locked..."}


def test_a_warp_outside_its_own_map_is_not_a_warp(rom):
    """Unused header slots parse into garbage that looks exactly like data. Map 231 claims tileset
    103 (every real map uses 0-23) and 110 of its 113 warps sit past its own edges, pointing at
    arbitrary map ids — and because `route` links a LAST_MAP interior to every map that warps
    *into* it, those phantoms made 231 a wormhole joined to most of the world. Routes to the
    Safari-side maps came back five hops from Saffron, through a map nothing can enter."""
    _, data = rom
    rom_bytes = bytearray(data)
    # Point map 0's second warp off the map: (x=9, y=9) on a 4x4 map.
    rom_bytes[OBJ0 + 6] = 9  # y
    rom_bytes[OBJ0 + 7] = 9  # x
    m0 = parse_map(bytes(rom_bytes), 0)
    assert m0["warps"] == [[1, 3, LAST_MAP, 0]]  # the in-bounds one survives; the phantom is gone


def test_a_header_with_a_tileset_past_the_table_is_not_a_map(rom):
    """Map 231 parses with tileset 103 while all 226 real maps use 0-23, 28x64 dimensions, and 113
    warps of which 110 sit outside its own edges. Nothing in the game can enter it, but `route`
    links a LAST_MAP interior to every map that warps *into* it, so those phantoms made it a
    wormhole joined to most of the world."""
    _, data = rom
    rom_bytes = bytearray(data)
    rom_bytes[HDR0] = rom_truth.MAX_TILESET + 1
    assert parse_map(bytes(rom_bytes), 0) is None


def test_item_names_are_read_from_the_list_that_opens_with_master_ball(rom):
    """The list is located by content signature, never by address — and TMs/HMs live past it as a
    numbered range, which is why 'HM03' is a label this code generates rather than ROM text."""
    _, data = rom
    items = rom_truth.item_names(data)
    assert items["1"] == "MASTER BALL"
    assert items["2"] == "ULTRA BALL" and items["3"] == "GREAT BALL"
    assert items[str(rom_truth.HM_FIRST)] == "HM01"
    assert items[str(rom_truth.HM_FIRST + 2)] == "HM03"  # the Surf HM, by generated name
    assert items[str(rom_truth.TM_BASE + 1)] == "TM01"
    assert rom_truth.item_names(bytes(0x100)) == {}  # no signature, no table


def test_machine_moves_says_what_each_tm_and_hm_teaches(rom):
    """An item's name does not say what it is: the cartridge stores machines as a numbered range
    with no text, so "HM03" is generated and nothing anywhere says SURF. The mapping is in the
    ROM — fifty TM move ids followed by the five HM ids — and it is found by content signature:
    the HM entries are exactly CUT, FLY, SURF, STRENGTH, FLASH."""
    import rom_truth as rt

    _, data = rom
    machines = rt.machine_moves(data)
    assert machines["HM01"] == "CUT" and machines["HM03"] == "SURF"
    assert machines["HM02"] == "FLY" and machines["HM04"] == "STRENGTH" and machines["HM05"] == "FLASH"
    assert len([k for k in machines if k.startswith("TM")]) == 50
    assert rt.machine_moves(bytes(0x100)) == {}  # no move list, no mapping


def test_move_names_come_from_the_list_that_opens_with_pound(rom):
    import rom_truth as rt

    _, data = rom
    moves = rt.move_names(data)
    assert moves["1"] == "POUND"
    assert moves["57"] == "SURF" and moves["15"] == "CUT"
    assert rt.move_names(bytes(0x100)) == {}


def test_machine_moves_refuses_an_image_it_cannot_verify(rom):
    """The table is found by signature or not at all: no move list, no field moves among the
    names, or no run of fifty valid ids before the HM marker each mean we do not know what a
    machine teaches — and saying nothing beats guessing."""
    import rom_truth as rt

    _, data = rom
    assert rt.machine_moves(bytes(0x200)) == {}  # no move list at all

    # A move list that has POUND but none of the field moves: the marker cannot be built.
    letters = bytes([0x80 + ord("P") - ord("A"), 0x50])
    blob = bytearray(0x400)
    pound = bytes([0x80 + ord(c) - ord("A") for c in "POUND"]) + bytes([0x50])
    blob[0x100 : 0x100 + len(pound)] = pound
    blob[0x100 + len(pound) : 0x100 + len(pound) + len(letters) * 160] = letters * 160
    assert rt.machine_moves(bytes(blob)) == {}

    # The marker present but with nothing usable before it, and no other candidate: report nothing.
    forged = bytearray(0x400)
    forged[0x100 : 0x100 + len(pound)] = pound
    off = 0x100 + len(pound)
    field = {15: "CUT", 19: "FLY", 57: "SURF", 70: "STRENGTH", 148: "FLASH"}
    for mid in range(2, 149):
        nm = field.get(mid, "M")
        enc = bytes([0x80 + ord(c) - ord("A") if c != " " else 0x7F for c in nm]) + bytes([0x50])
        forged[off : off + len(enc)] = enc
        off += len(enc)
    assert rt.machine_moves(bytes(forged)) == {}  # the HM ids never appear as a run


def test_machine_moves_keeps_searching_past_a_false_marker(rom):
    """The HM ids can appear as data before the real table does — this cartridge has three such
    runs and only one has fifty valid move ids in front of it. Take the one that holds up."""
    import rom_truth as rt

    _, data = rom
    decoy = bytes([0, 0, 0]) + bytes([15, 19, 57, 70, 148])
    forged = bytearray(0x200) + bytearray(decoy) + bytearray(data)
    machines = rt.machine_moves(bytes(forged))
    assert machines["HM03"] == "SURF"  # skipped the decoy, found the table


def test_a_battle_page_is_never_recorded_as_a_gate(tmp_path):
    """Twenty-one Silph/Saffron 'doors' were the award page 'got 500 for winning!'."""
    import rom_truth as rt

    p = tmp_path / "gates.json"
    merged = rt.merge_measured_gates(
        {"10": {"13,25,left": "AAAAAAA got 500 for winning!", "4,7,left": "Excuse me! Wait up please"}}, path=p
    )
    assert merged == {"10": {"4,7,left": "Excuse me! Wait up please"}}
    assert rt.is_battle_sentence("AAAAAAAAAA gained 438 EXP. Points!")
    assert rt.is_battle_sentence("AAAAAAAAAA's attack missed!")
    assert not rt.is_battle_sentence("This requires STRENGTH to move!")
    # a survey made only of battle pages leaves no trace at all
    assert rt.merge_measured_gates({"99": {"1,1,up": "AAAAAAA got 840 for winning!"}}, path=p) == merged


def test_move_table_comes_from_the_six_byte_table_that_opens_with_pound(rom):
    import rom_truth as rt

    _, data = rom
    assert rt.move_table(data) == {}  # the mini ROM carries names but no move-data table
    # plant the table: POUND, KARATE CHOP (the signature), then a third move to prove the walk
    table = bytes([1, 0, 40, 0, 255, 35, 2, 0, 50, 0, 255, 25, 3, 0, 15, 0, 216, 10])
    moves = rt.move_table(bytes(data) + table)
    assert moves["1"] == {"name": "POUND", "type": "normal", "power": 40, "accuracy": 100, "pp": 35}
    assert moves["3"]["power"] == 15 and moves["3"]["accuracy"] == 85 and moves["3"]["pp"] == 10
    assert len(moves) == 3  # the walk stops where the id sequence breaks
    assert rt.move_table(bytes(0x100)) == {}


@pytest.mark.skipif(not rom_truth.ROM_DEFAULT.exists(), reason="no cartridge on this checkout")
def test_move_table_on_the_cartridge_names_surf_and_hyper_beam():
    moves = rom_truth.move_table(rom_truth.ROM_DEFAULT.read_bytes())
    assert len(moves) == 165
    assert moves["57"] == {"name": "SURF", "type": "water", "power": 95, "accuracy": 100, "pp": 15}
    assert moves["63"]["name"] == "HYPER BEAM" and moves["63"]["type"] == "normal"
    assert moves["53"]["name"] == "FLAMETHROWER"  # the hand-typed table had put this name on 0x3F


def test_load_slopes_reads_the_measured_file_and_is_empty_without_it(tmp_path):
    import json as _json

    import rom_truth as rt

    assert rt.load_slopes(tmp_path / "none.json") == {}
    f = tmp_path / "slopes.json"
    f.write_text(_json.dumps({"28": {"down": "measured"}, "7": "left"}))
    assert rt.load_slopes(f) == {"28": "down", "7": "left"}
