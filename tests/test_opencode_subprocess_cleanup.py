"""Tests for start_new_session=True on opencode subprocess Popen calls.

Architecture ref: sprints/2026-05-14-security-hygiene/ARCHITECTURE.md § Item 3
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Unit: both Popen call-sites pass start_new_session=True
# ---------------------------------------------------------------------------

def _make_popen_capture():
    """Return a MagicMock Popen and list that captures kwargs."""
    calls = []

    class FakePopen:
        def __init__(self, *args, **kwargs):
            calls.append(kwargs)
            self.pid = 99999

    return FakePopen, calls


def test_start_passes_start_new_session(tmp_path, monkeypatch):
    """opencode.start() must pass start_new_session=True to Popen."""
    import arail.portal.services.opencode as oc

    FakePopen, calls = _make_popen_capture()

    monkeypatch.setattr(oc, "is_installed", lambda: True)
    monkeypatch.setattr(oc, "is_running", lambda port: False)
    monkeypatch.setattr(oc, "_maybe_rotate_log", lambda path: None)
    monkeypatch.setattr(oc, "_regenerate_config_unlocked", lambda: {"ok": True, "path": "x"})
    monkeypatch.setattr(oc, "_compute_source_env", lambda: {})

    # Patch _open_log_with_redactor to return a real pipe (no actual file I/O)
    r_fd, w_fd = os.pipe()
    dummy_writer = MagicMock()
    dummy_writer.flush_tail = MagicMock()
    dummy_thread = MagicMock()
    dummy_thread.start = MagicMock()
    monkeypatch.setattr(oc, "_open_log_with_redactor", lambda path, env: (w_fd, dummy_writer, dummy_thread))

    import threading
    popen_calls = []

    original_Popen = subprocess.Popen

    class CapturingPopen:
        def __init__(self, *args, **kwargs):
            popen_calls.append(kwargs)
            self.pid = 12345
            # Close the write fd so the pipe doesn't leak
            try:
                os.close(w_fd)
            except OSError:
                pass

    with patch("subprocess.Popen", CapturingPopen):
        # close read end to avoid leaking
        try:
            oc.start(port=14096)
        except Exception:
            pass
    try:
        os.close(r_fd)
    except OSError:
        pass

    assert popen_calls, "Popen was not called"
    assert popen_calls[0].get("start_new_session") is True, (
        f"start_new_session missing from start() Popen kwargs: {popen_calls[0]}"
    )


def test_start_inner_passes_start_new_session(tmp_path, monkeypatch):
    """opencode._start_inner() must also pass start_new_session=True."""
    import arail.portal.services.opencode as oc

    monkeypatch.setattr(oc, "is_installed", lambda: True)
    monkeypatch.setattr(oc, "is_running", lambda port: False)
    monkeypatch.setattr(oc, "_maybe_rotate_log", lambda path: None)
    monkeypatch.setattr(oc, "_regenerate_config_unlocked", lambda: {"ok": True, "path": "x"})
    monkeypatch.setattr(oc, "_compute_source_env", lambda: {})

    r_fd, w_fd = os.pipe()
    dummy_writer = MagicMock()
    dummy_thread = MagicMock()
    monkeypatch.setattr(oc, "_open_log_with_redactor", lambda path, env: (w_fd, dummy_writer, dummy_thread))

    popen_calls = []

    class CapturingPopen:
        def __init__(self, *args, **kwargs):
            popen_calls.append(kwargs)
            self.pid = 12346
            try:
                os.close(w_fd)
            except OSError:
                pass

    with patch("subprocess.Popen", CapturingPopen):
        try:
            oc._start_inner(port=14097)
        except Exception:
            pass
    try:
        os.close(r_fd)
    except OSError:
        pass

    assert popen_calls, "Popen was not called from _start_inner"
    assert popen_calls[0].get("start_new_session") is True, (
        f"start_new_session missing from _start_inner() Popen kwargs: {popen_calls[0]}"
    )


# ---------------------------------------------------------------------------
# Integration: child is its own process-group leader (POSIX only)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")
def test_child_is_pgroup_leader():
    """A child spawned with start_new_session=True is its own pgid leader."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        pgid = os.getpgid(proc.pid)
        assert pgid == proc.pid, f"expected pgid == pid ({proc.pid}), got {pgid}"
    finally:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        proc.wait(timeout=3)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")
def test_killpg_cascades_to_grandchild():
    """SIGTERM to pgid of session-leader kills both child and grandchild."""
    # Parent spawns a grandchild sleeper; we kill the whole group.
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import subprocess, sys, time; "
                "grandchild = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
                "time.sleep(30)"
            ),
        ],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Give parent time to spawn grandchild
    time.sleep(0.3)

    grandchild_alive_before = True
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        time.sleep(0.5)
        # If the process group is gone, killpg raises ProcessLookupError or
        # PermissionError on macOS (when the group leader has already exited).
        os.killpg(proc.pid, 0)  # signal 0 = existence check
        grandchild_alive_before = True  # still alive — unexpected
    except (ProcessLookupError, PermissionError):
        grandchild_alive_before = False  # group is gone — expected
    finally:
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    assert not grandchild_alive_before, "Process group should be gone after SIGTERM to pgid"
