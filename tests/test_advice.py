"""Advice inbox reader — file-based feedback into a live run."""

import json
from datetime import datetime, timedelta, timezone

from advice import SCHEMA_ADVICE, is_expired, poll_inbox


def _line(id="a1", type="note", **overrides):
    base = {
        "schema": SCHEMA_ADVICE,
        "id": id,
        "type": type,
        "data": {"text": "hi"},
        "expires_at": None,
        "source": "test",
    }
    base.update(overrides)
    return json.dumps(base)


def test_poll_inbox_reads_new_lines_and_advances_offsets(tmp_path):
    (tmp_path / "advice.jsonl").write_text(_line(id="a1") + "\n" + _line(id="a2") + "\n")
    items, offsets = poll_inbox(str(tmp_path), {})
    assert [i["id"] for i in items] == ["a1", "a2"]

    # Nothing new: same offsets, no items.
    again, offsets2 = poll_inbox(str(tmp_path), offsets)
    assert again == [] and offsets2 == offsets

    # Appended line is picked up from the saved offset.
    with open(tmp_path / "advice.jsonl", "a") as fh:
        fh.write(_line(id="a3") + "\n")
    items3, _ = poll_inbox(str(tmp_path), offsets)
    assert [i["id"] for i in items3] == ["a3"]


def test_poll_inbox_leaves_partial_trailing_line(tmp_path):
    (tmp_path / "advice.jsonl").write_text(_line(id="a1") + "\n" + '{"schema": "pokemon.adv')
    items, offsets = poll_inbox(str(tmp_path), {})
    assert [i["id"] for i in items] == ["a1"]

    # Writer finishes the line -> it is read exactly once.
    with open(tmp_path / "advice.jsonl", "a") as fh:
        fh.write('ice.v1", "id": "a2", "type": "note", "data": {}}' + "\n")
    items2, _ = poll_inbox(str(tmp_path), offsets)
    assert [i["id"] for i in items2] == ["a2"]


def test_poll_inbox_skips_malformed_and_foreign_lines(tmp_path):
    (tmp_path / "advice.jsonl").write_text(
        "not json\n"
        + json.dumps({"schema": "other.v1", "id": "x"})
        + "\n"
        + json.dumps(["a", "list"])
        + "\n"
        + _line(id="good")
        + "\n"
    )
    items, _ = poll_inbox(str(tmp_path), {})
    assert [i["id"] for i in items] == ["good"]


def test_poll_inbox_missing_dir_is_empty(tmp_path):
    items, offsets = poll_inbox(str(tmp_path / "nope"), {"stale.jsonl": 7})
    assert items == [] and offsets == {"stale.jsonl": 7}


def test_poll_inbox_reads_files_in_sorted_order(tmp_path):
    (tmp_path / "b.jsonl").write_text(_line(id="from-b") + "\n")
    (tmp_path / "a.jsonl").write_text(_line(id="from-a") + "\n")
    items, _ = poll_inbox(str(tmp_path), {})
    assert [i["id"] for i in items] == ["from-a", "from-b"]


def test_is_expired_cases():
    now = datetime(2026, 8, 14, 12, 0, 0, tzinfo=timezone.utc)
    future = (now + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    past = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert not is_expired({"expires_at": None}, now)
    assert not is_expired({}, now)
    assert not is_expired({"expires_at": future}, now)
    assert is_expired({"expires_at": past}, now)
    assert is_expired({"expires_at": "not-a-date"}, now)


def test_is_expired_defaults_to_wall_clock():
    assert is_expired({"expires_at": "2000-01-01T00:00:00Z"})
