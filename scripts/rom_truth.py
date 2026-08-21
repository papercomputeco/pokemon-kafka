"""ROM truth — world topology as lookup, not search.

Every wall class the benchmarks measured (docs/expedition-spec.md) traces to models re-deriving
facts by collision that sit deterministically in the ROM: warp tables ("gym sealed" — the door
mats warp to LAST_MAP), map connections ("Route 3 is a pocket" — its exit is the NORTH edge to
Route 4), and collision grids (the A* pilot's stale-grid wedges). This module parses those
structures straight out of ``rom/pokemon_red.gb`` (Gen 1, pret/pokered layout) and serves them
three ways:

    uv run python scripts/rom_truth.py extract                 # -> references/rom_truth.json
    uv run python scripts/rom_truth.py route 54 59             # map-level hop chain with tiles
    uv run python scripts/rom_truth.py seed-worldmap 2 14 15 --out seed.worldmap

``seed-worldmap`` writes a :class:`world_map.WorldMap` snapshot (grids + bounds) that
``relay.py --seed-worldmap`` already accepts — the pilot starts every listed map fully known,
with zero agent-code changes.

Validation discipline: the parser was checked against ground truth *measured live* by past runs —
Pewter City's seven warps (tests/test_agent_mtmoon.py CITY_WARPS), the gym's (4,13)/(5,13)
LAST_MAP mats, Route 3's empty warp table and 70x18 bounds, and 100 % cell agreement with the
learned ``badge1_gym_hp6.worldmap`` (465/465 cells on map 2). A wrong collision grid misroutes
silently, so ``extract`` records the ROM's sha256 and refuses a mismatched cached file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from world_map import WorldMap

ROM_DEFAULT = Path(__file__).resolve().parent.parent / "rom" / "pokemon_red.gb"
TRUTH_DEFAULT = Path(__file__).resolve().parent.parent / "references" / "rom_truth.json"

# Gen 1 Red (US) structure offsets, pret/pokered names. MapHeaderBanks/Pointers give each map's
# header; the header gives dims (in 2x2-tile blocks), the connections byte (N/S/W/E edge links),
# and the object data (warps, signs, sprites). The Tilesets table maps a header's tileset id to
# its blockset + the 0xFF-terminated list of walkable tile ids; a walk tile's passability is its
# 2x2 quad's bottom-left tile being in that list (the engine's own rule).
MAP_HEADER_POINTERS = 0x01AE  # bank 0: 2-byte pointer per map id
MAP_HEADER_BANKS = 0xC23D  # bank 3 (3:423D): 1 byte per map id
TILESETS = 0xC7BE  # bank 3 (3:47BE): 12-byte entries
NUM_MAPS = 248
LAST_MAP = 0xFF  # warp destination "back where we came from" (door mats)
_CONN_BITS = (("north", 0x08), ("south", 0x04), ("west", 0x02), ("east", 0x01))
# pokered's TilePairCollisionsLand: triples of (tileset, tile a, tile b) ending in 0xFF. Moving
# BETWEEN these two tiles is refused even though each is individually walkable — the cave-wall
# lips in the CAVERN tileset (17) and the forest edges in FOREST (3). This is an EDGE property:
# no per-cell walkable/solid grid can express it, so ``grid`` alone over-reports connectivity.
TILE_PAIR_COLLISIONS_LAND = 0x0C7E


def _u16(rom: bytes, off: int) -> int:
    return rom[off] | (rom[off + 1] << 8)


def _faddr(bank: int, addr: int) -> int:
    """GB banked address -> file offset (0x4000-0x7FFF window maps into ``bank``)."""
    return addr if addr < 0x4000 else bank * 0x4000 + (addr - 0x4000)


def _walkable_tiles(rom: bytes, coll_ptr: int) -> set[int]:
    tiles: set[int] = set()
    i = coll_ptr
    while rom[i] != 0xFF:
        tiles.add(rom[i])
        i += 1
    return tiles


def tile_pairs(rom: bytes) -> set[tuple[int, int, int]]:
    """``{(tileset, tile_a, tile_b)}`` the engine refuses to walk between, both directions."""
    pairs: set[tuple[int, int, int]] = set()
    i = TILE_PAIR_COLLISIONS_LAND
    while rom[i] != 0xFF:
        ts, a, b = rom[i], rom[i + 1], rom[i + 2]
        pairs.add((ts, a, b))
        pairs.add((ts, b, a))
        i += 3
    return pairs


def passable(m: dict, pairs: set[tuple[int, int, int]], x0: int, y0: int, x1: int, y1: int) -> bool:
    """Can the player step from (x0,y0) to (x1,y1) on map ``m``? Both cells must be walkable
    AND the move must not be a tile-pair collision. Checking ``grid`` alone is not enough: on
    Mt. Moon B2F (map 61) the engine refuses (25,11)->(25,12) although both cells are open,
    because the pair is CAVERN 0x20/0x05 — measured live, see
    docs/learnings/mtmoon-collision-rule-audit.md."""
    h, w = m["height"], m["width"]
    if not (0 <= x0 < w and 0 <= y0 < h and 0 <= x1 < w and 0 <= y1 < h):
        return False
    if m["grid"][y0][x0] != "1" or m["grid"][y1][x1] != "1":
        return False
    tiles = m.get("tiles")
    if not tiles:
        return True
    return (m["tileset"], int(tiles[y0][2 * x0 : 2 * x0 + 2], 16), int(tiles[y1][2 * x1 : 2 * x1 + 2], 16)) not in pairs


def parse_map(rom: bytes, map_id: int) -> dict | None:
    """One map's truth: dims (walk tiles), connections, warps as (x, y, dest_map, dest_warp),
    sprites (NPC/trainer positions), grass tile presence, and the walkable grid ('01' row
    strings, ``grid[y][x]``). ``None`` for an id whose header is degenerate (unused slots)."""
    bank = rom[MAP_HEADER_BANKS + map_id]
    off = _faddr(bank, _u16(rom, MAP_HEADER_POINTERS + 2 * map_id))
    tileset, h_blocks, w_blocks = rom[off], rom[off + 1], rom[off + 2]
    if not (0 < w_blocks <= 0x80 and 0 < h_blocks <= 0x80):
        return None
    data = _faddr(bank, _u16(rom, off + 3))
    conns: dict[str, int] = {}
    p = off + 10
    for name, bit in _CONN_BITS:
        if rom[off + 9] & bit:
            conns[name] = rom[p]
            p += 11
    obj = _faddr(bank, _u16(rom, p))
    warps = []
    q = obj + 2
    for _ in range(rom[obj + 1]):
        warps.append((rom[q + 1], rom[q], rom[q + 3], rom[q + 2]))  # stored y,x,dwarp,dmap
        q += 4
    q += 1 + 3 * rom[q]  # signs: count byte then (y, x, text id) each
    sprites = []
    n_sprites = rom[q]
    q += 1
    for _ in range(n_sprites):
        pic, y, x, _mv, _rng, text = rom[q], rom[q + 1] - 4, rom[q + 2] - 4, rom[q + 3], rom[q + 4], rom[q + 5]
        kind = "npc"
        q += 6
        if text & 0x40:  # trainer: +2 bytes (class/pokemon set, level/roster id)
            kind = "trainer"
            q += 2
        elif text & 0x80:  # item ball: +1 byte
            kind = "item"
            q += 1
        sprites.append({"kind": kind, "x": x, "y": y, "pic": pic})
    te = TILESETS + 12 * tileset
    tbank = rom[te]
    blocks = _faddr(tbank, _u16(rom, te + 1))
    walk = _walkable_tiles(rom, _u16(rom, te + 5))
    grass = rom[te + 10]
    w, h = 2 * w_blocks, 2 * h_blocks
    grid, grass_tiles, tiles = [], [], []
    for y in range(h):
        row, trow = [], []
        for x in range(w):
            block = rom[data + (y // 2) * w_blocks + (x // 2)]
            tile = rom[blocks + block * 16 + ((y % 2) * 2 + 1) * 4 + (x % 2) * 2]
            row.append("1" if tile in walk else "0")
            trow.append(f"{tile:02x}")  # kept so ``passable`` can apply tile-pair collisions
            if tile == grass and grass != 0xFF:
                grass_tiles.append([x, y])
        grid.append("".join(row))
        tiles.append("".join(trow))
    return {
        "width": w,
        "height": h,
        "tileset": tileset,
        "connections": conns,
        "warps": [list(wp) for wp in warps],
        "sprites": sprites,
        "grass": grass_tiles,
        "grid": grid,
        "tiles": tiles,
    }


def parse_rom(path: Path = ROM_DEFAULT, map_ids: list[int] | None = None) -> dict:
    rom = path.read_bytes()
    maps = {}
    for mid in map_ids if map_ids is not None else range(NUM_MAPS):
        m = parse_map(rom, mid)
        if m is not None:
            maps[str(mid)] = m
    return {
        "rom_sha256": hashlib.sha256(rom).hexdigest(),
        "tile_pairs": [list(t) for t in sorted(tile_pairs(rom))],
        "maps": maps,
    }


def load_truth(path: Path = TRUTH_DEFAULT, rom_path: Path | None = None) -> dict:
    """Load an extracted truth file; if the ROM is present, refuse a sha mismatch (a grid from a
    different image misroutes silently — the spec's number-one risk)."""
    truth = json.loads(path.read_text())
    if rom_path is not None and rom_path.exists():
        sha = hashlib.sha256(rom_path.read_bytes()).hexdigest()
        if sha != truth.get("rom_sha256"):
            raise ValueError(f"rom_truth.json was extracted from a different ROM (sha {truth.get('rom_sha256')[:12]}…)")
    return truth


def route(truth: dict, src: int, dst: int) -> list[dict] | None:
    """BFS over the map graph: warps (LAST_MAP mats are the return leg of the warp that entered,
    so only forward, non-LAST_MAP warps make edges) plus edge connections. Returns the hop list
    — each hop names the mechanism and the tile to use — or ``None`` if unreachable."""
    maps = truth["maps"]
    if str(src) not in maps or str(dst) not in maps:
        return None
    frontier, seen, parents = [src], {src}, {}
    while frontier:
        nxt = []
        for m in frontier:
            hops = []
            for x, y, dmap, dwarp in maps[str(m)]["warps"]:
                if dmap != LAST_MAP and str(dmap) in maps:
                    hops.append((dmap, {"from": m, "to": dmap, "via": "warp", "x": x, "y": y, "dest_warp": dwarp}))
            for edge, dmap in maps[str(m)]["connections"].items():
                if str(dmap) in maps:
                    hops.append((dmap, {"from": m, "to": dmap, "via": "edge", "edge": edge}))
            # A LAST_MAP mat is usable as "back out the way in": link to every map holding a warp
            # into this one (single-door interiors: the Center, the gym, gate rooms).
            if any(w[2] == LAST_MAP for w in maps[str(m)]["warps"]):
                for other, om in maps.items():
                    for x, y, dmap, dwarp in om["warps"]:
                        if dmap == m:
                            mat = maps[str(m)]["warps"][0]
                            hops.append(
                                (int(other), {"from": m, "to": int(other), "via": "mat", "x": mat[0], "y": mat[1]})
                            )
            for dmap, hop in hops:
                if dmap not in seen:
                    seen.add(dmap)
                    parents[dmap] = hop
                    nxt.append(dmap)
            if m == dst:
                nxt = []
                break
        if dst in seen:
            break
        frontier = nxt
    if dst not in seen and src != dst:
        return None
    chain: list[dict] = []
    cur = dst
    while cur != src:
        hop = parents[cur]
        chain.append(hop)
        cur = hop["from"]
    return list(reversed(chain))


def describe_route(chain: list[dict]) -> str:
    parts = []
    for hop in chain:
        if hop["via"] == "edge":
            parts.append(f"{hop['from']} --{hop['edge']} edge--> {hop['to']}")
        elif hop["via"] == "mat":
            parts.append(f"{hop['from']} --door mat ({hop['x']},{hop['y']})--> {hop['to']}")
        else:
            parts.append(f"{hop['from']} --warp ({hop['x']},{hop['y']})--> {hop['to']}")
    return "\n".join(parts)


def seed_worldmap(truth: dict, map_ids: list[int]) -> WorldMap:
    """A WorldMap with the listed maps fully known (grid + bounds), ready for
    ``relay.py --seed-worldmap``. Sprites are stamped as hard-blocked tiles — the collision grid
    says walkable, but an NPC stands there; the existing expiry machinery re-tests them."""
    wm = WorldMap()
    for mid in map_ids:
        m = truth["maps"][str(mid)]
        cells = wm.cells.setdefault(mid, {})
        for y, row in enumerate(m["grid"]):
            for x, ch in enumerate(row):
                cells[(x, y)] = 1 if ch == "1" else 0
        wm.bounds[mid] = (m["width"], m["height"])
        for s in m["sprites"]:
            if 0 <= s["x"] < m["width"] and 0 <= s["y"] < m["height"]:
                wm.block(mid, s["x"], s["y"])
        for gx, gy in m["grass"]:
            wm.mark_encounter(mid, gx, gy)
    return wm


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract", help="parse the ROM into references/rom_truth.json")
    ex.add_argument("--rom", type=Path, default=ROM_DEFAULT)
    ex.add_argument("--out", type=Path, default=TRUTH_DEFAULT)
    rt = sub.add_parser("route", help="map-level hop chain from A to B")
    rt.add_argument("src", type=int)
    rt.add_argument("dst", type=int)
    rt.add_argument("--truth", type=Path, default=TRUTH_DEFAULT)
    sw = sub.add_parser("seed-worldmap", help="write a WorldMap snapshot for relay.py --seed-worldmap")
    sw.add_argument("maps", type=int, nargs="+")
    sw.add_argument("--out", type=Path, required=True)
    sw.add_argument("--truth", type=Path, default=TRUTH_DEFAULT)
    args = ap.parse_args(argv)
    if args.cmd == "extract":
        truth = parse_rom(args.rom)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(truth))
        print(f"{len(truth['maps'])} maps -> {args.out} (rom sha {truth['rom_sha256'][:12]}…)")
        return 0
    truth = load_truth(args.truth)
    if args.cmd == "route":
        chain = route(truth, args.src, args.dst)
        if chain is None:
            print(f"no route {args.src} -> {args.dst}")
            return 1
        print(describe_route(chain))
        return 0
    wm = seed_worldmap(truth, args.maps)
    wm.save(args.out)
    print(f"seeded maps {args.maps} -> {args.out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
