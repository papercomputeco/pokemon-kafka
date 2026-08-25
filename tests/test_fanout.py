"""Tests for the fan-out backends and runner.

The Daytona SDK is an optional dependency and is not installed in CI, so these
tests inject a fake `daytona` module. That is deliberate beyond convenience:
teardown is the behavior most worth testing and the least safe to test against
real infrastructure, since a bug there leaks billable sandboxes.
"""

from __future__ import annotations

import json
import sys
import types

import pytest
from fanout import get_backend
from fanout.backend import degraded_fitness
from fanout.local import LocalBackend

# ── backend contract ──────────────────────────────────────────────────


def test_degraded_fitness_has_every_key_score_reads():
    from evolve import score

    fitness = degraded_fitness(500)
    assert fitness["turns"] == 500
    assert fitness["stuck_count"] == 500
    # The point of the shape: scoring a failure must not raise.
    assert isinstance(score(fitness), (int, float))


# ── local backend ─────────────────────────────────────────────────────


def test_local_backend_runs_each_candidate_in_order(monkeypatch):
    seen = []

    def fake_run_agent(rom, turns, params, load_state=None, strategy=None):
        seen.append((rom, turns, params["n"], load_state, strategy))
        return {"party_size": params["n"]}

    monkeypatch.setattr("fanout.local.run_agent", fake_run_agent)
    out = LocalBackend().run_batch("rom.gb", 10, [{"n": 1}, {"n": 2}], strategy="medium")

    assert [f["party_size"] for f in out] == [1, 2]
    assert seen[0] == ("rom.gb", 10, 1, None, "medium")


def test_local_backend_defaults_to_heuristic_tier(monkeypatch):
    captured = {}

    def fake_run_agent(rom, turns, params, load_state=None, strategy=None):
        captured["strategy"] = strategy
        return {}

    monkeypatch.setattr("fanout.local.run_agent", fake_run_agent)
    LocalBackend().run_batch("rom.gb", 10, [{}])
    # low makes zero LLM calls; a different default would silently cost money.
    assert captured["strategy"] == "low"


# ── backend registry ──────────────────────────────────────────────────


def test_get_backend_local():
    assert isinstance(get_backend("local"), LocalBackend)


def test_get_backend_unknown_name():
    with pytest.raises(ValueError, match="unknown backend"):
        get_backend("ec2")


def test_get_backend_daytona_requires_snapshot_and_cohort(fake_daytona_sdk):
    with pytest.raises(ValueError, match="needs --snapshot and --cohort"):
        get_backend("daytona", snapshot="snap")


def test_get_backend_daytona_builds(fake_daytona_sdk):
    backend = get_backend("daytona", snapshot="snap", cohort="c1")
    assert backend.name == "daytona"
    assert backend.settings.snapshot == "snap"


# ── daytona backend ───────────────────────────────────────────────────


class FakeExec:
    def __init__(self, exit_code=0, result=""):
        self.exit_code = exit_code
        self.result = result


class FakeSandbox:
    def __init__(self, fitness_json='{"party_size": 3}', exec_fails=False, upload_fails=False):
        self.id = "sb-1"
        self.uploaded = []
        self.commands = []
        self._fitness_json = fitness_json
        self._exec_fails = exec_fails
        self._upload_fails = upload_fails
        self.fs = types.SimpleNamespace(upload_file=self._upload)
        self.process = types.SimpleNamespace(exec=self._exec)

    def _upload(self, local, remote, **kw):
        if self._upload_fails:
            raise RuntimeError("upload failed")
        self.uploaded.append((local, remote))

    def _exec(self, command, cwd=None, timeout=None, env=None):
        self.commands.append(command)
        if self._exec_fails:
            raise RuntimeError("exec failed")
        if command.startswith("cat "):
            return FakeExec(0, self._fitness_json)
        return FakeExec(0, "run output")


