"""The encounter catalog and roster optimizer: aggregation, legacy un-lying, and ranking.

The catalog's first real scan (3.67M battle rows, 84 streams) exposed two measurement lies the
tests below pin as legacy behavior: TYPE_ID_MAP had grass<->electric and psychic<->ice swapped,
and SPECIES_ID_MAP called Paras "Metapod" — hiding Mt. Moon's 6,515 wild grass-type sightings."""

import json

import encounters as en

OLD, NEW = "2026-08-20T00:00:00Z", "2026-08-27T00:00:00Z"


def _ev(event_type, data, at=NEW):
    return json.dumps({"event_type": event_type, "occurred_at": at, "data": data})


def _battle(species, level, map_id, hp, battle_type=1, at=NEW):
    return _ev(
        "battle",
        {"enemy_species": species, "enemy_level": level, "map_id": map_id, "enemy_hp": hp, "battle_type": battle_type},
        at,
    )


def _stream(tmp_path, name, lines):
    p = tmp_path / name
    p.write_text("\n".join(lines) + "\n")
    return str(p)


def test_scan_dedupes_battle_turns_into_encounters(tmp_path):
    lines = [
        _battle("Zubat", 8, 59, 22),
        _battle("Zubat", 8, 59, 15),  # same fight, hp falling
        _battle("Zubat", 8, 59, 22),  # hp back UP: a fresh Zubat
        _battle("Geodude", 9, 59, 30, battle_type=2),
        '{"event_type": "battle" not json at all',
        '{"event_type": "agent_state", "data": {}}',
    ]
    cat = en.scan([_stream(tmp_path, "a.jsonl", lines)])
    zubat = cat["maps"]["59"]["Zubat"]
    assert zubat["count"] == 2 and zubat["wild"] == 2
    assert cat["maps"]["59"]["Geodude"]["trainer"] == 1
    assert cat["maps"]["59"]["Zubat"]["min_level"] == 8


def test_scan_counts_encounter_events_and_types(tmp_path):
    lines = [
        _ev(
            "encounter",
            {
                "species": "Spearow",
                "level": 10,
                "map_id": 15,
                "battle_type": 1,
                "disposition": "caught",
                "enemy_type": "normal/flying",
            },
        ),
        _ev("battle_outcome", {"enemy_species": "Paras", "enemy_type": "bug/grass"}),
    ]
    cat = en.scan([_stream(tmp_path, "a.jsonl", lines)])
    assert cat["maps"]["15"]["Spearow"]["caught"] == 1
    assert cat["types"]["Spearow"] == ["flying", "normal"]
    assert cat["types"]["Paras"] == ["bug", "grass"]


def test_scan_unswaps_legacy_type_and_species_labels(tmp_path):
    lines = [
        # Pre-fix streams: Paras was decoded "Metapod", electric was labeled "grass".
        _battle("Metapod", 10, 59, 20, at=OLD),
        _ev("battle_outcome", {"enemy_species": "Pikachu", "enemy_type": "grass"}, at=OLD),
        # Post-fix streams pass through untouched.
        _ev("battle_outcome", {"enemy_species": "Oddish", "enemy_type": "grass"}, at=NEW),
    ]
    cat = en.scan([_stream(tmp_path, "a.jsonl", lines)])
    assert "Paras" in cat["maps"]["59"] and "Metapod" not in cat["maps"]["59"]
    assert cat["types"]["Pikachu"] == ["electric"]
    assert cat["types"]["Oddish"] == ["grass"]


def test_scan_decodes_raw_hex_ids_and_survives_missing_files(tmp_path):
    cat = en.scan([_stream(tmp_path, "a.jsonl", [_battle("#6D", 9, 60, 18)]), str(tmp_path / "gone.jsonl")])
    assert "Paras" in cat["maps"]["60"]
    assert en._decode_species("#zz") == "#zz"  # unparseable stays raw
    assert en._decode_species("Zubat") == "Zubat"


def test_report_renders_maps_and_filters(tmp_path):
    cat = en.scan([_stream(tmp_path, "a.jsonl", [_battle("Zubat", 8, 59, 22), _battle("Pidgey", 3, 12, 11)])])
    text = en.report(cat)
    assert "Mt. Moon 1F" in text and "Route 1" in text
    only = en.report(cat, only_map=59)
    assert "Zubat" in only and "Pidgey" not in only


def test_report_handles_levelless_rows():
    cat = {
        "maps": {"59": {"Zubat": {"count": 1, "wild": 1, "trainer": 0, "caught": 0, "min_level": 999, "max_level": 0}}},
        "types": {},
        "files": 1,
        "events": 1,
    }
    assert "L?" in en.report(cat)


