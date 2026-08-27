#!/usr/bin/env python3
"""Encounter catalog + roster optimizer v0: what we've SEEN, where, and what to catch next.

Every run already streams ``battle`` events (species, level, map, per battle turn) and
``battle_outcome`` rows (with the enemy's OBSERVED type); new runs add the labeled ``encounter``
event (map AND tile, disposition). This tool aggregates all of it into a catalog and answers the
roster question from our own telemetry, never from a guide:

    uv run python scripts/encounters.py scan                       # all known streams -> data/encounters.json
    uv run python scripts/encounters.py report [--map 59]          # who lives where, at what levels
    uv run python scripts/encounters.py recommend --vs water       # ranked catch targets for a gym type

``recommend`` is the optimizer's seed: score = how hard the candidate's observed type hits the
target type (offense, references/type_chart.json) + how well it resists it (defense), over only
the species our runs have actually met. Its output is a ready ``--catch`` list for agent.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from glob import glob
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
CATALOG_DEFAULT = WORKSPACE / "data" / "encounters.json"
TYPE_CHART_PATH = WORKSPACE / "references" / "type_chart.json"

# Streams this box accumulates: curated demo runs, local telemetry, kept runs, and every
# persisted speedrun worktree ("worktrees persist for mining").
DEFAULT_GLOBS = (
    "demo-runs/*/events.jsonl",
    "data/telemetry/game/*.jsonl",
    "runs/*/events.jsonl",
    "../pokemon-kafka-speedrun-*/data/telemetry/game/*.jsonl",
)

# Streams written before this moment carry TYPE_ID_MAP's swapped labels (grass<->electric,
# psychic<->ice — fixed in memory_reader the same day the catalog exposed it). The raw bytes in
# RAM were always right; only the string labels lie, so legacy rows are un-swapped on read.
LEGACY_TYPE_FIX_AT = "2026-08-26T13:00:00Z"
LEGACY_TYPE_SWAP = {"grass": "electric", "electric": "grass", "psychic": "ice", "ice": "psychic"}
# Same vintage, same class of lie, in the species map: 0x6D was labeled "Metapod" (it is PARAS)
# and 0x6E "Kakuna" (it is POLIWHIRL). Old streams stored the decoded STRING, so the labels are
# corrected on read; 0x7C/0x71 appeared as raw "#7C"/"#71" back then and decode right today.
LEGACY_SPECIES_SWAP = {"Metapod": "Paras", "Kakuna": "Poliwhirl"}

MAP_NAMES = {
    0: "Pallet Town",
    1: "Viridian City",
    2: "Pewter City",
    3: "Cerulean City",
    12: "Route 1",
    13: "Route 2",
    14: "Route 3",
    15: "Route 4",
    33: "Route 22",
    35: "Route 24",
    36: "Route 25",
    51: "Viridian Forest",
    54: "Pewter Gym",
    59: "Mt. Moon 1F",
    60: "Mt. Moon B1F",
    61: "Mt. Moon B2F",
    65: "Cerulean Gym",
}


def _decode_species(name: str) -> str:
    """Old streams predate parts of SPECIES_ID_MAP and carry ``#NN`` hex ids; decode them with
    today's map so history is recovered, not discarded."""
    if name.startswith("#"):
        from memory_reader import SPECIES_ID_MAP

        try:
            return SPECIES_ID_MAP.get(int(name[1:], 16), name)
        except ValueError:
            return name
    return name