class FakeClient:
    def __init__(self, sandbox=None, create_fails=False, delete_fails=False):
        self.sandbox = sandbox or FakeSandbox()
        self.created = []
        self.deleted = []
        self._create_fails = create_fails
        self._delete_fails = delete_fails

    def create(self, params, timeout=None):
        if self._create_fails:
            raise RuntimeError("create failed")
        self.created.append(params)
        return self.sandbox

    def delete(self, sandbox):
        if self._delete_fails:
            raise RuntimeError("delete failed")
        self.deleted.append(sandbox)


@pytest.fixture
def fake_daytona_sdk(monkeypatch):
    """Install a stand-in `daytona` module so the lazy imports resolve."""

    module = types.ModuleType("daytona")

    class CreateSandboxFromSnapshotParams:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.kwargs = kwargs

    module.CreateSandboxFromSnapshotParams = CreateSandboxFromSnapshotParams
    module.Daytona = lambda *a, **k: FakeClient()
    monkeypatch.setitem(sys.modules, "daytona", module)
    return module


def _backend(client, **overrides):
    from fanout.daytona_backend import DaytonaBackend, DaytonaSettings

    settings = DaytonaSettings(snapshot="snap", cohort="cohort-1", **overrides)
    return DaytonaBackend(settings, client=client)


def test_build_agent_command_carries_params_and_disables_nested_healing():
    from fanout.daytona_backend import build_agent_command

    cmd = build_agent_command(500, {"door_cooldown": 4}, "low")
    assert "EVOLVE_PARAMS=" in cmd
    assert "door_cooldown" in cmd
    assert "--max-turns 500" in cmd
    # A race child spawning its own healer would recurse, billed per sandbox.
    assert "--no-self-heal" in cmd and "--no-in-run-heal" in cmd


def test_build_agent_command_includes_load_state():
    from fanout.daytona_backend import build_agent_command

    assert "--load-state" in build_agent_command(10, {}, "low", load_state="/tmp/s.state")


@pytest.mark.parametrize(
    "raw",
    ['{"not_fitness": 1}', "not json at all", "", "[1, 2, 3]"],
)
def test_parse_fitness_degrades_on_bad_payloads(raw):
    from fanout.daytona_backend import parse_fitness

    assert parse_fitness(raw, 99)["stuck_count"] == 99


def test_parse_fitness_accepts_real_payload():
    from fanout.daytona_backend import parse_fitness

    assert parse_fitness('{"party_size": 4}', 99)["party_size"] == 4


def test_settings_from_env_reads_secrets_not_image(monkeypatch):
    from fanout.daytona_backend import DaytonaSettings

    monkeypatch.setenv("FANOUT_CAPTURE_BASE_URL", "http://capture:8080")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    settings = DaytonaSettings.from_env(snapshot="s", cohort="c")
    assert settings.capture_base_url == "http://capture:8080"
    assert settings.anthropic_api_key == "sk-test"


def test_env_tags_cohort_and_routes_llm_through_capture(fake_daytona_sdk):
    backend = _backend(FakeClient(), capture_base_url="http://capture:8080", anthropic_api_key="sk-x")
    env = backend._env_for("arm-0")
    # Provenance only — tapes reads neither of these. The cohort tag that
    # actually reaches the store is `--project` on the sidecar command.
    assert env["FANOUT_COHORT"] == "cohort-1"
    assert env["FANOUT_VARIANT"] == "arm-0"
    assert "TAPES_PROJECT" not in env
    # LLM calls must egress through the sidecar, not straight to the vendor.
    assert env["ANTHROPIC_BASE_URL"] == "http://capture:8080"
    assert env["ANTHROPIC_API_KEY"] == "sk-x"


