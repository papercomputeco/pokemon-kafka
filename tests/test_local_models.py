import json

import local_models as lm
import pytest


def test_roster_aliases_unique_and_variant_names():
    aliases = [s.alias for s in lm.ROSTER]
    assert len(aliases) == len(set(aliases))
    assert lm.variant_name(lm.BY_ALIAS["glm47-flash"], 131072) == "glm47-flash-128k"


def test_every_spec_has_a_known_group():
    assert {s.group for s in lm.ROSTER} <= set(lm.GROUPS)


def test_pick_accepts_groups_and_aliases_and_rejects_junk():
    moe = lm._pick(["moe-30b"])
    assert moe and all(s.group == "moe-30b" for s in moe)
    assert [s.alias for s in lm._pick(["gemma4-31b"])] == ["gemma4-31b"]
    assert len(lm._pick([])) == len(lm.ROSTER)
    with pytest.raises(SystemExit):
        lm._pick(["not-a-model"])


def test_by_group_orders_by_groups_dict_and_drops_empties():
    got = lm._by_group([lm.BY_ALIAS["gemma4"], lm.BY_ALIAS["gpt-oss-20b"]])
    assert [g for g, _ in got] == ["moe-30b", "baseline"]


def test_modelfile_sets_ctx():
    mf = lm.modelfile(lm.BY_ALIAS["gpt-oss-20b"], 131072)
    assert mf.splitlines() == ["FROM gpt-oss:20b", "PARAMETER num_ctx 131072"]


def test_register_is_idempotent(tmp_path):
    mj = tmp_path / "models.json"
    mj.write_text(json.dumps({"providers": {"ollama": {"models": [{"id": "kimi-k2.6:cloud"}]}}}))
    specs = [lm.BY_ALIAS["gemma4-31b"], lm.BY_ALIAS["gpt-oss-20b"]]
    assert lm.register(mj, specs, 131072) == ["gemma4-31b-128k", "gpt-oss-20b-128k"]
    assert lm.register(mj, specs, 131072) == []
    models = json.loads(mj.read_text())["providers"]["ollama"]["models"]
    by_id = {m["id"]: m for m in models}
    assert by_id["gemma4-31b-128k"]["input"] == ["text", "image"]
    assert by_id["gpt-oss-20b-128k"]["reasoning"] is True
    assert by_id["kimi-k2.6:cloud"] == {"id": "kimi-k2.6:cloud"}


def test_gpu_split_and_bench_row_flags_spill():
    assert lm.gpu_split({"size": 100, "size_vram": 50}) == (0.5, 100)
    row = {
        "model": "x-64k",
        "out_tok_s": 10.0,
        "prompt_tok_s": 100.0,
        "gpu_frac": 0.5,
        "size_gb": 20.0,
        "peak_w": 400.0,
        "mean_w": 300.2,
        "load_s": 3.0,
    }
    assert "**CPU spill**" in lm.bench_row(row)
    assert "error" in lm.bench_row({"model": "y", "error": "boom"})


def test_same_model_ignores_latest_tag():
    assert lm._same_model("glm47-flash-128k:latest", "glm47-flash-128k")
    assert not lm._same_model("glm47-flash-64k:latest", "glm47-flash-128k")


def test_roster_is_blackwell_runnable():
    assert [s.alias for s in lm.ROSTER if lm.check_runnable(s.tag)] == []


def test_check_runnable_flags_macos_only_formats():
    assert lm.check_runnable("qwen3.8:27b-nvfp4")
    assert lm.check_runnable("muse-glimmer:30b-mlx-bf16")
    assert lm.check_runnable("qwen3.8:27b") is None
    assert lm.check_runnable("gpt-oss:20b") is None


def test_qwen3_coder_is_retired_not_rostered():
    assert "qwen3-coder-30b" not in lm.BY_ALIAS
    assert "qwen3-coder-30b" in lm.RETIRED
    with pytest.raises(SystemExit) as ex:
        lm._pick(["qwen3-coder-30b"])
    assert "retired" in str(ex.value)


# ---------------------------------------------------------------- CLI paths, with Ollama and subprocess faked


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return json.dumps(self._payload).encode()


def _fake_ollama(monkeypatch, *, tags=(), ps=(), generate=None, fail=False):
    """Route local_models._api's urlopen to canned answers by path."""

    def urlopen(req, timeout=0):
        if fail:
            raise OSError("connection refused")
        url = req.full_url if hasattr(req, "full_url") else req
        if url.endswith("/api/tags"):
            return _Resp({"models": [{"name": n} for n in tags]})
        if url.endswith("/api/ps"):
            return _Resp({"models": list(ps)})
        if url.endswith("/api/generate"):
            return _Resp(generate or {})
        raise AssertionError(url)

    monkeypatch.setattr(lm.urllib.request, "urlopen", urlopen)


def test_installed_models_and_ps_survive_a_dead_ollama(monkeypatch):
    _fake_ollama(monkeypatch, fail=True)
    assert lm.installed_models() == set()
    assert lm.ollama_ps() == []


def test_has_accepts_implicit_latest():
    assert lm._has("x-128k", {"x-128k:latest"})
    assert not lm._has("y", {"x-128k:latest"})


def test_power_sampler_reads_nvidia_smi(monkeypatch):
    calls = iter(["300.5\n", "310.5\n", "garbage\n"])

    class R:
        def __init__(self, out):
            self.stdout = out

    monkeypatch.setattr(lm.subprocess, "run", lambda *a, **k: R(next(calls, "")))
    s = lm.PowerSampler(interval=0.01)
    s.start()
    s._halt.wait(0.05)
    peak, mean = s.stop()
    assert peak == 310.5 and 300 < mean <= 310.5


