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
    rom[HDR1 + 10 : HDR1 + 21] = bytes([2] + [0] * 10)  # east -> map 2
    rom[HDR1 + 21 : HDR1 + 23] = bytes(_u16(OBJ1))
    rom[DATA1 : DATA1 + 4] = bytes([0, 1, 2, 0])  # walk, wall, grass, walk
    rom[OBJ1 : OBJ1 + 2] = bytes([0, 1])
    rom[OBJ1 + 2 : OBJ1 + 6] = bytes([0, 0, 0, 0])  # (0,0) -> map 0
    rom[OBJ1 + 6] = 0  # signs
    rom[OBJ1 + 7] = 0  # sprites

    # Map 2 — outdoor: west connection to 1, plus a warp to an absent map (filtered from routing).
    rom[HDR2 : HDR2 + 10] = bytes([0, 2, 2, *_u16(DATA2), 0, 0, 0, 0, 0x02])  # west
    rom[HDR2 + 10 : HDR2 + 21] = bytes([1] + [0] * 10)
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
    assert m0["grid"] == ["1111", "1111", "1111", "1111"]
    m1 = parse_map(data, 1)
    assert m1["connections"] == {"east": 2}
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
