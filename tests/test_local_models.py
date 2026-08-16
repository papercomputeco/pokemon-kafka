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