def _catalog_for_recommend():
    return {
        "maps": {
            "59": {
                "Paras": {"count": 5, "wild": 5, "trainer": 0, "caught": 0, "min_level": 8, "max_level": 12},
                "Oddish": {"count": 2, "wild": 0, "trainer": 2, "caught": 0, "min_level": 11, "max_level": 11},
            },
            "51": {"Pikachu": {"count": 3, "wild": 3, "trainer": 0, "caught": 0, "min_level": 3, "max_level": 5}},
        },
        "types": {"Paras": ["bug"], "Pikachu": ["electric"], "Oddish": ["grass"]},
        "files": 1,
        "events": 10,
    }


def test_recommend_ranks_by_dual_type_truth(monkeypatch):
    monkeypatch.setattr(
        en,
        "_truth_species",
        lambda: {
            "Paras": {"types": ["bug", "grass"], "catch_rate": 190},
            "Pikachu": {"types": ["electric"], "catch_rate": 190},
        },
    )
    rows = en.recommend(_catalog_for_recommend(), "water")
    assert [r["species"] for r in rows] == ["Paras", "Pikachu"]  # Oddish excluded: trainer-only
    paras = rows[0]
    assert paras["score"] == 4.0 and paras["takes_from_water"] == 0.5 and paras["catch_rate"] == 190


def test_recommend_falls_back_to_observed_types_and_scores_immunity(monkeypatch):
    monkeypatch.setattr(en, "_truth_species", lambda: {"Pikachu": {"types": ["ghost"], "catch_rate": 45}})
    cat = _catalog_for_recommend()
    rows = en.recommend(cat, "normal")  # normal -> ghost is 0.0: immunity is the best wall
    pika = next(r for r in rows if r["species"] == "Pikachu")
    assert pika["takes_from_normal"] == 0.0 and pika["score"] == 4.0  # ghost also cannot HIT normal
    paras = next(r for r in rows if r["species"] == "Paras")
    assert paras["types"] == ["bug"]  # not in the truth stub: observed type1 fallback


def test_recommend_skips_species_with_no_type_information(monkeypatch):
    monkeypatch.setattr(en, "_truth_species", lambda: {})
    cat = _catalog_for_recommend()
    cat["types"] = {}
    assert en.recommend(cat, "water") == []


def test_truth_species_reads_the_extracted_table(monkeypatch):
    import rom_truth

    monkeypatch.setattr(
        rom_truth,
        "load_truth",
        lambda: {"species": {"109": {"name": "Paras", "dex": 46, "types": ["bug", "grass"], "catch_rate": 190}}},
    )
    assert en._truth_species() == {"Paras": {"types": ["bug", "grass"], "catch_rate": 190}}

    def gone():
        raise OSError("no truth file")

    monkeypatch.setattr(rom_truth, "load_truth", gone)
    assert en._truth_species() == {}


def test_cli_scan_report_recommend(tmp_path, monkeypatch, capsys):
    stream = _stream(tmp_path, "events.jsonl", [_battle("Paras", 9, 59, 20)])
    out = tmp_path / "catalog.json"
    assert en.main(["scan", stream, "--out", str(out)]) == 0
    assert "1 stream(s)" in capsys.readouterr().out
    assert en.main(["report", "--catalog", str(out)]) == 0
    assert "Paras" in capsys.readouterr().out
    monkeypatch.setattr(en, "_truth_species", lambda: {"Paras": {"types": ["bug", "grass"], "catch_rate": 190}})
    assert en.main(["recommend", "--vs", "water", "--catalog", str(out)]) == 0
    text = capsys.readouterr().out
    assert "Paras" in text and '--catch "Paras"' in text


def test_cli_scan_uses_default_globs_when_none_given(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(en, "WORKSPACE", tmp_path)  # empty workspace: zero streams, still valid
    out = tmp_path / "catalog.json"
    assert en.main(["scan", "--out", str(out)]) == 0
    assert "0 stream(s)" in capsys.readouterr().out


def test_cli_recommend_empty_catalog_prints_nothing(tmp_path, monkeypatch, capsys):
    out = tmp_path / "c.json"
    out.write_text(json.dumps({"maps": {}, "types": {}, "files": 0, "events": 0}))
    monkeypatch.setattr(en, "_truth_species", lambda: {})
    assert en.main(["recommend", "--vs", "water", "--catalog", str(out)]) == 0
    assert "--catch" not in capsys.readouterr().out
