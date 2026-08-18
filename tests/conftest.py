"""Shared fixtures for Pokemon agent tests."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _private_emulator_slot_pool(tmp_path, monkeypatch):
    """Point every test at its own slot pool with plenty of slots.

    agent.main() acquires a box-wide emulator slot before it builds the agent (default wait
    900 s). The pool is sized cores-2, which is ONE slot on a 2-vCPU CI runner; a test whose
    mocked PokemonAgent never exits then holds that slot for the process lifetime and every later
    main() test blocks on it — the suite hung at "in progress" for 10+ minutes, three times, and
    never reproduced on a 32-core dev box. Tests must not touch the real pool at all.
    """
    import emulator_slots

    monkeypatch.setattr(emulator_slots, "DEFAULT_DIR", tmp_path / "slots")
    monkeypatch.setenv("POKEMON_EMULATOR_SLOTS", "64")


class FakeMemory:
    """Dict-backed memory that mimics pyboy.memory[addr] access."""

    def __init__(self):
        self._data: dict[int, int] = {}

    def __getitem__(self, addr: int) -> int:
        return self._data.get(addr, 0)

    def __setitem__(self, addr: int, value: int):
        self._data[addr] = value & 0xFF


@pytest.fixture
def fake_memory():
    return FakeMemory()


@pytest.fixture
def mock_pyboy(fake_memory):
    """PyBoy mock with dict-backed memory."""
    pyboy = MagicMock()
    pyboy.memory = fake_memory
    return pyboy


@pytest.fixture(autouse=True)
def _no_real_self_heal(monkeypatch):
    """Keep agent.main()'s automatic self-heal from spawning real healer subprocesses.

    Without this, CLI tests race variants against the repo's actual
    data/healer_state.json and notes.md. test_self_heal.py is unaffected:
    it imports run_self_heal directly and injects its own runner.
    """
    import agent

    monkeypatch.setattr(agent, "run_self_heal", lambda *a, **kw: False)
    # Same guard for the in-run wedge heal: a wedged test run must never spawn a
    # background race. Tests for the real thing import start_in_run_heal directly.
    monkeypatch.setattr(agent, "start_in_run_heal", lambda *a, **kw: None)
