import json
from pathlib import Path

import relay
from relay import (
    BASE_GENOME,
    SEGMENTS,
    Baton,
    Segment,
    _kill_lane,
    _select_segments,
    build_agent_cmd,
    main,
    pick_winner,
    prepare_variant_dir,
    promote_winner,
    run_segment,
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
    # The end-of-run healer writes the *shared* notes.md, so it stays off; the in-run heal is on
    # but pointed at the lane's own genome file, so parallel lanes cannot overwrite each other.
    assert "--no-self-heal" in cmd and "--no-in-run-heal" not in cmd
    assert f"--in-run-heal-notes {vdir / 'genome.md'}" in joined
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


class FakeProc:
    """Completes after N polls; writes its fitness.json at completion like agent.py does."""

    def __init__(self, vdir, fitness=None, polls_until_done=1):
        self.vdir, self.fitness = vdir, fitness
        self.polls_left = polls_until_done
        self.returncode = None
        self.killed = False

    def poll(self):
        if self.killed:
            self.returncode = -9
            return self.returncode
        if self.polls_left > 0:
            self.polls_left -= 1
            return None
        if self.fitness is not None:
            (self.vdir / "fitness.json").write_text(json.dumps(self.fitness))
        self.returncode = 0
        return self.returncode

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return self.returncode


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def _tiny_seg(variants):
    return Segment("seg", stop_on_map=51, stop_on_badge=None, max_turns=10, variants=variants)


def _fake_popen_factory(procs):
    """Hands out FakeProcs in launch order, asserting the harness shape."""
    queue = list(procs)

    def fake_popen(cmd, env=None, cwd=None, stdout=None, stderr=None, start_new_session=False):
        assert "--no-self-heal" in cmd
        return queue.pop(0)

    return fake_popen


def test_run_segment_picks_winner_and_kills_straggler(tmp_path):
    seg = _tiny_seg(({"label": "a"}, {"label": "b"}))
    baton = Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    seg_dir = tmp_path / "seg"
    va, vb = seg_dir / "a", seg_dir / "b"
    va.mkdir(parents=True), vb.mkdir(parents=True)
    (va / "stop.state").write_bytes(b"x")
    clock = FakeClock()
    procs = [
        FakeProc(va, fitness={"final_map_id": 51, "lead_hp": 20, "turns": 100}, polls_until_done=1),
        FakeProc(vb, polls_until_done=10**6),  # never finishes on its own
    ]
    winner, results = run_segment(
        "rom.gb",
        seg,
        baton,
        seg_dir,
        tmp_path,
        popen=_fake_popen_factory(procs),
        sleep=clock.sleep,
        clock=clock,
        grace=10.0,
    )
    assert winner["label"] == "a"
    assert procs[1].killed
    by_label = {r["label"]: r for r in results}
    assert by_label["b"].get("killed") is True


def test_run_segment_launches_lanes_in_their_own_process_group(tmp_path):
    """uv run spawns python as a child; without start_new_session=True a kill orphans it (see _kill_lane)."""
    seg = _tiny_seg(({"label": "a"},))
    baton = Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    seg_dir = tmp_path / "seg"
    (seg_dir / "a").mkdir(parents=True)
    clock = FakeClock()
    procs = [FakeProc(seg_dir / "a", fitness={"final_map_id": 51, "lead_hp": 20, "turns": 100})]
    (seg_dir / "a" / "stop.state").write_bytes(b"x")
    queue = list(procs)
    captured_kwargs = []

    def capturing_popen(cmd, env=None, cwd=None, stdout=None, stderr=None, start_new_session=False):
        captured_kwargs.append(start_new_session)
        return queue.pop(0)

    run_segment(
        "rom.gb",
        seg,
        baton,
        seg_dir,
        tmp_path,
        popen=capturing_popen,
        sleep=clock.sleep,
        clock=clock,
    )
    assert captured_kwargs == [True]


def test_run_segment_success_requires_stop_state_file(tmp_path):
    """Fitness can claim success even when the winning lane never wrote its baton file."""
    seg = _tiny_seg(({"label": "a"},))
    baton = Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    seg_dir = tmp_path / "seg"
    (seg_dir / "a").mkdir(parents=True)
    # Deliberately no stop.state written for this lane.
    clock = FakeClock()
    procs = [FakeProc(seg_dir / "a", fitness={"final_map_id": 51, "lead_hp": 20, "turns": 100})]
    winner, results = run_segment(
        "rom.gb",
        seg,
        baton,
        seg_dir,
        tmp_path,
        popen=_fake_popen_factory(procs),
        sleep=clock.sleep,
        clock=clock,
    )
    assert winner is None
    assert results[0]["success"] is False


def test_run_segment_returns_none_when_all_lanes_fail(tmp_path):
    seg = _tiny_seg(({"label": "a"},))
    baton = Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    seg_dir = tmp_path / "seg"
    (seg_dir / "a").mkdir(parents=True)
    clock = FakeClock()
    procs = [FakeProc(seg_dir / "a", fitness={"final_map_id": 13, "lead_hp": 5, "turns": 10})]
    winner, results = run_segment(
        "rom.gb",
        seg,
        baton,
        seg_dir,
        tmp_path,
        popen=_fake_popen_factory(procs),
        sleep=clock.sleep,
        clock=clock,
    )
    assert winner is None
    assert results[0]["success"] is False


def test_run_segment_timeout_kills_everything(tmp_path):
    seg = _tiny_seg(({"label": "a"},))
    baton = Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    (tmp_path / "seg" / "a").mkdir(parents=True)
    clock = FakeClock()
    procs = [FakeProc(tmp_path / "seg" / "a", polls_until_done=10**6)]
    winner, results = run_segment(
        "rom.gb",
        seg,
        baton,
        tmp_path / "seg",
        tmp_path,
        popen=_fake_popen_factory(procs),
        sleep=clock.sleep,
        clock=clock,
        timeout=20.0,
    )
    assert winner is None
    assert procs[0].killed


def test_main_dry_run_prints_commands_without_launching(tmp_path, capsys):
    rc = main(["rom.gb", "--dry-run", "--run-dir", str(tmp_path / "r"), "--segments", "route1_to_forest"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "--stop-on-map 51" in out
    assert "EVOLVE_PARAMS" in out
    assert not (tmp_path / "r").exists()  # dry-run touches nothing


def test_main_dry_run_applies_max_turns_scale(tmp_path, capsys):
    rc = main(
        [
            "rom.gb",
            "--dry-run",
            "--max-turns-scale",
            "0.5",
            "--run-dir",
            str(tmp_path / "r"),
            "--segments",
            "route1_to_forest",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "--max-turns 2000" in out  # route1_to_forest is 4000 * 0.5
    assert not (tmp_path / "r").exists()  # dry-run touches nothing


def test_main_rejects_unknown_segment(tmp_path, capsys):
    rc = main(["rom.gb", "--dry-run", "--run-dir", str(tmp_path / "r"), "--segments", "nope"])
    assert rc == 1
    assert "unknown segment" in capsys.readouterr().out.lower()


def test_select_segments_empty_spec_returns_full_list():
    assert _select_segments("") == list(SEGMENTS)


class WaitRaisesProc:
    """No pid attribute (like the test doubles) and wait() raises after being reaped elsewhere."""

    def __init__(self):
        self.killed = False

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        raise RuntimeError("already reaped")


def test_kill_lane_swallows_wait_errors():
    proc = WaitRaisesProc()
    _kill_lane(proc)  # must not raise
    assert proc.killed


def test_main_runs_segment_end_to_end_success(tmp_path, monkeypatch):
    rom = tmp_path / "rom.gb"
    rom.write_bytes(b"rom")
    seed = tmp_path / "seed.state"
    seed.write_bytes(b"seed")
    run_dir = tmp_path / "run"

    def fake_run_segment(rom_arg, seg, baton, seg_dir, run_dir_arg, parallel=6, timeout=1200.0, grace=90.0, **_kw):
        vdir = seg_dir / "winner"
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "stop.state").write_bytes(b"state-bytes")
        (vdir / "world.map").write_bytes(b"map-bytes")
        winner = {
            "label": "winner",
            "vdir": vdir,
            "genome": {"door_cooldown": 5},
            "success": True,
            "fitness": {"lead_hp": 20, "turns": 300, "final_map_id": 51},
        }
        results = [{"label": "winner", "success": True, "killed": False, "fitness": winner["fitness"]}]
        return winner, results

    monkeypatch.setattr(relay, "run_segment", fake_run_segment)
    rc = main([str(rom), "--run-dir", str(run_dir), "--segments", "route1_to_forest", "--seed-state", str(seed)])
    assert rc == 0
    assert (run_dir / "report.json").exists()
    report = json.loads((run_dir / "report.json").read_text())
    assert report["segments"][0]["winner"] == "winner"
    assert (run_dir / "batons" / "route1_to_forest.state").read_bytes() == b"state-bytes"
    assert (run_dir / "batons" / "route1_to_forest.worldmap").read_bytes() == b"map-bytes"


def test_main_retries_and_reports_failure_after_two_attempts(tmp_path, monkeypatch):
    rom = tmp_path / "rom.gb"
    rom.write_bytes(b"rom")
    seed = tmp_path / "seed.state"
    seed.write_bytes(b"seed")
    run_dir = tmp_path / "run"
    calls = []

    def fake_run_segment_fail(rom_arg, seg, baton, seg_dir, run_dir_arg, parallel=6, timeout=1200.0, grace=90.0, **_kw):
        calls.append((seg, seg_dir))
        return None, [{"label": "a", "success": False, "killed": False, "fitness": {}}]

    monkeypatch.setattr(relay, "run_segment", fake_run_segment_fail)
    rc = main([str(rom), "--run-dir", str(run_dir), "--segments", "route1_to_forest", "--seed-state", str(seed)])
    assert rc == 1
    assert (run_dir / "report.json").exists()
    report = json.loads((run_dir / "report.json").read_text())
    assert report["segments"][0]["winner"] is None
    assert len(calls) == 2
    first_seg, first_dir = calls[0]
    second_seg, second_dir = calls[1]
    assert second_seg.max_turns == first_seg.max_turns * 2
    assert second_dir.name == "route1_to_forest_retry"


def test_main_missing_rom_returns_1(tmp_path, capsys):
    seed = tmp_path / "seed.state"
    seed.write_bytes(b"seed")
    rc = main(
        [
            str(tmp_path / "nope.gb"),
            "--run-dir",
            str(tmp_path / "run"),
            "--segments",
            "route1_to_forest",
            "--seed-state",
            str(seed),
        ]
    )
    assert rc == 1
    assert "ROM not found" in capsys.readouterr().out


def test_main_missing_seed_state_returns_1(tmp_path, capsys):
    rom = tmp_path / "rom.gb"
    rom.write_bytes(b"rom")
    rc = main(
        [
            str(rom),
            "--run-dir",
            str(tmp_path / "run"),
            "--segments",
            "route1_to_forest",
            "--seed-state",
            str(tmp_path / "nope.state"),
        ]
    )
    assert rc == 1
    assert "seed state not found" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Memory write-back: a segment win must land in the agent's own memory
# ---------------------------------------------------------------------------


def _winner(genome, lead_hp=13, turns=2270):
    return {
        "label": "very_cautious",
        "genome": genome,
        "success": True,
        "fitness": {"lead_hp": lead_hp, "turns": turns, "final_map_id": 2},
    }


def test_record_win_appends_observation_line(tmp_path):
    memory_dir = tmp_path / "memory"
    seg = relay.SEGMENTS[1]  # forest_to_pewter
    genome = dict(relay.BASE_GENOME, hp_run_threshold=0.5, hp_heal_threshold=0.5)
    relay.record_win(seg, _winner(genome), memory_dir=memory_dir, notes_path=None, run_dir=tmp_path / "run")
    text = (memory_dir / "observations.md").read_text()
    assert "[important] relay forest_to_pewter cleared by very_cautious" in text
    assert "hp_run_threshold=0.5" in text and "hp_heal_threshold=0.5" in text
    assert "lead_hp=13" in text and "turns=2270" in text
    assert "(session: relay)" in text
    # notes.md is opt-in: nothing written when notes_path is None
    assert not (tmp_path / "notes.md").exists()


def test_record_win_reports_only_the_genome_diff(tmp_path):
    memory_dir = tmp_path / "memory"
    seg = relay.SEGMENTS[0]
    relay.record_win(seg, _winner(dict(relay.BASE_GENOME)), memory_dir=memory_dir, notes_path=None, run_dir=tmp_path)
    text = (memory_dir / "observations.md").read_text()
    assert "genome=base" in text  # no diff from BASE_GENOME


def test_record_win_promotes_genome_into_notes_when_asked(tmp_path):
    from autotune_bridge import load_genome_from_notes

    notes = tmp_path / "notes.md"
    notes.write_text("# Agent Notes\n")
    seg = relay.SEGMENTS[1]
    genome = dict(relay.BASE_GENOME, hp_run_threshold=0.5)
    relay.record_win(seg, _winner(genome), memory_dir=tmp_path / "memory", notes_path=notes, run_dir=tmp_path)
    loaded = load_genome_from_notes(notes)
    assert loaded["hp_run_threshold"] == 0.5
    body = notes.read_text()
    assert "relay forest_to_pewter" in body and "very_cautious" in body


def test_record_win_never_raises_on_unwritable_memory(tmp_path, monkeypatch):
    seg = relay.SEGMENTS[0]

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr(relay, "append_observations", boom)
    # Must not propagate: memory write-back is best-effort and must never fail the relay.
    relay.record_win(
        seg, _winner(dict(relay.BASE_GENOME)), memory_dir=tmp_path / "m", notes_path=None, run_dir=tmp_path
    )


def test_main_writes_memory_on_win_and_promotes_with_flag(tmp_path, monkeypatch):
    rom = tmp_path / "rom.gb"
    rom.write_bytes(b"rom")
    seed = tmp_path / "seed.state"
    seed.write_bytes(b"seed")
    run_dir = tmp_path / "run"
    memory_dir = tmp_path / "memory"
    notes = tmp_path / "notes.md"

    def fake_run_segment(rom_arg, seg, baton, seg_dir, run_dir_arg, parallel=6, timeout=1200.0, grace=90.0, **_kw):
        vdir = seg_dir / "winner"
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "stop.state").write_bytes(b"state-bytes")
        winner = {
            "label": "winner",
            "vdir": vdir,
            "genome": dict(relay.BASE_GENOME, door_cooldown=9),
            "success": True,
            "fitness": {"lead_hp": 20, "turns": 300, "final_map_id": 51},
        }
        return winner, [{"label": "winner", "success": True, "killed": False, "fitness": winner["fitness"]}]

    monkeypatch.setattr(relay, "run_segment", fake_run_segment)
    argv = [
        str(rom),
        "--run-dir",
        str(run_dir),
        "--segments",
        "route1_to_forest",
        "--seed-state",
        str(seed),
        "--memory-dir",
        str(memory_dir),
        "--notes",
        str(notes),
    ]
    assert main(argv) == 0
    assert "relay route1_to_forest cleared by winner" in (memory_dir / "observations.md").read_text()
    assert not notes.exists()  # no --promote-genome
    assert main(argv + ["--promote-genome"]) == 0
    from autotune_bridge import load_genome_from_notes

    assert load_genome_from_notes(notes)["door_cooldown"] == 9


def test_main_no_memory_disables_writeback(tmp_path, monkeypatch):
    rom = tmp_path / "rom.gb"
    rom.write_bytes(b"rom")
    seed = tmp_path / "seed.state"
    seed.write_bytes(b"seed")
    memory_dir = tmp_path / "memory"

    def fake_run_segment(rom_arg, seg, baton, seg_dir, run_dir_arg, **_kw):
        vdir = seg_dir / "w"
        vdir.mkdir(parents=True, exist_ok=True)
        (vdir / "stop.state").write_bytes(b"s")
        w = {"label": "w", "vdir": vdir, "genome": {}, "success": True, "fitness": {"lead_hp": 1, "turns": 1}}
        return w, [{"label": "w", "success": True, "killed": False, "fitness": w["fitness"]}]

    monkeypatch.setattr(relay, "run_segment", fake_run_segment)
    rc = main(
        [
            str(rom),
            "--run-dir",
            str(tmp_path / "run"),
            "--segments",
            "route1_to_forest",
            "--seed-state",
            str(seed),
            "--memory-dir",
            str(memory_dir),
            "--no-memory",
        ]
    )
    assert rc == 0
    assert not memory_dir.exists()


def test_record_win_never_raises_on_unwritable_notes(tmp_path, monkeypatch, capsys):
    seg = relay.SEGMENTS[0]

    def boom(*_a, **_k):
        raise OSError("read-only notes")

    monkeypatch.setattr(relay, "append_genome", boom)
    relay.record_win(
        seg, _winner(dict(relay.BASE_GENOME)), memory_dir=tmp_path / "m", notes_path=tmp_path / "n.md", run_dir=tmp_path
    )
    assert "notes promotion skipped" in capsys.readouterr().out


def test_run_segment_seeds_each_lane_its_own_genome_file(tmp_path):
    """Each lane's in-run heal must race from *that lane's* knobs, not the repo's or a sibling's.

    `healer.py`'s baseline is DEFAULT_PARAMS + the notes file it is pointed at, and it appends its
    winner back to the same file. Six lanes sharing the repo's notes.md would therefore heal from
    each other's genome; each lane gets `genome.md` in its own variant dir instead, pre-seeded with
    its own merged genome (BASE_GENOME < baton < variant).
    """
    seg = _tiny_seg(({"label": "a", "hp_run_threshold": 0.2}, {"label": "b", "hp_run_threshold": 0.45}))
    baton = Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={"door_cooldown": 9})
    seg_dir = tmp_path / "seg"
    va, vb = seg_dir / "a", seg_dir / "b"
    va.mkdir(parents=True), vb.mkdir(parents=True)
    (va / "stop.state").write_bytes(b"x")
    clock = FakeClock()
    procs = [
        FakeProc(va, fitness={"final_map_id": 51, "lead_hp": 20, "turns": 100}, polls_until_done=1),
        FakeProc(vb, fitness={"final_map_id": 13, "lead_hp": 4, "turns": 100}, polls_until_done=1),
    ]
    run_segment(
        "rom.gb", seg, baton, seg_dir, tmp_path, popen=_fake_popen_factory(procs), sleep=clock.sleep, clock=clock
    )
    from autotune_bridge import load_genome_from_notes

    a_genome = load_genome_from_notes(va / "genome.md")
    b_genome = load_genome_from_notes(vb / "genome.md")
    assert a_genome["hp_run_threshold"] == 0.2  # the lane's own variant value, not the sibling's
    assert b_genome["hp_run_threshold"] == 0.45
    assert a_genome["door_cooldown"] == 9  # inherited from the baton


def test_build_agent_cmd_gives_each_lane_a_private_advice_inbox(tmp_path):
    """Continuous self-heal reaches a running lane through the inbox; a shared one would cross-feed.

    Two lanes must never point at the same inbox: `_apply_advice` hot-applies whatever it finds,
    so one shared path would push every lane onto the first winner's genome and erase the spread.
    """
    va, vb = tmp_path / "a", tmp_path / "b"
    baton = relay.Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    seg = relay.SEGMENTS[0]
    cmd_a, _ = relay.build_agent_cmd("rom.gb", seg, {"label": "base"}, va, baton, tmp_path)
    cmd_b, _ = relay.build_agent_cmd("rom.gb", seg, {"label": "patient"}, vb, baton, tmp_path)
    assert f"--advice-inbox {va / 'advice'}" in " ".join(cmd_a)
    assert f"--advice-inbox {vb / 'advice'}" in " ".join(cmd_b)
    assert cmd_a[cmd_a.index("--advice-inbox") + 1] != cmd_b[cmd_b.index("--advice-inbox") + 1]


def test_build_agent_cmd_sideloop_is_opt_in_and_threaded(tmp_path):
    """--sideloop-every is off unless asked for; when asked, it reaches the lane verbatim."""
    vdir = tmp_path / "v"
    baton = relay.Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    seg = relay.SEGMENTS[0]
    off, _ = relay.build_agent_cmd("rom.gb", seg, {"label": "base"}, vdir, baton, tmp_path)
    assert "--sideloop-every" not in off
    on, _ = relay.build_agent_cmd("rom.gb", seg, {"label": "base"}, vdir, baton, tmp_path, sideloop_every=400)
    assert "--sideloop-every 400" in " ".join(on)


def test_run_segment_passes_sideloop_cadence_to_every_lane(tmp_path):
    """The cadence is a segment-level setting: every lane heals, not just the first."""
    seg = _tiny_seg(({"label": "a"}, {"label": "b"}))
    baton = Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    seg_dir = tmp_path / "seg"
    va, vb = seg_dir / "a", seg_dir / "b"
    va.mkdir(parents=True), vb.mkdir(parents=True)
    (va / "stop.state").write_bytes(b"x")
    clock = FakeClock()
    procs = [
        FakeProc(va, fitness={"final_map_id": 51, "lead_hp": 20, "turns": 100}, polls_until_done=1),
        FakeProc(vb, fitness={"final_map_id": 1, "lead_hp": 5, "turns": 100}, polls_until_done=1),
    ]
    launched = []
    popen = _fake_popen_factory(procs)

    def spy(cmd, **kwargs):
        launched.append(cmd)
        return popen(cmd, **kwargs)

    run_segment(
        "rom.gb",
        seg,
        baton,
        seg_dir,
        tmp_path,
        popen=spy,
        sleep=clock.sleep,
        clock=clock,
        sideloop_every=250,
    )
    assert len(launched) == 2
    for cmd in launched:
        assert cmd[cmd.index("--sideloop-every") + 1] == "250"


def test_acquire_relay_lock_refuses_while_a_live_relay_holds_it(tmp_path):
    """Parallel relays starve every lane; a starved lane reports as wedged, not as slow."""
    lock = tmp_path / "relay.lock"
    ok, holder = relay.acquire_relay_lock(lock, pid=100, alive=lambda p: True)
    assert (ok, holder) == (True, 100)
    ok, holder = relay.acquire_relay_lock(lock, pid=200, alive=lambda p: True)
    assert ok is False and holder == 100


def test_acquire_relay_lock_takes_over_a_stale_lock(tmp_path):
    """A killed relay must not block the next one — the holder is checked for liveness, not trusted."""
    lock = tmp_path / "relay.lock"
    relay.acquire_relay_lock(lock, pid=100, alive=lambda p: True)
    ok, holder = relay.acquire_relay_lock(lock, pid=200, alive=lambda p: False)
    assert ok is True and holder == 200
    assert lock.read_text() == "200"


def test_release_relay_lock_only_drops_our_own(tmp_path):
    lock = tmp_path / "relay.lock"
    relay.acquire_relay_lock(lock, pid=100, alive=lambda p: True)
    relay.release_relay_lock(lock, pid=200)
    assert lock.exists(), "a relay must never release a lock it does not hold"
    relay.release_relay_lock(lock, pid=100)
    assert not lock.exists()


def test_sideloop_parallel_is_budgeted_from_the_cpu_count():
    """6 lanes x 6 subloops on a 32-core box is 42 emulators — the starvation that invalidated a run."""
    assert relay.sideloop_parallel_for(6, cpus=32) == 4  # 6 lanes + 24 subloop lanes <= 32
    assert relay.sideloop_parallel_for(6, cpus=8) == 1  # never zero, never unbounded
    assert relay.sideloop_parallel_for(1, cpus=64) == 6  # capped at the spread width
    assert relay.sideloop_parallel_for(6, cpus=4) == 1


def test_build_agent_cmd_passes_the_subloop_budget_to_the_lane(tmp_path):
    vdir = tmp_path / "v"
    baton = relay.Baton(state_path=tmp_path / "s.state", worldmap_path=None, genome={})
    cmd, _ = relay.build_agent_cmd(
        "rom.gb",
        relay.SEGMENTS[0],
        {"label": "base"},
        vdir,
        baton,
        tmp_path,
        sideloop_every=300,
        sideloop_parallel=4,
    )
    assert "--sideloop-parallel 4" in " ".join(cmd)
