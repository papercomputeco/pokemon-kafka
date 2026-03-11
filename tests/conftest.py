"""Shared fixtures for Pokemon agent tests."""

from unittest.mock import MagicMock

import pytest


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
