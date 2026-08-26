from __future__ import annotations

from pathlib import Path

from fixtures.make_fixture_run import make_fixture_run

from viewer.store import RunStore


def test_list_runs_empty_when_missing(tmp_path: Path):
    assert RunStore(tmp_path / "nope").list_runs() == []


def test_list_and_load(tmp_path: Path):
    make_fixture_run(tmp_path, "20260626-000001-aaaa")
    make_fixture_run(tmp_path, "20260626-000002-bbbb")
    store = RunStore(tmp_path)
    runs = store.list_runs()
    assert [r.run_id for r in runs] == ["20260626-000002-bbbb", "20260626-000001-aaaa"]
    assert runs[0].status == "done"
    assert runs[0].battles_won == 1
    assert runs[0].frame_count == 4
    assert runs[0].thumbnail == "000040.png"


def test_load_events_skips_malformed(tmp_path: Path):
    run_dir = make_fixture_run(tmp_path, "r")
    with open(run_dir / "events.jsonl", "a", encoding="utf-8") as fh:
        fh.write("NOT JSON\n")
    events = RunStore(tmp_path).load_events("r")
    assert len(events) == 5  # malformed line skipped
    assert RunStore(tmp_path).frame_names("r")[0] == "000010.png"


def test_live_status_without_summary(tmp_path: Path):
    run_dir = make_fixture_run(tmp_path, "r")
    (run_dir / "summary.json").unlink()
    assert RunStore(tmp_path).list_runs()[0].status == "live"


def test_run_summary_to_dict(tmp_path: Path):
    make_fixture_run(tmp_path, "r")
    summary = RunStore(tmp_path).list_runs()[0]
    d = summary.to_dict()
    assert d["run_id"] == "r"
    assert d["status"] == "done"
    assert d["battles_won"] == 1


def test_label_from_meta_json(tmp_path: Path):
    run_dir = make_fixture_run(tmp_path, "r")
    (run_dir / "meta.json").write_text('{"label": "Beat 1 — flail"}')
    assert RunStore(tmp_path).list_runs()[0].label == "Beat 1 — flail"


def test_label_defaults_empty_without_meta(tmp_path: Path):
    make_fixture_run(tmp_path, "r")
    assert RunStore(tmp_path).list_runs()[0].label == ""


def test_label_falls_back_to_summary_params(tmp_path: Path):
    run_dir = make_fixture_run(tmp_path, "r")
    (run_dir / "summary.json").write_text('{"params": {"label": "from-summary"}}')
    assert RunStore(tmp_path).list_runs()[0].label == "from-summary"


def test_get_meta_invalid_json_returns_empty(tmp_path: Path):
    run_dir = make_fixture_run(tmp_path, "r")
    (run_dir / "meta.json").write_text("NOT JSON")
    assert RunStore(tmp_path).get_meta("r") == {}
    assert RunStore(tmp_path).list_runs()[0].label == ""


def test_get_summary_with_invalid_json(tmp_path: Path):
    run_dir = tmp_path / "r"
    run_dir.mkdir(parents=True)
    (run_dir / "summary.json").write_text("INVALID JSON")
    assert RunStore(tmp_path).get_summary("r") == {}


def test_frame_names_missing_frames_dir(tmp_path: Path):
    run_dir = tmp_path / "r"
    run_dir.mkdir(parents=True)
    assert RunStore(tmp_path).frame_names("r") == []


def test_load_events_missing_events_file(tmp_path: Path):
    run_dir = tmp_path / "r"
    run_dir.mkdir(parents=True)
    assert RunStore(tmp_path).load_events("r") == []


def test_load_events_with_empty_lines(tmp_path: Path):
    run_dir = tmp_path / "r"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text('{"a": 1}\n\n{"b": 2}\n  \n{"c": 3}')
    events = RunStore(tmp_path).load_events("r")
    assert len(events) == 3
    assert events[0] == {"a": 1}


def test_list_runs_skips_dirs_that_are_not_runs(tmp_path: Path):
    """The fan-out's fitness JSONs and demo-runs/states are not playable runs."""
    make_fixture_run(tmp_path, "20260626-000001-aaaa")
    proof = tmp_path / "fanout-proof"
    proof.mkdir()
    (proof / "fanout-proof-20260824-221113.json").write_text('{"cohort": "fanout-proof"}')
    (tmp_path / "fanout").mkdir()
    states = tmp_path / "states"
    states.mkdir()
    (states / "route1.state").write_bytes(b"\x00")

    assert [r.run_id for r in RunStore(tmp_path).list_runs()] == ["20260626-000001-aaaa"]


def test_list_runs_keeps_a_run_that_has_only_started(tmp_path: Path):
    """recorder.start lays down frames/ and events.jsonl before turn 1 — keep it."""
    live = tmp_path / "20260825-120000-live"
    (live / "frames").mkdir(parents=True)
    (live / "events.jsonl").write_text("")

    runs = RunStore(tmp_path).list_runs()
    assert [r.run_id for r in runs] == ["20260825-120000-live"]
    assert runs[0].status == "live"


def test_list_runs_sorts_beat_numbers_naturally(tmp_path: Path):
    for run_id in ("beat9-discovery", "beat10-gym-brock", "beat11-mt-moon", "beat12-mt-moon-clear"):
        make_fixture_run(tmp_path, run_id)

    assert [r.run_id for r in RunStore(tmp_path).list_runs()] == [
        "beat12-mt-moon-clear",
        "beat11-mt-moon",
        "beat10-gym-brock",
        "beat9-discovery",
    ]