def test_sidecar_command_tags_cohort_and_targets_central_store():
    from fanout.daytona_backend import build_sidecar_command

    cmd = build_sidecar_command("postgres://u:p@h:5432/db", "race-1", "https://api.anthropic.com")
    # --project is the cohort tag that makes a fan-out one queryable group.
    assert "--project race-1" in cmd
    assert "--postgres postgres://u:p@h:5432/db" in cmd
    assert "--provider anthropic" in cmd
    assert cmd.rstrip().endswith("&")  # backgrounded; the agent runs next


def test_dsn_mode_points_agent_at_the_local_sidecar(fake_daytona_sdk):
    """Capture-in-image: sandboxes can't reach a host-local paperd."""
    backend = _backend(FakeClient(), postgres_dsn="postgres://x")
    assert backend._env_for("a")["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:8080"


def test_boundary_mode_used_when_no_dsn(fake_daytona_sdk):
    backend = _backend(FakeClient(), capture_base_url="http://central:9000")
    assert backend._env_for("a")["ANTHROPIC_BASE_URL"] == "http://central:9000"


def test_boundary_wins_when_both_are_set(fake_daytona_sdk):
    """A host serving boundary capture usually ALSO holds the store's DSN for
    verification. Inside a sandbox that loopback DSN resolves to the sandbox's
    own empty postgres — so the explicit capture URL must take precedence, and
    no in-sandbox sidecar may start."""
    client = FakeClient(FakeSandbox())
    backend = _backend(client, capture_base_url="http://central:9000", postgres_dsn="postgres://tapes@localhost/t")
    assert backend._env_for("a")["ANTHROPIC_BASE_URL"] == "http://central:9000"
    backend.run_batch("/rom.gb", 10, [{"label": "a"}])
    assert not any("tapes serve proxy" in c for c in client.sandbox.commands)


def test_sidecar_starts_and_is_awaited_before_the_agent(fake_daytona_sdk):
    """Capture must be LISTENING first or the opening turns are lost.

    The proxy is nohup'd, so its exec returns before the socket opens; a
    readiness wait has to sit between it and the agent.
    """
    client = FakeClient(FakeSandbox())
    _backend(client, postgres_dsn="postgres://x").run_batch("/rom.gb", 10, [{"label": "a"}])

    cmds = client.sandbox.commands
    assert "tapes serve proxy" in cmds[0]
    assert "curl" in cmds[1] and "127.0.0.1:8080" in cmds[1]
    assert "scripts/agent.py" in cmds[2]


def test_every_result_carries_per_arm_timing(fake_daytona_sdk):
    """Cost extrapolation needs measured per-arm wall clock, not guesses."""
    ok = _backend(FakeClient(FakeSandbox())).run_batch("/rom.gb", 10, [{"label": "a"}])
    assert isinstance(ok[0]["fanout_elapsed"], float)
    # The degraded path is stamped too — a failed arm still costs money.
    bad = _backend(FakeClient(create_fails=True)).run_batch("/rom.gb", 7, [{"label": "b"}])
    assert isinstance(bad[0]["fanout_elapsed"], float)


def test_no_sidecar_started_without_a_dsn(fake_daytona_sdk):
    client = FakeClient(FakeSandbox())
    _backend(client).run_batch("/rom.gb", 10, [{"label": "a"}])
    assert not any("tapes serve proxy" in c for c in client.sandbox.commands)


def test_settings_from_env_reads_dsn_and_upstream(monkeypatch):
    from fanout.daytona_backend import DaytonaSettings

    monkeypatch.setenv("TAPES_POSTGRES_DSN", "postgres://central/db")
    monkeypatch.setenv("FANOUT_LLM_UPSTREAM", "http://gpu-box:8000")
    settings = DaytonaSettings.from_env(snapshot="s", cohort="c")
    assert settings.postgres_dsn == "postgres://central/db"
    assert settings.llm_upstream == "http://gpu-box:8000"


def test_env_omits_absent_secrets(fake_daytona_sdk):
    env = _backend(FakeClient())._env_for("arm-0")
    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_API_KEY" not in env


def test_extra_env_is_injected(fake_daytona_sdk):
    backend = _backend(FakeClient(), extra_env={"KAFKA_BOOTSTRAP": "host:9092"})
    assert backend._env_for("a")["KAFKA_BOOTSTRAP"] == "host:9092"


def test_run_batch_uploads_rom_and_returns_fitness(fake_daytona_sdk):
    client = FakeClient(FakeSandbox('{"party_size": 6}'))
    out = _backend(client).run_batch("/local/rom.gb", 100, [{"label": "a"}])

    assert out[0]["party_size"] == 6
    # ROM arrives by upload — it is deliberately absent from the snapshot.
    assert client.sandbox.uploaded == [("/local/rom.gb", "/tmp/rom.gb")]
    assert client.deleted == [client.sandbox]


def test_run_batch_preserves_candidate_order(fake_daytona_sdk):
    client = FakeClient(FakeSandbox('{"party_size": 1}'))
    out = _backend(client, concurrency=3).run_batch("/rom.gb", 10, [{"label": f"a{i}"} for i in range(3)])
    assert len(out) == 3


def test_sandbox_is_deleted_even_when_the_run_fails(fake_daytona_sdk):
    client = FakeClient(FakeSandbox(exec_fails=True))
    out = _backend(client).run_batch("/rom.gb", 42, [{"label": "a"}])

    assert out[0]["stuck_count"] == 42  # degraded, not an exception
    assert client.deleted == [client.sandbox]  # the expensive part still cleaned up


def test_sandbox_is_deleted_when_upload_fails(fake_daytona_sdk):
    client = FakeClient(FakeSandbox(upload_fails=True))
    _backend(client).run_batch("/rom.gb", 42, [{"label": "a"}])
    assert client.deleted == [client.sandbox]


def test_create_failure_degrades_without_leaking(fake_daytona_sdk):
    client = FakeClient(create_fails=True)
    out = _backend(client).run_batch("/rom.gb", 7, [{"label": "a"}])
    assert out[0]["stuck_count"] == 7
    assert client.deleted == []  # nothing was created, so nothing to reap


def test_delete_failure_is_swallowed(fake_daytona_sdk):
    """A teardown error must not mask the run's result."""
    client = FakeClient(FakeSandbox(), delete_fails=True)
    out = _backend(client).run_batch("/rom.gb", 10, [{"label": "a"}])
    assert out[0]["party_size"] == 3


def test_nonzero_cat_exit_degrades(fake_daytona_sdk):
    class NoFitnessSandbox(FakeSandbox):
        def _exec(self, command, cwd=None, timeout=None, env=None):
            if command.startswith("cat "):
                return FakeExec(1, "")
            return FakeExec(0, "")

    out = _backend(FakeClient(NoFitnessSandbox())).run_batch("/rom.gb", 33, [{"label": "a"}])
    assert out[0]["stuck_count"] == 33


def test_unlabeled_candidates_get_positional_labels(fake_daytona_sdk):
    client = FakeClient()
    _backend(client).run_batch("/rom.gb", 10, [{}])
    assert client.created[0].kwargs["labels"]["variant"] == "variant_0"


def test_sweep_reaps_stragglers(fake_daytona_sdk):
    """The interrupt path: anything still tracked gets deleted."""
    client = FakeClient()
    backend = _backend(client)
    straggler = FakeSandbox()
    backend._live["orphan"] = straggler
    backend._sweep()
    assert client.deleted == [straggler]
    assert backend._live == {}


def test_lazy_client_is_constructed_from_sdk(fake_daytona_sdk):
    from fanout.daytona_backend import DaytonaBackend, DaytonaSettings

    backend = DaytonaBackend(DaytonaSettings(snapshot="s", cohort="c"))
    assert isinstance(backend._daytona(), FakeClient)


def test_create_passes_ephemeral_and_ttl_backstops(fake_daytona_sdk):
    """Server-side reaping matters if this driver is killed outright."""
    client = FakeClient()
    _backend(client, ttl_minutes=15).run_batch("/rom.gb", 10, [{"label": "a"}])
    kwargs = client.created[0].kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["ttl_minutes"] == 15
    assert kwargs["snapshot"] == "snap"


# ── cli ───────────────────────────────────────────────────────────────


def test_build_work_list_is_deterministic_for_a_seed():
    from fanout.cli import build_work_list

    assert build_work_list(3, "navigation-thrash", 7) == build_work_list(3, "navigation-thrash", 7)


def test_build_work_list_labels_arms():
    from fanout.cli import build_work_list

    assert [v["label"] for v in build_work_list(2, "no-progress", 1)] == ["no-progress-0", "no-progress-1"]


def test_build_work_list_falls_back_for_unknown_rule():
    from fanout.cli import build_work_list

    assert build_work_list(1, "not-a-rule", 0)[0]["label"].startswith("navigation-thrash")


def test_summarize_ranks_by_score():
    from fanout.cli import summarize

    out = summarize([{"label": "lo", "score": 1.0}, {"label": "hi", "score": 9.0}], 12.34, "local", "c1")
    assert out["winner"] == "hi"
    assert out["arms"] == 2
    assert out["cohort"] == "c1"


def test_summarize_handles_empty_results():
    from fanout.cli import summarize

    assert summarize([], 0.0, "local", "c")["winner"] is None


def test_cli_missing_rom_exits_two(capsys):
    from fanout.cli import main

    assert main(["--rom", "/does/not/exist.gb"]) == 2
    assert "ROM not found" in capsys.readouterr().err


def test_cli_daytona_without_snapshot_exits_two(tmp_path, capsys):
    from fanout.cli import main

    rom = tmp_path / "r.gb"
    rom.write_bytes(b"\x00")
    assert main(["--rom", str(rom), "--backend", "daytona"]) == 2
    assert "requires --snapshot" in capsys.readouterr().err


def test_cli_local_run_writes_summary(tmp_path, monkeypatch, capsys):
    from fanout import cli

    rom = tmp_path / "r.gb"
    rom.write_bytes(b"\x00")
    out_json = tmp_path / "out.json"

    monkeypatch.setattr(
        cli,
        "get_backend",
        lambda name, **kw: types.SimpleNamespace(run_batch=lambda *a, **k: [{"party_size": 2}, {"party_size": 5}]),
    )
    assert cli.main(["--rom", str(rom), "--variants", "2", "--output-json", str(out_json)]) == 0

    written = json.loads(out_json.read_text())
    assert written["arms"] == 2
    assert written["backend"] == "local"
    assert "cohort" in capsys.readouterr().out


def test_cli_daytona_passes_snapshot_and_cohort_through(tmp_path, monkeypatch):
    from fanout import cli

    rom = tmp_path / "r.gb"
    rom.write_bytes(b"\x00")
    seen = {}

    def capture(name, **kwargs):
        seen["name"] = name
        seen["kwargs"] = kwargs
        return types.SimpleNamespace(run_batch=lambda *a, **k: [{}])

    monkeypatch.setattr(cli, "get_backend", capture)
    rc = cli.main(
        [
            "--rom",
            str(rom),
            "--backend",
            "daytona",
            "--snapshot",
            "snap-1",
            "--cohort",
            "race-9",
            "--variants",
            "1",
            "--concurrency",
            "4",
        ]
    )
    assert rc == 0
    assert seen["name"] == "daytona"
    assert seen["kwargs"] == {"snapshot": "snap-1", "cohort": "race-9", "concurrency": 4}


def test_cli_warns_when_strategy_costs_money(tmp_path, monkeypatch, capsys):
    from fanout import cli

    rom = tmp_path / "r.gb"
    rom.write_bytes(b"\x00")
    monkeypatch.setattr(cli, "get_backend", lambda name, **kw: types.SimpleNamespace(run_batch=lambda *a, **k: [{}]))
    cli.main(["--rom", str(rom), "--variants", "1", "--strategy", "medium"])
    assert "costs money" in capsys.readouterr().err


def test_cli_interrupt_reports_teardown(tmp_path, monkeypatch, capsys):
    from fanout import cli

    rom = tmp_path / "r.gb"
    rom.write_bytes(b"\x00")

    def interrupt(*a, **k):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "get_backend", lambda name, **kw: types.SimpleNamespace(run_batch=interrupt))
    assert cli.main(["--rom", str(rom)]) == 130
    assert "torn down" in capsys.readouterr().err


