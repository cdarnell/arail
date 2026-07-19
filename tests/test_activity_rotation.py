"""activity.jsonl: tail-read boot + 10MB rotation (no more unbounded file)."""

from __future__ import annotations

import json
import time

import pytest

from arail import activity


@pytest.fixture
def log(monkeypatch, tmp_path):
    """Fresh ActivityLog against a tmp log file (singleton reset around)."""
    path = tmp_path / "activity.jsonl"
    monkeypatch.setattr(activity, "LOG_FILE", path)
    activity.ActivityLog._instance = None
    yield path
    activity.ActivityLog._instance = None


def _mk(path, n, msg="event"):
    with open(path, "w") as f:
        for i in range(n):
            f.write(json.dumps({"ts": i, "source": "t",
                                "message": f"{msg}-{i}", "level": "info"}) + "\n")


def test_boot_replays_tail_only(log):
    _mk(log, 1000)
    inst = activity.ActivityLog()
    events = list(inst._buffer)
    assert len(events) == 200
    assert events[-1]["message"] == "event-999"
    assert events[0]["message"] == "event-800"


def test_boot_tail_read_is_fast_on_huge_file(log):
    # ~20MB file: the old read_text() loaded it all; tail-read must not.
    big = {"ts": 0, "source": "t", "message": "x" * 400, "level": "info"}
    line = json.dumps(big) + "\n"
    with open(log, "w") as f:
        f.write(line * 50_000)
    t0 = time.monotonic()
    activity.ActivityLog()
    assert time.monotonic() - t0 < 0.5     # generous; whole-file read was O(file)


def test_rotation_at_10mb(log):
    _mk(log, 10)
    inst = activity.ActivityLog()
    # Grow past 10MB, then force the modulo-256 check to fire.
    with open(log, "a") as f:
        f.write(("{\"pad\":\"" + "y" * 1024 + "\"}\n") * 11_000)
    inst._emit_count = 255
    inst.emit("t", "tips the rotation")
    rotated = log.with_suffix(".jsonl.1")
    assert rotated.exists()
    assert log.stat().st_size < 1024 * 1024   # fresh active file
    tail = log.read_text().strip().splitlines()
    assert json.loads(tail[-1])["message"] == "tips the rotation"


def test_boot_reads_rotated_file_when_active_is_short(log):
    _mk(log.with_suffix(".jsonl.1"), 300, msg="old")
    _mk(log, 5, msg="new")
    inst = activity.ActivityLog()
    events = list(inst._buffer)
    assert len(events) == 200
    assert events[-1]["message"] == "new-4"
    assert any(e["message"].startswith("old-") for e in events)