def test_power_sampler_with_no_samples_returns_none(monkeypatch):
    monkeypatch.setattr(lm.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no nvidia-smi")))
    s = lm.PowerSampler(interval=0.01)
    s.start()
    assert s.stop() == (None, None)


def test_bench_one_reports_gpu_split_and_speeds(monkeypatch):
    monkeypatch.setattr(
        lm, "PowerSampler", lambda: type("S", (), {"start": lambda s: None, "stop": lambda s: (400.0, 350.0)})()
    )
    _fake_ollama(
        monkeypatch,
        ps=[{"name": "m-128k:latest", "size": 100, "size_vram": 100}],
        generate={
            "eval_count": 400,
            "eval_duration": 2e9,
            "prompt_eval_count": 50,
            "prompt_eval_duration": 1e8,
            "load_duration": 5e8,
        },
    )
    r = lm.bench_one("m-128k", 131072)
    assert r["out_tok_s"] == 200.0 and r["prompt_tok_s"] == 500.0 and r["gpu_frac"] == 1.0
    assert r["peak_w"] == 400.0 and "error" not in r
    assert "CPU spill" not in lm.bench_row(r)


def test_bench_one_returns_error_row_when_ollama_is_down(monkeypatch):
    monkeypatch.setattr(
        lm, "PowerSampler", lambda: type("S", (), {"start": lambda s: None, "stop": lambda s: (None, None)})()
    )
    _fake_ollama(monkeypatch, fail=True)
    r = lm.bench_one("m-128k", 131072)
    assert "error" in r and "error" in lm.bench_row(r)


def test_cmd_list_prints_retired_and_groups(monkeypatch, capsys):
    _fake_ollama(monkeypatch, tags=["gpt-oss:20b", "gpt-oss-20b-128k:latest"])
    assert lm.main(["list"]) == 0
    out = capsys.readouterr().out
    assert "### retired" in out and "qwen3-coder-30b" in out
    assert "| gpt-oss-20b | `gpt-oss:20b` | yes | yes |" in out
    assert lm.main(["list", "moe-30b"]) == 0
    assert "### retired" not in capsys.readouterr().out


def test_cmd_pull_skips_macos_only_and_reports_failures(monkeypatch, capsys):
    calls = []

    class R:
        def __init__(self, rc):
            self.returncode = rc

    monkeypatch.setattr(
        lm.subprocess, "run", lambda cmd, **k: (calls.append(cmd), R(1 if "gpt-oss" in cmd[-1] else 0))[1]
    )
    monkeypatch.setattr(lm, "ROSTER", lm.ROSTER + (lm.Spec("fake-fp4", "fake:30b-nvfp4", "moe-30b", "test"),))
    monkeypatch.setattr(lm, "BY_ALIAS", {s.alias: s for s in lm.ROSTER})
    rc = lm.main(["pull", "gpt-oss-20b", "glm47-flash", "fake-fp4"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "skip fake-fp4" in out and "macOS-only" in out
    assert "FAILED (1)" in out
    assert ["ollama", "pull", "glm-4.7-flash"] in calls
    assert not any("nvfp4" in c[-1] for c in calls)


def test_cmd_create_writes_a_modelfile_and_skips_unpulled(monkeypatch, capsys, tmp_path):
    seen = {}

    class R:
        returncode = 0

    def run(cmd, **k):
        seen["cmd"] = cmd
        seen["modelfile"] = open(cmd[-1]).read()
        return R()

    monkeypatch.setattr(lm.subprocess, "run", run)
    _fake_ollama(monkeypatch, tags=["gpt-oss:20b"])
    assert lm.main(["create", "gpt-oss-20b", "glm47-flash"]) == 0
    out = capsys.readouterr().out
    assert seen["cmd"][:3] == ["ollama", "create", "gpt-oss-20b-128k"]
    assert seen["modelfile"] == "FROM gpt-oss:20b\nPARAMETER num_ctx 131072\n"
    assert "skip glm47-flash" in out
    assert not lm.Path(seen["cmd"][-1]).exists()  # temp Modelfile cleaned up


def test_cmd_register_only_registers_created_variants(monkeypatch, capsys, tmp_path):
    mj = tmp_path / "models.json"
    monkeypatch.setattr(lm, "PI_MODELS_JSON", mj)
    _fake_ollama(monkeypatch, tags=["gpt-oss-20b-128k:latest"])
    assert lm.main(["register"]) == 0
    assert "registered 1 new model(s)" in capsys.readouterr().out
    assert [m["id"] for m in json.loads(mj.read_text())["providers"]["ollama"]["models"]] == ["gpt-oss-20b-128k"]


def test_cmd_bench_prints_target_row_and_skips_uncreated(monkeypatch, capsys):
    _fake_ollama(monkeypatch, tags=["gpt-oss-20b-128k:latest"])
    monkeypatch.setattr(
        lm,
        "bench_one",
        lambda model, ctx: {
            "model": model,
            "wall_s": 1.0,
            "load_s": 0.1,
            "out_tok": 400,
            "out_tok_s": 250.0,
            "prompt_tok_s": 9000.0,
            "gpu_frac": 1.0,
            "size_gb": 14.0,
            "peak_w": 480.0,
            "mean_w": 440.0,
        },
    )
    assert lm.main(["bench", "moe-30b", "--repeat", "1"]) == 0
    out = capsys.readouterr().out
    assert "Haiku 4.5 (target)" in out
    assert "| gpt-oss-20b-128k | 250.0 |" in out
    assert "| glm47-flash-128k | not created |" in out


def test_modelfile_includes_extra_params():
    spec = lm.Spec("x", "x:1b", "moe-30b", "t", params={"temperature": 0.7})
    assert "PARAMETER temperature 0.7" in lm.modelfile(spec, 65536)