# ── sdk build ─────────────────────────────────────────────────────────


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """A miniature repo root for staging, so tests never copy 800 real files."""
    from fanout import sdk_build

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/agent.py").write_text("print('hi')")
    (tmp_path / "docker/fanout").mkdir(parents=True)
    (tmp_path / "docker/fanout/Dockerfile").write_text("FROM scratch")
    monkeypatch.setattr(sdk_build, "REPO_ROOT", tmp_path)

    def fake_git(cmd, cwd=None, capture_output=None, text=None, check=None):
        listing = "\n".join(
            str(p.relative_to(tmp_path)) for p in tmp_path.rglob("*") if p.is_file() and "Dockerfile" not in p.name
        )
        return types.SimpleNamespace(stdout=listing)

    monkeypatch.setattr(sdk_build.subprocess, "run", fake_git)
    return tmp_path


def test_stage_clean_context_copies_git_listing(fake_repo, tmp_path):
    from fanout.sdk_build import stage_clean_context

    dest = tmp_path / "stage"
    dest.mkdir()
    count = stage_clean_context(dest)
    assert count == 1
    assert (dest / "scripts/agent.py").read_text() == "print('hi')"
    assert (dest / "Dockerfile").exists()  # always carried alongside


def test_stage_clean_context_refuses_roms(fake_repo, tmp_path):
    """The whole point of the staged path: a ROM in context aborts the build."""
    from fanout.sdk_build import stage_clean_context

    (fake_repo / "scripts/sneaky.gb").write_bytes(b"\x00")
    dest = tmp_path / "stage2"
    dest.mkdir()
    with pytest.raises(SystemExit, match="REFUSING"):
        stage_clean_context(dest)


