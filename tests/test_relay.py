import json
import os
from pathlib import Path

import pytest
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


def test_segments_cover_the_road_to_cerulean():
    names = [s.name for s in SEGMENTS]
    assert names == [
        "route1_to_forest",
        "forest_to_pewter",
        "pewter_to_badge",
        "badge_to_mtmoon",
        "mtmoon_1f_to_b1f",
        "mtmoon_clear",
        "route4_to_cerulean",
        "cerulean_to_badge2",
        "cerulean_to_vermilion",
        "cerulean_recruit",
    ]
    assert SEGMENTS[0].stop_on_map == 51
    assert SEGMENTS[1].stop_on_map == 2
    assert SEGMENTS[2].stop_on_badge == 1
    assert SEGMENTS[3].stop_on_map == 59
    assert SEGMENTS[6].stop_on_map == 3
    assert SEGMENTS[7].stop_on_badge == 2
    assert SEGMENTS[8].stop_on_map == 5
    assert SEGMENTS[9].stop_on_party == 3 and "--catch" in SEGMENTS[9].extra_args


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
    party_seg = Segment("p", stop_on_map=None, stop_on_badge=None, max_turns=1, variants=(), stop_on_party=3)
    assert segment_success({"party_size": 3}, party_seg)
    assert not segment_success({"party_size": 2}, party_seg)


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


