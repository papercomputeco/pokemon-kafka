"""Tests for the on-demand Daytona Ollama host.

Same philosophy as test_fanout.py: the SDK is faked because the behavior most
worth testing — teardown on failure, refusing double-up, state hygiene — is
exactly what should never be exercised against billable infrastructure.
"""

from __future__ import annotations

import json
import sys
import types

import pytest
from fanout import ollama_host


class FakeExec:
    def __init__(self, exit_code=0, result=""):
        self.exit_code = exit_code
        self.result = result


class FakeSandbox:
    def __init__(self, fail_on=None, warm_answer="COLD", copy_polls=("0",)):
        self.id = "gpu-sb-1"
        self.commands = []
        self._fail_on = fail_on or ()
        self.warm_answer = warm_answer
        self.copy_polls = iter(copy_polls)

    def _exec(self, command, timeout=None):
        self.commands.append(command)
        if any(marker in command for marker in self._fail_on):
            return FakeExec(1, "boom")
        if "echo WARM || echo COLD" in command:
            return FakeExec(0, self.warm_answer)
        if command.startswith("cat /tmp/cp.rc"):
            return FakeExec(0, next(self.copy_polls, "0"))
        return FakeExec(0, "ok")

    @property
    def process(self):
        return types.SimpleNamespace(exec=self._exec)

    def get_preview_link(self, port):
        return types.SimpleNamespace(url=f"https://{port}-{self.id}.daytonaproxy.example")


class FakeVolumeService:
    def __init__(self):
        self.requested = []

    def get(self, name, create=False):
        self.requested.append((name, create))
        return types.SimpleNamespace(id=f"vol-{name}", state="ready")


class FakeClient:
    def __init__(self, sandbox=None):
        self.sandbox = sandbox or FakeSandbox()
        self.created = []
        self.deleted = []
        self.volume = FakeVolumeService()

    def create(self, params, timeout=None):
        self.created.append(params)
        return self.sandbox

    def get(self, sandbox_id):
        return types.SimpleNamespace(id=sandbox_id)

    def delete(self, sandbox):
        self.deleted.append(getattr(sandbox, "id", sandbox))


@pytest.fixture
def fake_sdk(monkeypatch, tmp_path):
    module = types.ModuleType("daytona")

    class CreateSandboxFromSnapshotParams:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    module.CreateSandboxFromSnapshotParams = CreateSandboxFromSnapshotParams

    class VolumeMount:
        def __init__(self, volume_id, mount_path, subpath=None):
            self.volume_id, self.mount_path = volume_id, mount_path

    module.VolumeMount = VolumeMount
    module.Daytona = lambda *a, **k: FakeClient()
    monkeypatch.setitem(sys.modules, "daytona", module)
    monkeypatch.setattr(ollama_host, "STATE_FILE", tmp_path / "host.json")
    return module


def test_resolve_models_maps_roster_aliases():
    tags = ollama_host.resolve_models(["qwen38-27b"])
    assert len(tags) == 1 and tags[0]  # real roster tag, whatever it currently is


def test_resolve_models_rejects_unknown_alias():
    with pytest.raises(SystemExit, match="unknown roster alias"):
        ollama_host.resolve_models(["definitely-not-a-model"])


def test_up_boots_pulls_and_saves_state(fake_sdk, capsys):
    client = FakeClient()
    url = ollama_host.up(["qwen38-27b"], ttl_minutes=90, client=client)

    assert url.startswith("https://11434-gpu-sb-1")
    kwargs = client.created[0].kwargs
    assert kwargs["snapshot"] == "daytona-gpu"
    assert kwargs["public"] is True  # plain OLLAMA_HOST_URL consumers, no headers
    assert kwargs["ephemeral"] is True and kwargs["ttl_minutes"] == 90
    assert "ollama pull " in "\n".join(client.sandbox.commands)
    state = json.loads(ollama_host.STATE_FILE.read_text())
    assert state["sandbox_id"] == "gpu-sb-1" and state["url"] == url
    assert capsys.readouterr().out.strip() == url  # stdout is ONLY the url — scriptable


def test_up_refuses_second_host(fake_sdk):
    ollama_host.save_state("gpu-sb-0", "https://old")
    with pytest.raises(SystemExit, match="already up"):
        ollama_host.up(["qwen38-27b"], client=FakeClient())


def test_up_tears_down_on_setup_failure(fake_sdk):
    """A half-built host must not survive to bill idle."""
    client = FakeClient(FakeSandbox(fail_on=("install.sh",)))
    with pytest.raises(SystemExit, match="install failed"):
        ollama_host.up(["qwen38-27b"], client=client)
    assert client.deleted == ["gpu-sb-1"]
    assert ollama_host.load_state() is None  # no state for a host that never was


