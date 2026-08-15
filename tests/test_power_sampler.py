import power_sampler


def test_read_gpu_watts_parses_nvidia_smi(monkeypatch):
    monkeypatch.setattr(power_sampler, "_run", lambda cmd: "123.4\n")
    assert power_sampler.read_gpu_watts() == 123.4


def test_read_gpu_watts_returns_none_when_unavailable(monkeypatch):
    def boom(cmd):
        raise OSError("no nvidia-smi")

    monkeypatch.setattr(power_sampler, "_run", boom)
    assert power_sampler.read_gpu_watts() is None
    monkeypatch.setattr(power_sampler, "_run", lambda cmd: "N/A\n")
    assert power_sampler.read_gpu_watts() is None


def test_read_hwmon_watts_sums_amdgpu_microwatts(tmp_path):
    h = tmp_path / "hwmon0"
    h.mkdir()
    (h / "name").write_text("amdgpu\n")
    (h / "power1_input").write_text("8000000\n")  # 8 W in microwatts
    other = tmp_path / "hwmon1"
    other.mkdir()
    (other / "name").write_text("nvme\n")
    (other / "power1_input").write_text("999999999\n")
    assert power_sampler.read_hwmon_watts(tmp_path) == 8.0


def test_read_rapl_joules_handles_permission(tmp_path):
    d = tmp_path / "intel-rapl:0"
    d.mkdir()
    (d / "energy_uj").write_text("5000000\n")  # 5 J
    assert power_sampler.read_rapl_joules(tmp_path) == 5.0
    (d / "energy_uj").chmod(0o000)
    try:
        assert power_sampler.read_rapl_joules(tmp_path) is None
    finally:
        (d / "energy_uj").chmod(0o644)
    assert power_sampler.read_rapl_joules(tmp_path / "nope") is None


def test_sample_loop_writes_csv_and_stops(tmp_path, monkeypatch):
    out = tmp_path / "power.csv"
    ticks = iter([0.0, 5.0, 10.0])
    monkeypatch.setattr(power_sampler, "read_gpu_watts", lambda: 300.0)
    monkeypatch.setattr(power_sampler, "read_hwmon_watts", lambda root=None: 8.0)
    joules = iter([100.0, 150.0, 250.0])
    monkeypatch.setattr(power_sampler, "read_rapl_joules", lambda root=None: next(joules))
    monkeypatch.setattr(power_sampler.time, "sleep", lambda s: None)
    n = power_sampler.sample_loop(out, interval=5.0, max_samples=3, clock=lambda: next(ticks))
    assert n == 3
    lines = out.read_text().splitlines()
    assert lines[0] == "ts,gpu_w,other_w,cpu_w"
    # cpu_w from RAPL deltas: (150-100)/5 = 10 W, (250-150)/5 = 20 W; first sample has no delta
    assert lines[1] == "0.0,300.0,8.0,"
    assert lines[2] == "5.0,300.0,8.0,10.0"
    assert lines[3] == "10.0,300.0,8.0,20.0"


def test_sample_loop_blank_when_sensors_missing(tmp_path, monkeypatch):
    out = tmp_path / "p.csv"
    monkeypatch.setattr(power_sampler, "read_gpu_watts", lambda: None)
    monkeypatch.setattr(power_sampler, "read_hwmon_watts", lambda root=None: None)
    monkeypatch.setattr(power_sampler, "read_rapl_joules", lambda root=None: None)
    monkeypatch.setattr(power_sampler.time, "sleep", lambda s: None)
    t = iter([1.0, 2.0])
    assert power_sampler.sample_loop(out, interval=1.0, max_samples=2, clock=lambda: next(t)) == 2
    assert out.read_text().splitlines()[1] == "1.0,,,"


def test_main_runs_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(power_sampler, "sample_loop", lambda out, interval, max_samples, clock=None: 4)
    assert power_sampler.main(["--out", str(tmp_path / "x.csv"), "--interval", "1", "--max-samples", "4"]) == 0


def test_run_invokes_subprocess(monkeypatch):
    class P:
        stdout = "42.0\n"

    monkeypatch.setattr(power_sampler.subprocess, "run", lambda cmd, **kw: P())
    assert power_sampler._run(["x"]) == "42.0\n"


def test_read_hwmon_watts_skips_unreadable_and_non_amdgpu(tmp_path):
    h = tmp_path / "hwmon0"
    h.mkdir()
    (h / "name").write_text("amdgpu\n")  # no power1_input -> OSError branch
    assert power_sampler.read_hwmon_watts(tmp_path) is None
    bad = tmp_path / "hwmon1"
    bad.mkdir()
    (bad / "name").write_text("amdgpu\n")
    (bad / "power1_input").write_text("garbage\n")  # ValueError branch
    assert power_sampler.read_hwmon_watts(tmp_path) is None