def test_main_dry_run_accepts_seed_worldmap(tmp_path, capsys):
    """The badge_to_mtmoon seed ships a .worldmap; the flag must be accepted without a dry-run touching it."""
    wm = tmp_path / "seed.worldmap"
    wm.write_text(json.dumps({"cells": {}, "blocked": {}, "encounters": {}, "bounds": {}}))
    rc = main(
        [
            "rom.gb",
            "--dry-run",
            "--run-dir",
            str(tmp_path / "r"),
            "--seed-worldmap",
            str(wm),
            "--segments",
            "badge_to_mtmoon",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "--stop-on-map 59" in out
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
    # --memory-dir is REQUIRED here: without it main() falls through to DEFAULT_MEMORY_DIR and
    # writes a real "[important] relay ... cleared by winner" line into the repo's own
    # pokedex/memory/observations.md. Measured: 438 such lines had accumulated from test runs,
    # every one citing a /tmp/pytest-of-*/ run dir that no longer exists. The agent loads that
    # file at session start, so a green test suite was quietly seeding the pipeline's memory
    # with its own fixtures.
    rc = main(
        [
            str(rom),
            "--run-dir",
            str(run_dir),
            "--segments",
            "route1_to_forest",
            "--seed-state",
            str(seed),
            "--memory-dir",
            str(tmp_path / "memory"),
        ]
    )
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


_FEW_CORES = (os.cpu_count() or 1) < 4
_RACE_SKIP = pytest.mark.skipif(
    _FEW_CORES,
    reason="barrier race needs N processes runnable at once; a 2-core CI runner deadlocks on it. "
    "The race is exercised on the dev box (32 cores), which is where the bug it guards was found.",
)


def _claim_lock_in_child(lock, q, barrier=None):
    if barrier is not None:
        barrier.wait()
    ok, holder = relay.acquire_relay_lock(lock)
    q.put(ok)
    if ok:  # hold it until told to let go, so the parent can observe refusal
        q.put("held")
        while not (lock.parent / "release").exists():
            import time as _t

            _t.sleep(0.05)
        relay.release_relay_lock()


def test_relay_lock_refuses_while_another_process_holds_it_and_frees_on_its_exit(tmp_path):
    """flock is per-process: it must be tested across processes, and it must vanish with the holder."""
    import multiprocessing as mp

    lock = tmp_path / "relay.lock"
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    holder = ctx.Process(target=_claim_lock_in_child, args=(lock, q))
    holder.start()
    assert q.get(timeout=60) is True and q.get(timeout=60) == "held"

    ok, who = relay.acquire_relay_lock(lock)
    assert ok is False and who == holder.pid, "a second relay must be refused and told who holds it"

    (tmp_path / "release").write_text("")
    holder.join(timeout=60)
    ok, _ = relay.acquire_relay_lock(lock)
    assert ok is True, "once the holder exits, the lock is free — no stale state to clear"
    relay.release_relay_lock()


@_RACE_SKIP
def test_relay_lock_is_atomic_under_a_real_race(tmp_path):
    """Five relays from one shell command start within milliseconds; exactly one may win."""
    import multiprocessing as mp

    lock = tmp_path / "relay.lock"
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    barrier = ctx.Barrier(8)
    procs = [ctx.Process(target=_claim_lock_in_child, args=(lock, q, barrier)) for _ in range(8)]
    for p in procs:
        p.start()
    results = []
    for _ in range(8):
        results.append(q.get(timeout=120))
    winners = [r for r in results if r is True]
    assert len(winners) == 1, f"exactly one relay may hold the lock, got {len(winners)}"
    (tmp_path / "release").write_text("")
    for p in procs:
        p.join(timeout=60)


def test_main_refuses_when_another_relay_holds_the_lock(tmp_path, monkeypatch, capsys):
    """The guard in main(): a second relay prints why and exits 2 without touching the box."""
    monkeypatch.setattr(relay, "acquire_relay_lock", lambda *a, **k: (False, 4242))
    launched = []
    monkeypatch.setattr(relay, "run_segment", lambda *a, **k: launched.append(1) or (None, []))
    rom = tmp_path / "rom.gb"
    rom.write_bytes(b"x")
    seed = tmp_path / "seed.state"
    seed.write_bytes(b"x")
    rc = main([str(rom), "--seed-state", str(seed), "--segments", "route1_to_forest", "--run-dir", str(tmp_path / "r")])
    assert rc == 2
    assert "REFUSED: relay pid 4242" in capsys.readouterr().out
    assert launched == [], "a refused relay must launch nothing"


def test_release_relay_lock_is_a_noop_without_a_lock_and_swallows_close_errors(monkeypatch):
    relay._RELAY_LOCK_FD = None
    relay.release_relay_lock()  # nothing held: no error
    relay._RELAY_LOCK_FD = 999_999  # a bogus fd: flock/close raise OSError, release must not
    relay.release_relay_lock()
    assert relay._RELAY_LOCK_FD is None


def test_acquire_relay_lock_reports_holder_zero_when_the_lock_file_is_unreadable(tmp_path, monkeypatch):
    """A held lock whose pid cannot be parsed still refuses — it just cannot name the holder."""
    import multiprocessing as mp

    lock = tmp_path / "relay.lock"
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    holder = ctx.Process(target=_claim_lock_in_child, args=(lock, q))
    holder.start()
    assert q.get(timeout=60) is True and q.get(timeout=60) == "held"
    monkeypatch.setattr(relay.os, "pread", lambda *a: b"not-a-pid")
    ok, who = relay.acquire_relay_lock(lock)
    assert (ok, who) == (False, 0)
    (tmp_path / "release").write_text("")
    holder.join(timeout=60)


# ---- inert spread detection -----------------------------------------------------------------


def _fit(**kw):
    base = {"turns": 364, "final_map_id": 59, "final_x": 18, "final_y": 5, "stuck_count": 20}
    base.update(kw)
    return base


def _lane(label, fitness, **kw):
    return {"label": label, "fitness": fitness, "success": True, **kw}


def _seg_named(name="badge_to_mtmoon"):
    return Segment(name, stop_on_map=59, stop_on_badge=None, max_turns=10, variants=())


def test_identical_lanes_are_called_out_as_one_sample(capsys):
    """Six lanes that agree byte-for-byte are one result copied six times, not six confirmations.
    The NAV spread varies knobs the ROM-truth leg never reads, so it produced exactly this — and
    the silence is what made it cost six lanes x 12,000 turns to notice."""
    results = [_lane(str(i), _fit()) for i in range(6)]
    assert relay.report_inert_spread(_seg_named(), results) is True
    out = capsys.readouterr().out
    assert "identical fitness" in out and "ONE sample" in out


def test_a_spread_that_actually_diverged_is_not_flagged(capsys):
    results = [_lane("a", _fit()), _lane("b", _fit(turns=901, final_map_id=14))]
    assert relay.report_inert_spread(_seg_named(), results) is False
    assert capsys.readouterr().out == ""


def test_wall_clock_noise_alone_does_not_count_as_divergence(capsys):
    """Only what the lane DID is compared. A key the lanes happen to differ on for reasons other
    than behaviour must not disguise a spread that explored nothing."""
    results = [_lane("a", _fit(lead_hp=32)), _lane("b", _fit(lead_hp=31))]
    assert relay.report_inert_spread(_seg_named(), results) is True


def test_killed_and_empty_lanes_are_not_evidence(capsys):
    assert relay.report_inert_spread(_seg_named(), [_lane("a", _fit())]) is False  # one lane proves nothing
    assert relay.report_inert_spread(_seg_named(), [_lane("a", _fit()), _lane("b", {}, killed=True)]) is False
    assert relay.report_inert_spread(_seg_named(), []) is False


def test_nav_spread_varies_a_knob_the_truth_leg_reads():
    """Regression guard for the inert spread itself: the NAV variants must differ on something
    the ROM-truth planner consults, not only on the waypoint Navigator's knobs."""
    assert "truth_refuse_strikes" in relay.BASE_GENOME
    varied = {v.get("truth_refuse_strikes") for v in relay.NAV_SPREAD if "truth_refuse_strikes" in v}
    assert len(varied) >= 2, "the spread must explore more than one value"


# ---- stop_min_x: the east-exit vs west-entrance disambiguation ------------------------------


def test_mtmoon_clear_requires_the_east_side_of_route_4():
    """Route 4's west side is where the lane ENTERED the cave — its entrance mat is (18,5), the
    dungeon's east exit lands at (24,5). Without the column check the 59<->15 entrance spring
    scores as a clear on its first bounce."""
    seg = next(s for s in SEGMENTS if s.name == "mtmoon_clear")
    assert (seg.stop_on_map, seg.stop_min_x) == (15, 22)
    bounce = {"final_map_id": 15, "final_x": 18, "final_y": 5}
    cleared = {"final_map_id": 15, "final_x": 24, "final_y": 5}
    assert not relay.segment_success(bounce, seg)
    assert relay.segment_success(cleared, seg)
    assert not relay.segment_success({"final_map_id": 59, "final_x": 30}, seg)


def test_stop_min_x_reaches_the_lane_command_line():
    seg = next(s for s in SEGMENTS if s.name == "mtmoon_clear")
    baton = Baton(state_path=Path("s.state"), worldmap_path=None, genome={})
    cmd, _env = relay.build_agent_cmd("rom.gb", seg, {"label": "v"}, Path("v"), baton, Path("run"))
    joined = " ".join(cmd)
    assert "--stop-on-map 15" in joined and "--stop-min-x 22" in joined
    nav = next(s for s in SEGMENTS if s.name == "mtmoon_1f_to_b1f")
    cmd2, _ = relay.build_agent_cmd("rom.gb", nav, {"label": "v"}, Path("v"), baton, Path("run"))
    assert "--stop-min-x" not in " ".join(cmd2)  # a plain map stop stays plain


def test_build_agent_cmd_emits_stop_on_party_and_catch_list(tmp_path):
    seg = next(s for s in SEGMENTS if s.name == "cerulean_recruit")
    cmd, _ = build_agent_cmd("rom.gb", seg, seg.variants[0], tmp_path / "v", _baton(tmp_path), tmp_path)
    joined = " ".join(cmd)
    assert "--stop-on-party 3" in joined
    assert "--catch Paras,Oddish,Pikachu,Mankey,Sandshrew" in joined
