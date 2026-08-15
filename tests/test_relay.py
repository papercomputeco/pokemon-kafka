import json
from pathlib import Path

from relay import (
    BASE_GENOME,
    SEGMENTS,
    Baton,
    Segment,
    build_agent_cmd,
    pick_winner,
    prepare_variant_dir,
    promote_winner,
    segment_success,
)


def _baton(tmp_path, genome=None):
    state = tmp_path / "seed.state"
    state.write_bytes(b"x")
    return Baton(state_path=state, worldmap_path=None, genome=genome or {})


def test_segments_cover_the_road_to_mt_moon():
    names = [s.name for s in SEGMENTS]
    assert names == ["route1_to_forest", "forest_to_pewter", "pewter_to_badge", "badge_to_mtmoon"]
    assert SEGMENTS[0].stop_on_map == 51
    assert SEGMENTS[1].stop_on_map == 2
    assert SEGMENTS[2].stop_on_badge == 1
    assert SEGMENTS[3].stop_on_map == 59


def test_build_agent_cmd_emits_stop_flags_and_isolated_paths(tmp_path):
    seg = SEGMENTS[0]
    vdir = tmp_path / "v"
    cmd, env = build_agent_cmd("rom.gb", seg, seg.variants[0], vdir, _baton(tmp_path), tmp_path)
    joined = " ".join(cmd)
    assert "--stop-on-map 51" in joined
    assert f"--output-json {vdir / 'fitness.json'}" in joined
    assert f"--worldmap-file {vdir / 'world.map'}" in joined
    assert f"--stop-state {vdir / 'stop.state'}" in joined
    assert "--no-self-heal" in cmd and "--no-in-run-heal" in cmd
    assert "paper" not in cmd[0]


def test_build_agent_cmd_merges_genome_variant_over_baton_over_base(tmp_path):
    seg = Segment(
        "s", stop_on_map=2, stop_on_badge=None, max_turns=10, variants=({"label": "v", "hp_run_threshold": 0.5},)
    )
    baton = _baton(tmp_path, genome={"hp_run_threshold": 0.4, "door_cooldown": 9})
    _, env = build_agent_cmd("rom.gb", seg, seg.variants[0], tmp_path / "v", baton, tmp_path)
    genome = json.loads(env["EVOLVE_PARAMS"])
    assert genome["hp_run_threshold"] == 0.5  # variant beats baton
    assert genome["door_cooldown"] == 9  # baton beats base
    assert genome["stuck_threshold"] == BASE_GENOME["stuck_threshold"]
    assert "label" not in genome


def test_build_agent_cmd_formats_run_dir_in_extra_args(tmp_path):
    seg = SEGMENTS[2]  # pewter_to_badge carries the pre_brock capture hook
    cmd, _ = build_agent_cmd("rom.gb", seg, seg.variants[0], tmp_path / "v", _baton(tmp_path), tmp_path)
    assert f"54:{tmp_path}/batons/pre_brock.state" in " ".join(cmd)


def test_segment_success_by_map_and_badge():
    map_seg = Segment("m", stop_on_map=51, stop_on_badge=None, max_turns=1, variants=())
    badge_seg = Segment("b", stop_on_map=None, stop_on_badge=1, max_turns=1, variants=())
    assert segment_success({"final_map_id": 51}, map_seg)
    assert not segment_success({"final_map_id": 13}, map_seg)
    assert segment_success({"badges": 1}, badge_seg)
    assert not segment_success({"badges": 0}, badge_seg)
    assert not segment_success({}, map_seg)


def _result(label, success, lead_hp, turns):
    return {
        "label": label,
        "vdir": Path(label),
        "genome": {},
        "success": success,
        "fitness": {"lead_hp": lead_hp, "turns": turns},
    }


def test_pick_winner_prefers_healthiest_then_fastest():
    results = [
        _result("fast_but_hurt", True, lead_hp=2, turns=100),
        _result("healthy_slow", True, lead_hp=25, turns=900),
        _result("healthy_fast", True, lead_hp=25, turns=400),
        _result("failed", False, lead_hp=30, turns=50),
    ]
    assert pick_winner(results)["label"] == "healthy_fast"


def test_pick_winner_none_when_no_success():
    assert pick_winner([_result("a", False, 10, 10)]) is None


def test_prepare_variant_dir_copies_baton_worldmap(tmp_path):
    seed_map = tmp_path / "seed.worldmap"
    seed_map.write_bytes(b"geometry")
    baton = Baton(state_path=tmp_path / "s.state", worldmap_path=seed_map, genome={})
    vdir = prepare_variant_dir(tmp_path / "seg", {"label": "cautious"}, baton)
    assert vdir == tmp_path / "seg" / "cautious"
    assert (vdir / "world.map").read_bytes() == b"geometry"


def test_prepare_variant_dir_without_worldmap_starts_fresh(tmp_path):
    baton = Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    vdir = prepare_variant_dir(tmp_path / "seg", {"label": "base"}, baton)
    assert not (vdir / "world.map").exists()


def test_promote_winner_builds_next_baton(tmp_path):
    seg = SEGMENTS[0]
    vdir = tmp_path / "seg" / "wide_dc2"
    vdir.mkdir(parents=True)
    (vdir / "stop.state").write_bytes(b"state")
    (vdir / "world.map").write_bytes(b"map")
    winner = {
        "label": "wide_dc2",
        "vdir": vdir,
        "genome": {"door_cooldown": 2},
        "success": True,
        "fitness": {"lead_hp": 20, "turns": 300},
    }
    baton = promote_winner(tmp_path, seg, winner)
    assert baton.state_path.read_bytes() == b"state"
    assert baton.worldmap_path.read_bytes() == b"map"
    assert baton.genome == {"door_cooldown": 2}
    saved = json.loads((tmp_path / "batons" / "route1_to_forest.genome.json").read_text())
    assert saved == {"door_cooldown": 2}
