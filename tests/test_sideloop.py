import json

import sideloop
from sideloop import advice_line, main, pick_by_score, run_sideloop, sideloop_segment


class FakeProc:
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


def test_sideloop_segment_has_no_stop_condition():
    seg = sideloop_segment(horizon=800)
    assert seg.stop_on_map is None and seg.stop_on_badge is None
    assert seg.max_turns == 800


def test_pick_by_score_prefers_higher_evolve_score():
    good = {
        "label": "g",
        "fitness": {
            "turns": 500,
            "battles_won": 9,
            "maps_visited": 4,
            "final_map_id": 51,
            "party_size": 1,
            "stuck_count": 1,
            "level_ups": 3,
            "badges": 0,
        },
    }
    bad = {
        "label": "b",
        "fitness": {
            "turns": 500,
            "battles_won": 0,
            "maps_visited": 1,
            "final_map_id": 12,
            "party_size": 1,
            "stuck_count": 400,
            "level_ups": 0,
            "badges": 0,
        },
    }
    empty = {"label": "e", "fitness": {}}
    assert pick_by_score([bad, good, empty])["label"] == "g"
    assert pick_by_score([empty]) is None


def test_advice_line_is_valid_genome_patch():
    line = json.loads(advice_line({"hp_run_threshold": 0.35}))
    assert line["schema"] == "pokemon.advice.v1"
    assert line["type"] == "genome_patch"
    assert line["data"] == {"hp_run_threshold": 0.35}
    assert line["id"]


def test_run_sideloop_writes_winner_advice(tmp_path):
    state = tmp_path / "live.state"
    state.write_bytes(b"x")
    work = tmp_path / "work"
    lanes = work / "lanes"
    (lanes / "base").mkdir(parents=True)
    (lanes / "cautious").mkdir(parents=True)
    clock = FakeClock()
    procs = [
        FakeProc(
            lanes / "base",
            fitness={
                "turns": 400,
                "battles_won": 0,
                "maps_visited": 1,
                "final_map_id": 51,
                "party_size": 1,
                "stuck_count": 300,
                "level_ups": 0,
                "badges": 0,
            },
        ),
        FakeProc(
            lanes / "cautious",
            fitness={
                "turns": 400,
                "battles_won": 8,
                "maps_visited": 3,
                "final_map_id": 2,
                "party_size": 1,
                "stuck_count": 2,
                "level_ups": 2,
                "badges": 0,
            },
        ),
    ]
    queue = list(procs)

    def fake_popen(cmd, env=None, cwd=None, stdout=None, stderr=None, start_new_session=False):
        assert "--no-self-heal" in cmd and "--sideloop-every" not in " ".join(cmd)
        return queue.pop(0)

    advice_out = tmp_path / "inbox" / "sideloop.jsonl"
    winner = run_sideloop(
        "rom.gb",
        state,
        {"door_cooldown": 5},
        work,
        advice_out,
        parallel=2,
        popen=fake_popen,
        sleep=clock.sleep,
        clock=clock,
    )
    assert winner["label"] == "cautious"
    written = json.loads(advice_out.read_text().strip())
    assert written["type"] == "genome_patch"
    assert written["data"]["door_cooldown"] == 5  # baton genome carried into the winner


def test_run_sideloop_returns_none_without_lanes_finishing(tmp_path):
    state = tmp_path / "live.state"
    state.write_bytes(b"x")
    (tmp_path / "work" / "lanes" / "base").mkdir(parents=True)
    clock = FakeClock()
    queue = [FakeProc(tmp_path / "work" / "lanes" / "base", polls_until_done=10**6)]

    def fake_popen(cmd, env=None, cwd=None, stdout=None, stderr=None, start_new_session=False):
        return queue.pop(0)

    advice_out = tmp_path / "inbox" / "sideloop.jsonl"
    winner = run_sideloop(
        "rom.gb",
        state,
        {},
        tmp_path / "work",
        advice_out,
        parallel=1,
        timeout=30.0,
        popen=fake_popen,
        sleep=clock.sleep,
        clock=clock,
    )
    assert winner is None
    assert not advice_out.exists()


def test_main_returns_0_and_forwards_args_when_winner_found(tmp_path, monkeypatch):
    captured = {}

    def fake_run_sideloop(rom, state, genome, work_dir, advice_out, horizon=800, parallel=4, timeout=600.0, **_kw):
        captured["args"] = (rom, state, genome, work_dir, advice_out, horizon, parallel, timeout)
        return {"label": "winner"}

    monkeypatch.setattr(sideloop, "run_sideloop", fake_run_sideloop)
    rc = main(
        [
            "rom.gb",
            "--state",
            str(tmp_path / "live.state"),
            "--genome-json",
            '{"door_cooldown": 5}',
            "--work-dir",
            str(tmp_path / "work"),
            "--advice-out",
            str(tmp_path / "advice.jsonl"),
            "--horizon",
            "500",
            "--parallel",
            "2",
            "--timeout",
            "60",
        ]
    )
    assert rc == 0
    rom, state, genome, work_dir, advice_out, horizon, parallel, timeout = captured["args"]
    assert rom == "rom.gb"
    assert state == str(tmp_path / "live.state")
    assert genome == {"door_cooldown": 5}
    assert work_dir == str(tmp_path / "work")
    assert advice_out == str(tmp_path / "advice.jsonl")
    assert horizon == 500
    assert parallel == 2
    assert timeout == 60.0


def test_main_returns_1_when_no_winner(tmp_path, monkeypatch):
    monkeypatch.setattr(sideloop, "run_sideloop", lambda *a, **k: None)
    rc = main(
        [
            "rom.gb",
            "--state",
            str(tmp_path / "live.state"),
            "--work-dir",
            str(tmp_path / "work"),
            "--advice-out",
            str(tmp_path / "advice.jsonl"),
        ]
    )
    assert rc == 1
