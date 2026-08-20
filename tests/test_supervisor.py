"""Supervisor decisions against synthetic lane logs shaped like the measured runs: the Center
door bounce (Sonnet 08-19: 58<->2, 617 round trips in probe13), the gate-room spring (qwen38 r2:
2<->57), and the Brock-day load rule (starvation must never be reported as a wall)."""

import json

import supervisor
from supervisor import SPRING_MIN, Supervisor, spring_counts


def _spring_log(a: int, b: int, trips: int) -> str:
    lines = []
    for _ in range(trips):
        lines.append(f"[12:00:00] MAP CHANGE | {a} -> {b} | Pos: (13, 25)")
        lines.append(f"[12:00:00] MAP CHANGE | {b} -> {a} | Pos: (13, 25)")
    return "\n".join(lines)


def test_spring_counts_round_trips_only():
    springs = spring_counts(_spring_log(58, 2, 7))
    assert springs["2<->58"] >= 7
    # A one-way walk (2 -> 14 -> 15) is travel, not a spring.
    assert spring_counts("MAP CHANGE | 2 -> 14 |\nMAP CHANGE | 14 -> 15 |") == {}


def test_observe_nudges_once_per_wall_and_ignores_small_counts():
    sup = Supervisor()
    nudges = sup.observe([_spring_log(58, 2, 10)])
    assert len(nudges) == 1 and "2<->58" in nudges[0] and "rom_truth" in nudges[0]
    assert sup.observe([_spring_log(58, 2, 10)]) == []  # once per fingerprint, ever
    assert sup.observe([_spring_log(3, 4, SPRING_MIN - 2)]) == []  # heal-trip scale: not a wall


def test_stall_nudge_respects_the_load_rule():
    sup = Supervisor()
    assert sup.observe([], positions="sig-a") == []  # first sighting arms the comparison
    assert sup.observe([], positions="sig-a", load_ok=False) == []  # Brock rule: loaded box, no verdict
    nudges = sup.observe([], positions="sig-a")
    assert len(nudges) == 1 and "STALL" in nudges[0]
    assert sup.observe([], positions="sig-a") == []  # stall is also once per run


def test_classify_exit_harness_death_resumes_then_alerts():
    sup = Supervisor(max_resumes=2)
    assert sup.classify_exit(budget_s=7200, used_s=100, baton=False, harness_death=True)["action"] == "resume"
    assert sup.classify_exit(budget_s=7200, used_s=100, baton=False, harness_death=True)["action"] == "resume"
    assert sup.classify_exit(budget_s=7200, used_s=100, baton=False, harness_death=True)["action"] == "stop_alert"


def test_classify_exit_baton_moves_on():
    sup = Supervisor()
    assert sup.classify_exit(budget_s=7200, used_s=7000, baton=True, harness_death=False)["action"] == "next_leg"


def test_early_exit_continues_with_evidence_then_charges_the_wall():
    sup = Supervisor(max_continuations=1, escalate_after=2)
    sup.observe([_spring_log(58, 2, 20)])
    d = sup.classify_exit(budget_s=7200, used_s=1134, baton=False, harness_death=False)  # Sonnet's 18.9m shape
    assert d["action"] == "continue" and "2<->58" in d["prompt"] and "minutes of budget remain" in d["prompt"]
    # Continuation budget spent: the same early exit now charges an attempt against the wall.
    d = sup.classify_exit(budget_s=7200, used_s=1134, baton=False, harness_death=False)
    assert d == {"action": "retry_leg", "reason": "attempt 1/2 on wall 2<->58", "wall": "2<->58"}
    d = sup.classify_exit(budget_s=7200, used_s=7100, baton=False, harness_death=False)
    assert d["action"] == "escalate" and d["wall"] == "2<->58"


def test_budget_spent_without_fingerprint_still_counts_attempts():
    sup = Supervisor(escalate_after=3)
    d = sup.classify_exit(budget_s=7200, used_s=7100, baton=False, harness_death=False)
    assert d["action"] == "retry_leg" and d["wall"] == "no-fingerprint"


def test_state_roundtrip(tmp_path):
    sup = Supervisor(max_continuations=1)
    sup.observe([_spring_log(2, 57, 9)])
    sup.classify_exit(budget_s=7200, used_s=7100, baton=False, harness_death=False)
    path = tmp_path / "state.json"
    sup.save(path)
    back = Supervisor.load(path)
    assert back.fingerprints == sup.fingerprints and back.springs == sup.springs
    assert back.nudged == sup.nudged and back.max_continuations == 1
    assert Supervisor.load(tmp_path / "absent.json").springs == {}  # fresh state


def test_cli_classify_exit_and_replay(tmp_path, capsys):
    log = tmp_path / "lane.log"
    log.write_text(_spring_log(58, 2, 12))
    state = tmp_path / "state.json"
    rc = supervisor.main(
        [
            "classify-exit",
            "--state",
            str(state),
            "--budget",
            "7200",
            "--used",
            "1000",
            "--lane-log",
            str(log),
            "--lane-log",
            str(tmp_path / "missing.log"),
        ]
    )
    assert rc == 0
    decision = json.loads(capsys.readouterr().out)
    assert decision["action"] == "continue" and "WALL 2<->58" in decision["prompt"]
    assert decision["nudges"] and json.loads(state.read_text())["springs"]
    assert supervisor.main(["replay", str(log)]) == 0
    assert "WALL 2<->58: 12 round trips" in capsys.readouterr().out
