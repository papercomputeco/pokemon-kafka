import json

from relay import BASE_GENOME, SEGMENTS, Baton, Segment, build_agent_cmd


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
