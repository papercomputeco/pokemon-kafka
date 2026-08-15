"""In-run advice: the agent polls the inbox and applies typed advice mid-run."""

import json

from test_agent import _make_agent

ADVICE_SCHEMA = "pokemon.advice.v1"


def _line(id="a1", type="note", data=None, **overrides):
    base = {
        "schema": ADVICE_SCHEMA,
        "id": id,
        "type": type,
        "data": data if data is not None else {"text": "hello"},
        "expires_at": None,
        "source": "test",
    }
    base.update(overrides)
    return json.dumps(base) + "\n"


def _agent_with_inbox(tmp_path, *lines, poll_turns=1):
    ag = _make_agent(tmp_path)
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "advice.jsonl").write_text("".join(lines))
    ag.advice_inbox_dir = str(inbox)
    ag.advice_poll_turns = poll_turns
    return ag, inbox


def _milestones(ag):
    return [e["data"]["description"] for e in ag.collector.events if e["event_type"] == "milestone"]


def test_disabled_by_default(tmp_path):
    ag = _make_agent(tmp_path)
    assert ag.advice_inbox_dir is None
    ag._tick_advice()  # no inbox -> no-op, no error
    assert ag.collector.events == []


def test_genome_patch_hot_applies_and_emits_milestone(tmp_path):
    ag, _ = _agent_with_inbox(tmp_path, _line(id="g1", type="genome_patch", data={"door_cooldown": 9}))
    ag._tick_advice()
    assert ag.evolve_params["door_cooldown"] == 9
    assert any("Advice applied" in m and "door_cooldown=9" in m for m in _milestones(ag))


def test_genome_patch_ignores_unknown_params(tmp_path):
    ag, _ = _agent_with_inbox(tmp_path, _line(id="g2", type="genome_patch", data={"not_a_knob": 1}))
    ag._tick_advice()
    assert _milestones(ag) == []


def test_note_appends_to_strategy_notes_when_present(tmp_path):
    ag, _ = _agent_with_inbox(tmp_path, _line(id="n1", data={"text": "heal before the forest"}))
    from memory_file import MemoryFile

    ag.strategy_engine.notes = MemoryFile(str(tmp_path / "notes.md"))
    ag._tick_advice()
    assert "heal before the forest" in ag.strategy_engine.notes.read()
    assert any("Advice noted" in m for m in _milestones(ag))


def test_note_without_notes_file_still_emits_milestone(tmp_path):
    ag, _ = _agent_with_inbox(tmp_path, _line(id="n2", data={"text": "hello"}))
    assert ag.strategy_engine.notes is None
    ag._tick_advice()
    assert any("Advice noted" in m for m in _milestones(ag))


def test_dedupes_by_id_and_skips_expired_blank_unknown(tmp_path):
    ag, inbox = _agent_with_inbox(
        tmp_path,
        _line(id="dup"),
        _line(id="dup"),  # duplicate id -> applied once
        _line(id="old", expires_at="2000-01-01T00:00:00Z"),  # expired
        _line(id="blank", data={"text": "  "}),  # empty note text
        _line(id="mystery", type="teleport"),  # unknown type
        _line(id=""),  # missing id
    )
    ag._tick_advice()
    assert len(_milestones(ag)) == 1

    # A re-appended duplicate id is absorbed by the per-run seen set.
    with open(inbox / "advice.jsonl", "a") as fh:
        fh.write(_line(id="dup"))
    ag._tick_advice()
    assert len(_milestones(ag)) == 1


def test_poll_cadence_every_n_ticks(tmp_path):
    ag, _ = _agent_with_inbox(tmp_path, _line(id="c1"), poll_turns=3)
    ag._tick_advice()
    ag._tick_advice()
    assert _milestones(ag) == []  # ticks 1 and 2: no poll yet
    ag._tick_advice()
    assert len(_milestones(ag)) == 1  # tick 3 polls


def test_inbox_read_failure_never_breaks_the_run(tmp_path, monkeypatch):
    ag, _ = _agent_with_inbox(tmp_path, _line(id="x1"))
    import agent as agent_mod

    def boom(*a, **kw):
        raise OSError("disk gone")

    monkeypatch.setattr(agent_mod.advice, "poll_inbox", boom)
    ag._tick_advice()  # logs, does not raise
    assert _milestones(ag) == []


def test_turns_remaining_unlimited_and_bounded():
    from agent import PokemonAgent

    assert PokemonAgent._turns_remaining(10_000_000, -1)  # negative = unlimited
    assert not PokemonAgent._turns_remaining(0, 0)  # 0 keeps meaning zero iterations
    assert PokemonAgent._turns_remaining(4, 5)
    assert not PokemonAgent._turns_remaining(5, 5)


def test_fitness_snapshot_writes_on_interval(tmp_path):
    ag = _make_agent(tmp_path)
    out = tmp_path / "fit.json"
    ag.turn_count = 100
    ag._last_fitness_turn = -1
    ag._maybe_snapshot_fitness(100, str(out))
    written = json.loads(out.read_text())
    assert written["turns"] == 100

    out.unlink()
    ag._maybe_snapshot_fitness(100, str(out))  # same turn -> no rewrite
    assert not out.exists()

    ag.turn_count = 150  # off-interval -> no write
    ag._maybe_snapshot_fitness(100, str(out))
    assert not out.exists()


def test_fitness_snapshot_disabled_without_path_or_interval(tmp_path):
    ag = _make_agent(tmp_path)
    ag.turn_count = 100
    ag._last_fitness_turn = -1
    ag._maybe_snapshot_fitness(0, str(tmp_path / "a.json"))
    ag._maybe_snapshot_fitness(100, None)
    ag.turn_count = 0
    ag._maybe_snapshot_fitness(100, str(tmp_path / "a.json"))
    assert list(tmp_path.glob("*.json")) == []