def scan(paths: list[str]) -> dict:
    """Aggregate every stream into the catalog.

    ``battle`` events fire once per battle TURN, so an encounter is counted when the enemy
    changes (species/level/map differs from the previous battle event in the same file, or the
    enemy's HP went UP — a fresh full bar is a new opponent). ``encounter`` events are counted
    directly. ``battle_outcome``/``move_result`` rows contribute observed types."""
    maps: dict = {}
    types: dict = {}
    files = 0
    lines = 0
    for path in paths:
        files += 1
        last = None  # (species, level, map_id, enemy_hp) of the previous battle event
        try:
            fh = open(path, encoding="utf-8", errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                if '"battle"' not in line and '"encounter"' not in line and '"enemy_type"' not in line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                lines += 1
                et, d = ev.get("event_type"), ev.get("data", {})
                if ev.get("occurred_at", "") < LEGACY_TYPE_FIX_AT:
                    if d.get("enemy_type"):
                        d["enemy_type"] = LEGACY_TYPE_SWAP.get(d["enemy_type"], d["enemy_type"])
                    for key in ("enemy_species", "species"):
                        if d.get(key) in LEGACY_SPECIES_SWAP:
                            d[key] = LEGACY_SPECIES_SWAP[d[key]]
                if et == "battle":
                    key = (d.get("enemy_species"), d.get("enemy_level"), d.get("map_id"))
                    hp = d.get("enemy_hp", 0)
                    fresh = last is None or key != last[:3] or hp > last[3]
                    last = (*key, hp)
                    if not fresh or key[0] is None:
                        continue
                    _count(maps, d.get("map_id"), _decode_species(key[0]), d.get("enemy_level"), d.get("battle_type"))
                elif et == "encounter":
                    _count(
                        maps,
                        d.get("map_id"),
                        _decode_species(d.get("species", "?")),
                        d.get("level"),
                        d.get("battle_type"),
                        caught=d.get("disposition") == "caught",
                    )
                    if d.get("enemy_type"):
                        s = types.setdefault(_decode_species(d.get("species", "?")), set())
                        s.update(d["enemy_type"].split("/"))
                elif et in ("battle_outcome", "move_result") and d.get("enemy_type"):
                    s = types.setdefault(_decode_species(d.get("enemy_species", "?")), set())
                    s.update(d["enemy_type"].split("/"))
    return {
        "maps": maps,
        "types": {k: sorted(v) for k, v in sorted(types.items())},
        "files": files,
        "events": lines,
    }


def _count(maps: dict, map_id, species: str, level, battle_type, caught: bool = False) -> None:
    m = maps.setdefault(str(map_id), {})
    row = m.setdefault(species, {"count": 0, "wild": 0, "trainer": 0, "caught": 0, "min_level": 999, "max_level": 0})
    row["count"] += 1
    row["wild" if battle_type == 1 else "trainer"] += 1
    row["caught"] += 1 if caught else 0
    if isinstance(level, int) and level > 0:
        row["min_level"] = min(row["min_level"], level)
        row["max_level"] = max(row["max_level"], level)


def report(catalog: dict, only_map: int | None = None) -> str:
    out = [f"{catalog['files']} stream(s), {catalog['events']} battle rows"]
    for map_id in sorted(catalog["maps"], key=lambda k: int(k) if k.isdigit() else 999):
        if only_map is not None and map_id != str(only_map):
            continue
        name = MAP_NAMES.get(int(map_id), f"map {map_id}") if map_id.isdigit() else f"map {map_id}"
        out.append(f"\n{name} ({map_id})")
        rows = sorted(catalog["maps"][map_id].items(), key=lambda kv: -kv[1]["wild"])
        for species, r in rows:
            lv = f"L{r['min_level']}-{r['max_level']}" if r["max_level"] else "L?"
            t = "/".join(catalog.get("types", {}).get(species, [])) or "?"
            out.append(
                f"  {species:12s} {t:16s} {lv:8s} wild {r['wild']:4d}  trainer {r['trainer']:4d}"
                + (f"  caught {r['caught']}" if r["caught"] else "")
            )
    return "\n".join(out)


def _truth_species() -> dict[str, dict]:
    """name -> {types, catch_rate} from references/rom_truth.json ({} for a pre-species file)."""
    import rom_truth as rt

    try:
        table = rt.load_truth().get("species", {})
    except OSError:
        return {}
    return {v["name"]: {"types": v["types"], "catch_rate": v["catch_rate"]} for v in table.values()}


def recommend(catalog: dict, vs: str) -> list[dict]:
    """Ranked catch targets against a defending type, over the species our runs have MET wild.

    Types and catch rates come from the ROM's own species table (the authority — observations
    only ever see type1, which undersold Paras's grass half); observed types are the fallback
    for a stale truth file. score = offense (best type vs the target) + defense (1 / the product
    of what the target type does to BOTH the candidate's types — dual types multiply). A species
    seen only in trainer battles is excluded: it cannot be caught there."""
    chart = json.loads(TYPE_CHART_PATH.read_text())
    chart.pop("_comment", None)
    authority = _truth_species()
    seen: dict[str, dict] = {}
    for map_id, rows in catalog["maps"].items():
        for species, r in rows.items():
            if r["wild"] == 0:
                continue
            s = seen.setdefault(species, {"maps": [], "min_level": 999, "max_level": 0, "wild": 0})
            s["maps"].append(map_id)
            s["wild"] += r["wild"]
            s["min_level"] = min(s["min_level"], r["min_level"])
            s["max_level"] = max(s["max_level"], r["max_level"])
    ranked = []
    for species, s in seen.items():
        truth_row = authority.get(species, {})
        stypes = [t.lower() for t in truth_row.get("types") or catalog.get("types", {}).get(species, [])]
        if not stypes:
            continue
        offense = max(chart.get(t, {}).get(vs, 1.0) for t in stypes)
        incoming = 1.0
        for t in stypes:
            incoming *= chart.get(vs, {}).get(t, 1.0)
        defense = 1.0 / incoming if incoming else 4.0  # immunity is the best wall there is
        ranked.append(
            {
                "species": species,
                "types": stypes,
                "score": offense + defense,
                "offense_vs_" + vs: offense,
                "takes_from_" + vs: incoming,
                "catch_rate": truth_row.get("catch_rate"),
                "maps": sorted(set(s["maps"])),
                "levels": f"{s['min_level']}-{s['max_level']}",
                "wild_seen": s["wild"],
            }
        )
    return sorted(ranked, key=lambda r: (-r["score"], -r["wild_seen"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("scan")
    sc.add_argument("globs", nargs="*", default=[])
    sc.add_argument("--out", type=Path, default=CATALOG_DEFAULT)
    rp = sub.add_parser("report")
    rp.add_argument("--map", type=int, default=None)
    rp.add_argument("--catalog", type=Path, default=CATALOG_DEFAULT)
    rc = sub.add_parser("recommend")
    rc.add_argument("--vs", required=True, help="defending type, e.g. water for Misty")
    rc.add_argument("--top", type=int, default=8)
    rc.add_argument("--catalog", type=Path, default=CATALOG_DEFAULT)
    args = ap.parse_args(argv)
    if args.cmd == "scan":
        patterns = args.globs or [str(WORKSPACE / g) for g in DEFAULT_GLOBS]
        paths = sorted(p for pat in patterns for p in glob(pat))
        catalog = scan(paths)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(catalog, indent=1))
        print(f"{len(paths)} stream(s) -> {args.out}: {sum(len(v) for v in catalog['maps'].values())} species rows")
        return 0
    catalog = json.loads(args.catalog.read_text())
    if args.cmd == "report":
        print(report(catalog, args.map))
        return 0
    rows = recommend(catalog, args.vs.lower())[: args.top]
    for r in rows:
        where = ", ".join(MAP_NAMES.get(int(m), m) if str(m).isdigit() else str(m) for m in r["maps"])
        print(
            f"{r['species']:12s} {'/'.join(r['types']):16s} score {r['score']:.1f} "
            f"(hits x{r['offense_vs_' + args.vs.lower()]}, takes x{r['takes_from_' + args.vs.lower()]}) "
            f"L{r['levels']}, seen wild x{r['wild_seen']} in: {where}"
        )
    if rows:
        print(f'\n--catch "{",".join(r["species"] for r in rows[:4])}"')
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