def test_up_tears_down_on_pull_failure(fake_sdk):
    client = FakeClient(FakeSandbox(fail_on=("ollama pull",)))  # fails the provision script
    with pytest.raises(SystemExit, match="pull .* failed"):
        ollama_host.up(["qwen38-27b"], client=client)
    assert client.deleted == ["gpu-sb-1"]


def test_down_deletes_and_clears_state(fake_sdk, capsys):
    ollama_host.save_state("gpu-sb-7", "https://x")
    client = FakeClient()
    assert ollama_host.down(client=client) == 0
    assert client.deleted == ["gpu-sb-7"]
    assert ollama_host.load_state() is None


def test_down_without_state_is_a_noop(fake_sdk):
    assert ollama_host.down(client=FakeClient()) == 0


def test_down_tolerates_already_reaped_sandbox(fake_sdk):
    """TTL may have beaten us to it; that is success, and state still clears."""

    class GoneClient(FakeClient):
        def get(self, sandbox_id):
            raise RuntimeError("not found")

    ollama_host.save_state("gpu-sb-9", "https://x")
    assert ollama_host.down(client=GoneClient()) == 0
    assert ollama_host.load_state() is None


def test_cli_up_and_down(fake_sdk, monkeypatch):
    calls = {}
    monkeypatch.setattr(
        ollama_host, "up", lambda aliases, ttl_minutes, volume: calls.setdefault("up", (aliases, ttl_minutes))
    )
    monkeypatch.setattr(ollama_host, "down", lambda: calls.setdefault("down", True) and 0)
    assert ollama_host.main(["up", "--models", "qwen38-27b, gemma4", "--ttl", "45"]) == 0
    assert calls["up"] == (["qwen38-27b", "gemma4"], 45)
    assert ollama_host.main(["down"]) == 0
    assert calls["down"] is True


def test_resolve_models_includes_daytona_tier():
    """H100-only models (too big for the local card) resolve on the host."""
    assert ollama_host.resolve_models(["gpt-oss-120b"]) == ["gpt-oss:120b"]
    # gpt-oss-120b is the tier's only model by decision (2026-08-25):
    # qwen coverage stays local via qwen38-27b.
    from local_models import DAYTONA_BY_ALIAS

    assert list(DAYTONA_BY_ALIAS) == ["gpt-oss-120b"]


def test_retired_models_are_gone():
    with pytest.raises(SystemExit, match="unknown roster alias"):
        ollama_host.resolve_models(["qwen35b"])


def test_up_mounts_the_weights_volume_when_opted_in(fake_sdk):
    """The volume is opt-in: measured FUSE reads (75-78 MB/s, parallel or not)
    are slower than a registry pull, so it exists for registry independence,
    not speed."""
    client = FakeClient()
    ollama_host.up(["gpt-oss-120b"], volume="fanout-ollama-models", client=client)
    assert client.volume.requested == [("fanout-ollama-models", True)]
    kwargs = client.created[0].kwargs
    assert kwargs["volumes"][0].volume_id == "vol-fanout-ollama-models"
    assert kwargs["volumes"][0].mount_path == "/models"
    assert any("OLLAMA_MODELS=/models" in c for c in client.sandbox.commands)


def test_up_without_volume_is_the_default(fake_sdk):
    client = FakeClient()
    ollama_host.up(["gpt-oss-120b"], client=client)
    assert client.volume.requested == []
    assert client.created[0].kwargs["volumes"] is None
    assert any("OLLAMA_MODELS=$HOME/.ollama/models" in c for c in client.sandbox.commands)


def test_cli_passes_volume_through(fake_sdk, monkeypatch):
    seen = {}
    monkeypatch.setattr(ollama_host, "up", lambda aliases, ttl_minutes, volume: seen.update(v=volume))
    ollama_host.main(["up", "--models", "gpt-oss-120b", "--volume", "my-weights"])
    assert seen["v"] == "my-weights"


def test_up_waits_for_a_pending_volume(fake_sdk, monkeypatch):
    """A fresh volume is pending_create for a few seconds; sandbox creation
    rejects it until ready, so up() must wait — observed live 2026-08-25."""
    monkeypatch.setattr(ollama_host.time, "sleep", lambda s: None)

    class SlowVolumeService(FakeVolumeService):
        def __init__(self):
            super().__init__()
            self.states = iter(["pending_create", "creating", "ready"])

        def get(self, name, create=False):
            self.requested.append((name, create))
            return types.SimpleNamespace(id=f"vol-{name}", state=next(self.states))

    client = FakeClient()
    client.volume = SlowVolumeService()
    ollama_host.up(["gpt-oss-120b"], volume="fanout-ollama-models", client=client)
    assert len(client.volume.requested) == 3  # initial create + two re-polls