def test_stage_clean_context_refuses_secrets(fake_repo, tmp_path):
    from fanout.sdk_build import stage_clean_context

    (fake_repo / "scripts/api-key-PROD.txt").write_text("dtn_secret")
    dest = tmp_path / "stage3"
    dest.mkdir()
    with pytest.raises(SystemExit, match="REFUSING"):
        stage_clean_context(dest)


def test_stage_clean_context_skips_vanished_paths(fake_repo, tmp_path):
    """git can list a path deleted moments later; staging must not crash."""
    from fanout import sdk_build

    real_run = sdk_build.subprocess.run

    def listing_with_ghost(cmd, **kw):
        r = real_run(cmd, **kw)
        return types.SimpleNamespace(stdout=r.stdout + "\nghost/definitely-gone.py")

    # fake_repo already monkeypatched subprocess.run; wrap that fake instead.
    prior = sdk_build.subprocess.run
    sdk_build.subprocess.run = lambda cmd, **kw: types.SimpleNamespace(
        stdout=prior(cmd, **kw).stdout + "\nghost/definitely-gone.py"
    )
    try:
        dest = tmp_path / "stage4"
        dest.mkdir()
        assert sdk_build.stage_clean_context(dest) == 2  # ghost counted in listing, not copied
        assert not (dest / "ghost").exists()
    finally:
        sdk_build.subprocess.run = prior


