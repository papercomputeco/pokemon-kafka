"""The box-wide emulator budget: the fix for self-heal subloops saturating the machine."""

import multiprocessing as mp
import os

import emulator_slots as slots


def test_slot_count_reserves_cores_and_honours_the_env(monkeypatch):
    monkeypatch.delenv("POKEMON_EMULATOR_SLOTS", raising=False)
    assert slots.slot_count(cpus=32) == 30
    assert slots.slot_count(cpus=2) == 1, "never zero"
    monkeypatch.setenv("POKEMON_EMULATOR_SLOTS", "4")
    assert slots.slot_count(cpus=32) == 4


def test_acquire_hands_out_distinct_slots_and_refuses_when_full(tmp_path):
    a = slots.acquire(wait_s=0, slots_dir=tmp_path, count=2)
    b = slots.acquire(wait_s=0, slots_dir=tmp_path, count=2)
    assert a is not None and b is not None and a.index != b.index
    assert slots.busy(slots_dir=tmp_path, count=2) == 2
    assert slots.acquire(wait_s=0, slots_dir=tmp_path, count=2) is None, "a full box refuses a no-wait caller"
    a.release()
    assert slots.busy(slots_dir=tmp_path, count=2) == 1
    c = slots.acquire(wait_s=0, slots_dir=tmp_path, count=2)
    assert c is not None and c.index == a.index


def test_acquire_waits_and_logs_then_gives_up(tmp_path):
    held = slots.acquire(wait_s=0, slots_dir=tmp_path, count=1)
    assert held is not None
    t = [0.0]
    lines = []
    got = slots.acquire(
        wait_s=100,
        slots_dir=tmp_path,
        count=1,
        log=lines.append,
        poll_s=10,
        clock=lambda: t[0],
        sleep=lambda s: t.__setitem__(0, t[0] + s),
    )
    assert got is None
    assert lines and "waiting" in lines[0], "a queued lane must read as queued in its log, not as hung"


def _hold_then_die(slots_dir):
    s = slots.acquire(wait_s=0, slots_dir=slots_dir, count=1)
    (slots_dir / "held").write_text("1" if s else "0")
    os._exit(0)  # die without releasing — the kernel must drop the flock for us


def test_a_dead_holder_frees_its_slot_without_cleanup(tmp_path):
    """The whole reason for flock over pid files: no stale state when a lane is SIGKILLed."""
    ctx = mp.get_context("fork")
    p = ctx.Process(target=_hold_then_die, args=(tmp_path,))
    p.start()
    p.join(timeout=10)
    assert (tmp_path / "held").read_text() == "1"
    assert slots.busy(slots_dir=tmp_path, count=1) == 0
    assert slots.acquire(wait_s=0, slots_dir=tmp_path, count=1) is not None


def _race_claim(slots_dir, q, barrier):
    barrier.wait()
    s = slots.acquire(wait_s=0, slots_dir=slots_dir, count=3)
    q.put(s.index if s else None)
    if s:
        while not (slots_dir / "release").exists():  # hold until the parent has counted
            import time as _t

            _t.sleep(0.02)


def test_concurrent_claimants_never_share_a_slot(tmp_path):
    ctx = mp.get_context("fork")
    q = ctx.Queue()
    barrier = ctx.Barrier(8)
    procs = [ctx.Process(target=_race_claim, args=(tmp_path, q, barrier)) for _ in range(8)]
    for p in procs:
        p.start()
    got = [q.get(timeout=30) for _ in range(8)]
    (tmp_path / "release").write_text("")
    won = [g for g in got if g is not None]
    assert len(won) == 3, f"3 slots -> exactly 3 winners, got {len(won)}"
    assert len(set(won)) == 3, f"winners must hold distinct slots, got {won}"
    for p in procs:
        p.join(timeout=10)
