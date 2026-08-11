"""The viewer's HEAL button: POST /api/runs/{id}/prompt drafts a discovery prompt."""

from __future__ import annotations

import functools
import json
from pathlib import Path

from fastapi.testclient import TestClient
from fixtures.make_fixture_run import make_fixture_run
from test_viewer_heal import FakeRunner as _HealFakeRunner

from viewer.prompt import PromptDrafter, compose_detail
from viewer.server import create_app

RUN_ID = "20260626-000001-aaaa"
PROMPT_JSON = json.dumps(
    {"prompt": "You are the discovery engine…", "escalation": {"rule": "navigation-thrash", "reason": "x"}}
)

# Same double as the heal tests, defaulted to this module's happy-path stdout.
FakeRunner = functools.partial(_HealFakeRunner, stdout=PROMPT_JSON)


# ---------------------------------------------------------------------------
# compose_detail — the human half of the prompt
# ---------------------------------------------------------------------------


def test_compose_detail_joins_note_and_anomaly():
    joined = compose_detail("waypoint goes stale", "T204 Stuck ×20")
    assert joined == "waypoint goes stale — selected anomaly: T204 Stuck ×20"


def test_compose_detail_tolerates_either_half_missing():
    assert compose_detail("just a note", "") == "just a note"
    assert compose_detail("  ", "T204 Stuck ×20") == "T204 Stuck ×20"
    assert compose_detail("", "") == ""


# ---------------------------------------------------------------------------
# PromptDrafter
# ---------------------------------------------------------------------------


def test_draft_invokes_discovery_prompt_with_rule_and_detail(tmp_path: Path):
    make_fixture_run(tmp_path, RUN_ID)
    runner = FakeRunner()
    result = PromptDrafter(tmp_path, runner=runner).draft(
        RUN_ID, rule="navigation-thrash", note="waypoint goes stale", anomaly="T204 Stuck ×20"
    )

    assert result["prompt"] == "You are the discovery engine…"
    assert result["escalation"]["rule"] == "navigation-thrash"
    cmd = runner.calls[0]
    assert "prompt" in cmd and "--json" in cmd
    assert cmd[cmd.index("--rule") + 1] == "navigation-thrash"
    assert cmd[cmd.index("--detail") + 1] == "waypoint goes stale — selected anomaly: T204 Stuck ×20"
    assert cmd[cmd.index("--fitness") + 1].endswith("summary.json")


def test_draft_falls_back_to_manual_rule(tmp_path: Path):
    make_fixture_run(tmp_path, RUN_ID)
    runner = FakeRunner()
    PromptDrafter(tmp_path, runner=runner).draft(RUN_ID, note="something odd")
    cmd = runner.calls[0]
    assert cmd[cmd.index("--rule") + 1] == "manual"


def test_draft_accepts_manual_explicitly(tmp_path: Path):
    """'manual' is the drafter's own fallback — passing it by name must not error."""
    make_fixture_run(tmp_path, RUN_ID)
    runner = FakeRunner()
    result = PromptDrafter(tmp_path, runner=runner).draft(RUN_ID, rule="manual")
    assert "error" not in result
    cmd = runner.calls[0]
    assert cmd[cmd.index("--rule") + 1] == "manual"


def test_draft_pins_cwd_to_the_repo_root(tmp_path: Path):
    """discovery.py's observation/route defaults are relative — a viewer launched
    outside the repo root must not silently resolve them elsewhere."""
    make_fixture_run(tmp_path, RUN_ID)
    runner = FakeRunner()
    PromptDrafter(tmp_path, runner=runner).draft(RUN_ID)
    cwd = runner.kwargs[0]["cwd"]
    assert (Path(cwd) / "scripts" / "discovery.py").is_file()


def test_draft_rejects_unknown_rule(tmp_path: Path):
    make_fixture_run(tmp_path, RUN_ID)
    runner = FakeRunner()
    result = PromptDrafter(tmp_path, runner=runner).draft(RUN_ID, rule="bogus")
    assert result == {"error": "unknown rule: bogus"}
    assert runner.calls == []  # never shells out on a bad rule


def test_draft_reports_a_live_run(tmp_path: Path):
    (tmp_path / RUN_ID).mkdir()
    result = PromptDrafter(tmp_path, runner=FakeRunner()).draft(RUN_ID)
    assert "summary.json" in result["error"]


def test_draft_surfaces_subprocess_failure(tmp_path: Path):
    make_fixture_run(tmp_path, RUN_ID)
    runner = FakeRunner(stdout="", returncode=1, stderr="[discovery] unreadable fitness file")
    result = PromptDrafter(tmp_path, runner=runner).draft(RUN_ID)
    assert result["error"] == "[discovery] unreadable fitness file"


def test_draft_surfaces_a_runner_that_raises(tmp_path: Path):
    make_fixture_run(tmp_path, RUN_ID)

    def exploding_runner(cmd, **kwargs):
        raise OSError("no such interpreter")

    result = PromptDrafter(tmp_path, runner=exploding_runner).draft(RUN_ID)
    assert result == {"error": "no such interpreter"}


def test_draft_surfaces_non_json_output(tmp_path: Path):
    make_fixture_run(tmp_path, RUN_ID)
    result = PromptDrafter(tmp_path, runner=FakeRunner(stdout="not json")).draft(RUN_ID)
    assert result["error"] == "discovery.py prompt returned no JSON"


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


def test_endpoint_drafts_and_404s(tmp_path: Path):
    make_fixture_run(tmp_path, RUN_ID)
    drafter = PromptDrafter(tmp_path, runner=FakeRunner())
    client = TestClient(create_app(tmp_path, prompt_drafter=drafter))

    ok = client.post(
        f"/api/runs/{RUN_ID}/prompt",
        json={"rule": "terminal-wedge", "note": "wedged", "anomaly": "T7993 Stuck ×95"},
    )
    assert ok.status_code == 200
    assert ok.json()["prompt"] == "You are the discovery engine…"

    assert client.post("/api/runs/missing/prompt", json={}).status_code == 404


def test_endpoint_tolerates_an_empty_body(tmp_path: Path):
    make_fixture_run(tmp_path, RUN_ID)
    drafter = PromptDrafter(tmp_path, runner=FakeRunner())
    client = TestClient(create_app(tmp_path, prompt_drafter=drafter))
    assert client.post(f"/api/runs/{RUN_ID}/prompt", json={}).status_code == 200