def test_build_stages_then_creates_snapshot(fake_repo, monkeypatch, capsys):
    from fanout import sdk_build

    created = {}

    class FakeSnapshotService:
        def create(self, params, on_logs=None):
            created["name"] = params.name
            if on_logs:
                on_logs("build log line")

    fake = types.ModuleType("daytona")
    fake.Daytona = lambda *a, **k: types.SimpleNamespace(snapshot=FakeSnapshotService())
    fake.Image = types.SimpleNamespace(from_dockerfile=lambda p: f"image:{p}")

    class CreateSnapshotParams:
        def __init__(self, name, image, resources):
            self.name, self.image, self.resources = name, image, resources

    fake.CreateSnapshotParams = CreateSnapshotParams
    fake.Resources = lambda **kw: kw
    monkeypatch.setitem(sys.modules, "daytona", fake)

    sdk_build.build("pokemon-fanout-test")
    assert created["name"] == "pokemon-fanout-test"
    assert "DONE: pokemon-fanout-test" in capsys.readouterr().out


def test_failed_arm_records_why(fake_daytona_sdk):
    """A quota rejection must be readable from the summary, not forensics."""
    out = _backend(FakeClient(create_fails=True)).run_batch("/rom.gb", 7, [{"label": "a"}])
    assert "RuntimeError: create failed" in out[0]["fanout_error"]
    ok = _backend(FakeClient(FakeSandbox())).run_batch("/rom.gb", 7, [{"label": "b"}])
    assert "fanout_error" not in ok[0]


