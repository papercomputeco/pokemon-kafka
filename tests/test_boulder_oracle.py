"""The boulder oracle's pure parts: candidates from a configuration, outcome classes, the catalog."""

import json

import boulder_oracle as bo


def _truth():
    # 5x3 cavern floor: all walkable, one boulder in the middle. Tileset 17 has no ledges.
    rows = ["11111", "11111", "11111"]
    return {"maps": {"7": {"width": 5, "height": 3, "tileset": 17, "grid": rows, "warps": [], "sprites": []}}}


def test_config_key_is_order_free():
    assert bo.config_key([(3, 1), (1, 1)]) == bo.config_key({(1, 1), (3, 1)}) == "1,1;3,1"


def test_candidates_are_the_stands_the_player_can_reach_with_boulders_solid():
    cands = bo.candidate_pushes(_truth(), set(), 7, (0, 0), {(2, 1)})
    stands = {(s, d) for s, d, _b in cands}
    assert stands == {((2, 2), "up"), ((2, 0), "down"), ((3, 1), "left"), ((1, 1), "right")}
    assert all(b == (2, 1) for _s, _d, b in cands)


def test_a_boulder_in_a_corridor_hides_the_stands_behind_it():
    t = _truth()
    t["maps"]["7"]["grid"] = ["00000", "11111", "00000"]  # one-row corridor
    cands = bo.candidate_pushes(t, set(), 7, (0, 1), {(2, 1)})
    assert [(s, d) for s, d, _b in cands] == [((1, 1), "right")]  # (3,1) is on the far side


def test_classify_reads_the_map_and_the_sprite_table_only():
    assert bo.classify(161, 162, {(1, 1)}, set()) == "player-fell"
    assert bo.classify(161, 161, {(1, 1), (2, 2)}, {(2, 2)}) == "fell"
    assert bo.classify(161, 161, {(1, 1)}, {(1, 2)}) == "moved"
    assert bo.classify(161, 161, {(1, 1)}, {(1, 1)}) == "refused"


def test_catalog_persists_every_record_and_resumes_untried_pushes(tmp_path):
    p = tmp_path / "cat.json"
    cat = bo.Catalog(p)
    key = bo.config_key({(2, 1)})
    cat.add(7, {"config": key, "stand": [2, 2], "dir": "up", "boulder": [2, 1], "outcome": "moved", "after": "2,0"})
    cands = bo.candidate_pushes(_truth(), set(), 7, (0, 0), {(2, 1)})
    left = cat.untried(7, key, cands)
    assert ((2, 2), "up") not in {(s, d) for s, d, _b in left} and len(left) == len(cands) - 1
    # a fresh Catalog on the same file knows the same push
    again = bo.Catalog(p)
    assert again.tried(7, key) == {((2, 2), "up")}
    assert json.loads(p.read_text())["7"]["pushes"][0]["outcome"] == "moved"


def test_catalog_states_and_summary(tmp_path):
    cat = bo.Catalog(tmp_path / "cat.json")
    cat.states(161)["1,1"] = "x.state"
    cat.add(161, {"config": "1,1", "stand": [1, 2], "dir": "up", "boulder": [1, 1], "outcome": "fell", "after": ""})
    cat.add(
        161, {"config": "1,1", "stand": [0, 1], "dir": "right", "boulder": [1, 1], "outcome": "refused", "after": "1,1"}
    )
    s = cat.summary(161)
    assert "2 pushes over 1 configurations" in s and "fell" in s and "refused" in s
    assert bo.Catalog(tmp_path / "cat.json").states(161) == {"1,1": "x.state"}


def test_show_prints_the_summary(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(bo, "CATALOG_PATH", tmp_path / "cat.json")
    assert bo.main(["show", "--map", "161"]) == 0
    assert "map 161: 0 pushes" in capsys.readouterr().out
