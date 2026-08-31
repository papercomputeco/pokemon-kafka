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
    """A world that swallows every step until `parked` rounds of A/B have been spent.

    Stepping onto a warp tile moves us to another map, exactly as the cartridge does — which is
    how the badge-6 leg warped itself back into the gym it had just left.
    """

    def __init__(self, rig, *, parked=0, walls=(), warp_to=None):
        self.rig = rig
        self.parked = parked
        self.walls = set(walls)
        self.warp_to = warp_to  # {(x, y): destination map id}
        self.presses: list[str] = []

    def press(self, button, hold=8, release=8):
        self.presses.append(button)
        if button in ("a", "b"):
            self.parked = max(0, self.parked - (1 if button == "b" else 0))
            return
        if self.parked or button in self.walls:
            return
        dx, dy = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}[button]
        nx, ny = self.rig.mem[0xD362] + dx, self.rig.mem[0xD361] + dy
        self.rig.mem[0xD362], self.rig.mem[0xD361] = nx, ny
        if self.warp_to and (nx, ny) in self.warp_to:
            self.rig.mem[0xD35E] = self.warp_to[(nx, ny)]

    def wait(self, frames=30):
        pass


def _stub_rig(*, parked=0, walls=(), warps=(), warp_to=None, at=(4, 11)):
    """A Rig with only the pieces settle() touches — no cartridge, no PyBoy."""
    r = rig.Rig.__new__(rig.Rig)
    r.mem = {0xD35E: 157, 0xD362: at[0], 0xD361: at[1], rig.ADDR_BADGES: 0b11111, 0xD057: 0}
    r.truth = {"maps": {"157": {"warps": [[wx, wy, 7, 0] for wx, wy in warps]}}}
    r.io = FakeIO(r, parked=parked, walls=walls, warp_to=warp_to)
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


def test_the_probe_refuses_to_thread_a_door():
    """Measured: a baton banked one tile below Fuchsia gym's mat probed *up* and warped inside."""
    r = _stub_rig(at=(5, 28), warps=[(5, 27)], warp_to={(5, 27): 999})
    assert r.probe_step() is True
    assert r.pos()[0] == 157  # the probe proved input without going through the door
    assert "up" not in r.io.presses[:1]


def test_the_probe_uses_a_door_only_when_there_is_nothing_else():
    """A state wedged in a doorway still has to be able to prove it accepts input."""
    r = _stub_rig(at=(5, 28), warps=[(5, 27), (5, 29), (4, 28), (6, 28)], warp_to={(5, 29): 999})
    assert r.probe_step() is True
    assert r.pos()[0] == 999  # it went through, because every neighbour was a door


def test_the_rig_points_at_this_repos_rom_and_baton_shelf():
    assert rig.ROM_DEFAULT.name == "pokemon_red.gb"
    assert rig.BATON_DIR.parts[-2:] == ("local_runs", "roster-bench")
    assert rig.TELEMETRY_DIR.parts[-2:] == ("telemetry", "game")


def test_settled_pos_rejects_a_torn_read_across_a_warp():
    """(234, 17, 11) on a map 16 tiles wide is the transition window, not a place."""
    r = _stub_rig(at=(17, 11))
    r.mem[0xD35E] = 234
    r.truth = {"maps": {"234": {"width": 16, "height": 18, "warps": []}}}
    calls = {"n": 0}

    def press(button, hold=8, release=8):  # the transition completes as the world ticks on
        calls["n"] += 1

    def wait(frames=30):
        r.mem[0xD362], r.mem[0xD361] = 13, 7
        r.mem[0xD35E] = 209

    r.io.press, r.io.wait = press, wait
    r.truth["maps"]["209"] = {"width": 26, "height": 18, "warps": []}
    assert r.settled_pos() == (209, 13, 7)


def test_settled_pos_returns_a_stable_in_bounds_read_unchanged():
    r = _stub_rig(at=(4, 11))
    r.truth = {"maps": {"157": {"width": 10, "height": 18, "warps": []}}}
    r.io.wait = lambda frames=30: None
    assert r.settled_pos() == (157, 4, 11)
