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

WALK, WALL, GRASS = 0x00, 0x01, 0x52

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
    rom[COLL : COLL + 3] = bytes([WALK, GRASS, 0xFF])
    # Block 0: all walkable. Block 1: all wall. Block 2: bottom-left tiles grass.
    rom[BLOCKS : BLOCKS + 16] = bytes([WALK] * 16)
    rom[BLOCKS + 16 : BLOCKS + 32] = bytes([WALL] * 16)
    b2 = [WALK] * 16
    for idx in (4, 6, 12, 14):  # the bottom-left tile of each 2x2 quad
        b2[idx] = GRASS
    rom[BLOCKS + 32 : BLOCKS + 48] = bytes(b2)

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
    rom[DATA2 : DATA2 + 4] = bytes([0, 0, 0, 0])
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


def test_parse_map_reads_dims_warps_connections_and_sprites(rom):
    _, data = rom
    m0 = parse_map(data, 0)
    assert (m0["width"], m0["height"]) == (4, 4)
    assert m0["warps"] == [[1, 3, LAST_MAP, 0], [2, 3, LAST_MAP, 0]]  # (x, y, dmap, dwarp)
    assert m0["connections"] == {}
    kinds = [(s["kind"], s["x"], s["y"]) for s in m0["sprites"]]
    assert kinds == [("npc", 1, 2), ("trainer", 0, 3), ("item", 0, -4)]
    assert m0["grid"] == ["1111", "1111", "1111", "1111"]
    m1 = parse_map(data, 1)
    assert m1["connections"] == {"east": 2}
    assert m1["grid"] == ["1100", "1100", "1111", "1111"]  # block 1 (wall) top-right
    assert [0, 2] in m1["grass"] and [1, 3] in m1["grass"]


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