def test_up_gives_up_on_a_stuck_volume(fake_sdk, monkeypatch):
    monkeypatch.setattr(ollama_host.time, "sleep", lambda s: None)
    clock = iter([0, 0, 500])  # deadline math: start, first check, past deadline
    monkeypatch.setattr(ollama_host.time, "time", lambda: next(clock))

    class StuckVolumeService(FakeVolumeService):
        def get(self, name, create=False):
            return types.SimpleNamespace(id="v", state="error")

    client = FakeClient()
    client.volume = StuckVolumeService()
    with pytest.raises(SystemExit, match="never became ready"):
        ollama_host.up(["gpt-oss-120b"], volume="fanout-ollama-models", client=client)


def test_cold_volume_flow_pulls_local_then_copies_then_serves_volume(fake_sdk, monkeypatch):
    """The FUSE volume cannot take ollama's partial writes and a silent
    25-minute exec died mid-copy (both live, 2026-08-25) — so the flow is:
    serve local -> pull -> stop -> detached copy + short polls -> serve volume."""
    monkeypatch.setattr(ollama_host.time, "sleep", lambda s: None)
    sandbox = FakeSandbox(warm_answer="COLD", copy_polls=("RUNNING", "RUNNING", "0"))
    client = FakeClient(sandbox)
    ollama_host.up(["gpt-oss-120b"], volume="fanout-ollama-models", client=client)

    joined = "\n---\n".join(sandbox.commands)
    order = [
        joined.index(m)
        for m in (
            "OLLAMA_MODELS=$HOME/.ollama/models",  # pull happens against local disk
            "ollama pull gpt-oss:120b",
            "pkill -x ollama",
            "cp -an $HOME/.ollama/models/. /models/",
            "cat /tmp/cp.rc",
            "OLLAMA_MODELS=/models",  # final serve reads from the volume
        )
    ]
    assert order == sorted(order), f"stages out of order:\n{joined}"
    assert sum(1 for c in sandbox.commands if c.startswith("cat /tmp/cp.rc")) == 3


def test_warm_volume_flow_serves_immediately(fake_sdk):
    sandbox = FakeSandbox(warm_answer="WARM")
    ollama_host.up(["gpt-oss-120b"], volume="fanout-ollama-models", client=FakeClient(sandbox))
    joined = "\n".join(sandbox.commands)
    assert "ollama pull" not in joined
    assert "cp -an" not in joined
    assert "OLLAMA_MODELS=/models" in joined


def test_copy_failure_tears_down(fake_sdk, monkeypatch):
    monkeypatch.setattr(ollama_host.time, "sleep", lambda s: None)
    sandbox = FakeSandbox(copy_polls=("RUNNING", "1"))
    client = FakeClient(sandbox)
    with pytest.raises(SystemExit, match="store copy failed"):
        ollama_host.up(["gpt-oss-120b"], volume="fanout-ollama-models", client=client)
    assert client.deleted == ["gpu-sb-1"]


def test_copy_timeout_tears_down(fake_sdk, monkeypatch):
    monkeypatch.setattr(ollama_host.time, "sleep", lambda s: None)
    clock = iter([0] * 6 + [10_000] * 10)
    monkeypatch.setattr(ollama_host.time, "time", lambda: next(clock))
    sandbox = FakeSandbox(copy_polls=iter(lambda: "RUNNING", None))
    client = FakeClient(sandbox)
    with pytest.raises(SystemExit, match="copy timed out"):
        ollama_host.up(["gpt-oss-120b"], volume="fanout-ollama-models", client=client)
    assert client.deleted == ["gpu-sb-1"]


def test_no_volume_flow_stays_on_local_store(fake_sdk):
    sandbox = FakeSandbox()
    ollama_host.up(["gpt-oss-120b"], client=FakeClient(sandbox))
    joined = "\n".join(sandbox.commands)
    assert "OLLAMA_MODELS=$HOME/.ollama/models" in joined
    assert "OLLAMA_MODELS=/models" not in joined
    assert "echo WARM" not in joined  # no volume, no warm check


def test_copy_start_command_is_detached_and_clears_partials():
    from fanout.ollama_host import copy_start_command

    cmd = copy_start_command(["gpt-oss:120b"])
    assert cmd.rstrip().endswith("&")  # detached: the exec returns immediately
    assert "/tmp/cp.rc" in cmd  # exit code parked for the poller
    assert "*partial*" in cmd  # stale junk from failed direct pulls removed
    assert "touch /models/.pulled-gpt-oss-120b" in cmd