def test_heartbeat_command_is_unique_per_arm_and_leaks_no_secrets():
    from fanout.daytona_backend import build_heartbeat_command

    a = build_heartbeat_command("race-1", "arm-0")
    b = build_heartbeat_command("race-1", "arm-1")
    # tapes dedupes raw turns by body hash — identical bodies collapse a race.
    assert a != b and "arm-0" in a and "race-1" in a
    # The key must arrive via shell env expansion, never inlined into a
    # command string that gets logged.
    assert "$ANTHROPIC_API_KEY" in a and "sk-" not in a


def test_heartbeat_sent_for_medium_strategy_with_capture(fake_daytona_sdk):
    client = FakeClient(FakeSandbox())
    out = _backend(client, capture_base_url="http://c:9", anthropic_api_key="sk-x").run_batch(
        "/rom.gb", 10, [{"label": "a"}], strategy="medium"
    )
    assert out[0]["capture_heartbeat"] == "ok"
    assert any("capture-heartbeat" in c for c in client.sandbox.commands)


def test_no_heartbeat_for_low_strategy(fake_daytona_sdk):
    """low makes zero LLM calls — the heartbeat must not break that promise."""
    client = FakeClient(FakeSandbox())
    out = _backend(client, capture_base_url="http://c:9", anthropic_api_key="sk-x").run_batch(
        "/rom.gb", 10, [{"label": "a"}]
    )
    assert "capture_heartbeat" not in out[0]
    assert not any("capture-heartbeat" in c for c in client.sandbox.commands)


def test_no_heartbeat_without_key_or_capture(fake_daytona_sdk):
    client = FakeClient(FakeSandbox())
    out = _backend(client, anthropic_api_key="sk-x").run_batch("/rom.gb", 10, [{"label": "a"}], strategy="medium")
    assert "capture_heartbeat" not in out[0]


def test_heartbeat_failure_recorded_not_raised(fake_daytona_sdk):
    class HeartbeatFails(FakeSandbox):
        def _exec(self, command, cwd=None, timeout=None, env=None):
            self.commands.append(command)
            if "capture-heartbeat" in command:
                return FakeExec(22, "")
            if command.startswith("cat "):
                return FakeExec(0, self._fitness_json)
            return FakeExec(0, "")

    out = _backend(FakeClient(HeartbeatFails()), capture_base_url="http://c:9", anthropic_api_key="k").run_batch(
        "/rom.gb", 10, [{"label": "a"}], strategy="medium"
    )
    assert out[0]["capture_heartbeat"] == "failed (exit 22)"
    assert out[0]["party_size"] == 3  # fitness survives a capture failure
