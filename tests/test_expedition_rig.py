"""The Rig's sink, tested without booting a cartridge.

A run that does not emit is unminable, so the sink's shape is doctrine: one file per UTC date
under ``data/telemetry/game/``, one JSON object per line, every line carrying the run_id that
correlates it to ``runs/<run_id>/``.
"""

import json
from datetime import datetime, timezone

import expedition_rig as rig


def test_the_sink_is_one_file_per_utc_date(tmp_path):
    when = datetime(2026, 8, 31, 23, 59, tzinfo=timezone.utc)
    assert rig.telemetry_path(when, root=tmp_path).name == "2026-08-31.jsonl"


def test_events_append_as_jsonl_and_carry_the_run_id(tmp_path):
    rig.emit_event("run-abc", "supervisor.leg_start", {"goal": 157}, root=tmp_path)
    rig.emit_event("run-abc", "supervisor.leg_end", {"outcome": "arrived"}, root=tmp_path)
    lines = [json.loads(x) for x in rig.telemetry_path(root=tmp_path).read_text().splitlines()]
    assert [x["event"] for x in lines] == ["supervisor.leg_start", "supervisor.leg_end"]
    assert {x["run_id"] for x in lines} == {"run-abc"}
    assert lines[0]["source"] == "expedition" and lines[0]["goal"] == 157
    assert lines[1]["ts"]  # every line is stamped; the sink is time-ordered by append


def test_the_sink_directory_is_created_on_first_write(tmp_path):
    root = tmp_path / "not" / "yet"
    rig.emit_event("run-xyz", "supervisor.hop_failed", {"failure": "no-path"}, root=root)
    assert rig.telemetry_path(root=root).exists()


class FakeIO:
    """A world that swallows every step until `parked` rounds of A/B have been spent."""

    def __init__(self, rig, *, parked=0, walls=()):
        self.rig = rig
        self.parked = parked
        self.walls = set(walls)
        self.presses: list[str] = []

    def press(self, button, hold=8, release=8):
        self.presses.append(button)
        if button in ("a", "b"):
            self.parked = max(0, self.parked - (1 if button == "b" else 0))
            return
        if self.parked or button in self.walls:
            return
        dx, dy = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}[button]
        self.rig.mem[0xD362] += dx
        self.rig.mem[0xD361] += dy

    def wait(self, frames=30):
        pass


def _stub_rig(*, parked=0, walls=()):
    """A Rig with only the pieces settle() touches — no cartridge, no PyBoy."""
    r = rig.Rig.__new__(rig.Rig)
    r.mem = {0xD35E: 157, 0xD362: 4, 0xD361: 11, rig.ADDR_BADGES: 0b11111, 0xD057: 0}
    r.io = FakeIO(r, parked=parked, walls=walls)
    r.ctl = r.io
    return r


def test_probe_step_moves_and_undoes_itself():
    r = _stub_rig()
    assert r.probe_step() is True
    assert r.pos() == (157, 4, 11)  # the probe left the world exactly where it found it
    assert r.io.presses[:2] == ["down", "up"]


def test_probe_step_reports_false_when_every_direction_is_swallowed():
    r = _stub_rig(parked=99)
    assert r.probe_step() is False


def test_settle_flushes_a_parked_textbox_and_proves_it_with_a_step():
    """BADGE5.state was banked on Koga's TM line and refused all four steps until flushed."""
    r = _stub_rig(parked=2)
    assert r.settle() is True
    assert "b" in r.io.presses  # A advances the pages, B closes what A opened
    assert r.pos() == (157, 4, 11)


def test_settle_gives_up_honestly_rather_than_claiming_a_flush():
    r = _stub_rig(parked=99)
    assert r.settle(max_rounds=3) is False


def test_the_rig_points_at_this_repos_rom_and_baton_shelf():
    assert rig.ROM_DEFAULT.name == "pokemon_red.gb"
    assert rig.BATON_DIR.parts[-2:] == ("local_runs", "roster-bench")
    assert rig.TELEMETRY_DIR.parts[-2:] == ("telemetry", "game")
