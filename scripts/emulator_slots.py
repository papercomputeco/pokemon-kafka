"""Box-wide emulator budget: every headless PyBoy on the machine draws from one pool of slots.

Why a pool and not a lock. The relay caps *its own* lanes at 6, but emulators come from three
places at once — relay lanes, each lane's self-heal subloop lanes, and leftovers from a previous
worktree's run — and no caller-side lock can see all three. Unbudgeted, one 2 h benchmark reached
238 emulators on 32 cores. Starved lanes still finish and still write fitness.json; they just report
an unchanged position and a high stuck_count, which is byte-identical to a real navigation wall.
The model then "fixes" navigation. Budgeting the resource makes that impossible: a lane either has
a core or is visibly waiting for one.

Mechanism: N slot files under one shared directory, claimed with fcntl.flock(LOCK_EX | LOCK_NB).
flock is atomic across processes and the kernel drops it when the holder dies, so there is no stale
state to detect and no create-then-write window to race — both of which the first attempt at this
(a pid file) got wrong.

Priority: a main lane blocks for a slot (`wait_s` > 0) and logs while it waits. A subloop lane
asks with `wait_s=0` and, if the box is full, skips that heal — self-healing degrades under load
instead of causing it.
"""

from __future__ import annotations

import fcntl
import os
import time
from pathlib import Path

DEFAULT_DIR = Path(os.environ.get("POKEMON_SLOTS_DIR", "/tmp/pokemon-kafka-slots"))
RESERVED_CORES = 2


def slot_count(cpus=None):
    """Emulators the box can run at ~30 turns/s each: one per core, two cores kept for everything else."""
    env = os.environ.get("POKEMON_EMULATOR_SLOTS")
    if env:
        return max(1, int(env))
    cpus = cpus or os.cpu_count() or 4
    return max(1, cpus - RESERVED_CORES)


class Slot:
    """A held emulator slot. Release explicitly, or let process exit drop the flock."""

    def __init__(self, index, fd):
        self.index = index
        self._fd = fd

    def release(self):
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None


def _try_claim(path):
    fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd


def acquire(wait_s=0.0, slots_dir=None, count=None, log=None, poll_s=1.0, clock=time.monotonic, sleep=time.sleep):
    """Claim a slot. Returns a Slot, or None if none freed up within wait_s.

    `log` (callable) gets a line every ~30 s of waiting so a lane that is queued reads as queued in
    its own agent.log, not as hung.
    """
    slots_dir = Path(slots_dir or DEFAULT_DIR)
    slots_dir.mkdir(parents=True, exist_ok=True)
    count = count or slot_count()
    deadline = clock() + wait_s
    last_log = clock()
    while True:
        for i in range(count):
            fd = _try_claim(slots_dir / f"slot-{i:03d}")
            if fd is not None:
                return Slot(i, fd)
        now = clock()
        if now >= deadline:
            return None
        if log and now - last_log >= 30:
            log(f"SLOT | all {count} emulator slots busy; waiting ({int(deadline - now)}s left)")
            last_log = now
        sleep(poll_s)


def busy(slots_dir=None, count=None):
    """How many slots are currently held (best-effort, for status lines and tests)."""
    slots_dir = Path(slots_dir or DEFAULT_DIR)
    count = count or slot_count()
    n = 0
    for i in range(count):
        p = slots_dir / f"slot-{i:03d}"
        if not p.exists():
            continue
        fd = os.open(str(p), os.O_RDWR)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            n += 1
        finally:
            os.close(fd)
    return n
