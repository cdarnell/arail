"""Tests for write-time token redaction in opencode.log.

Architecture ref: sprints/2026-05-14-security-hygiene/ARCHITECTURE.md § Item 2
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_redactor():
    from arail.portal.services.opencode import _RedactingLogWriter, _REDACTED
    return _RedactingLogWriter, _REDACTED


def _import_pipe_helpers():
    from arail.portal.services.opencode import (
        _open_log_with_redactor,
        _REDACTED,
    )
    return _open_log_with_redactor, _REDACTED


# ---------------------------------------------------------------------------
# Unit: _RedactingLogWriter
# ---------------------------------------------------------------------------

def test_redacts_single_token_in_chunk(tmp_path):
    _RedactingLogWriter, _REDACTED = _import_redactor()
    log = tmp_path / "opencode.log"
    secret = b"SUPER_SECRET_TOKEN_XYZ"
    writer = _RedactingLogWriter(log, [secret])
    writer.write(b"prefix " + secret + b" suffix")
    writer.flush_tail()
    writer.close()
    content = log.read_bytes()
    assert secret not in content
    assert _REDACTED in content
    assert b"prefix " in content
    assert b" suffix" in content


def test_redacts_token_split_across_two_writes(tmp_path):
    _RedactingLogWriter, _REDACTED = _import_redactor()
    log = tmp_path / "opencode.log"
    secret = b"SPLIT_TOKEN_ABCDEFGH"
    split = len(secret) // 2
    writer = _RedactingLogWriter(log, [secret])
    writer.write(b"start " + secret[:split])
    writer.write(secret[split:] + b" end")
    writer.flush_tail()
    writer.close()
    content = log.read_bytes()
    assert secret not in content
    assert _REDACTED in content


def test_redacts_multiple_distinct_tokens(tmp_path):
    _RedactingLogWriter, _REDACTED = _import_redactor()
    log = tmp_path / "opencode.log"
    s1 = b"ANTHROPIC_KEY_1234567"
    s2 = b"OPENROUTER_KEY_98765"
    writer = _RedactingLogWriter(log, [s1, s2])
    writer.write(b"auth failed " + s1 + b" also " + s2)
    writer.flush_tail()
    writer.close()
    content = log.read_bytes()
    assert s1 not in content
    assert s2 not in content
    assert content.count(_REDACTED) == 2


def test_passes_through_when_no_secrets(tmp_path):
    _RedactingLogWriter, _REDACTED = _import_redactor()
    log = tmp_path / "opencode.log"
    writer = _RedactingLogWriter(log, [])
    payload = b"nothing secret here"
    writer.write(payload)
    writer.flush_tail()
    writer.close()
    content = log.read_bytes()
    assert payload in content
    assert _REDACTED not in content


def test_ignores_empty_or_short_secrets(tmp_path):
    """Secrets shorter than 8 bytes must not be redacted (false-positive risk)."""
    _RedactingLogWriter, _REDACTED = _import_redactor()
    log = tmp_path / "opencode.log"
    short = b"abc"  # 3 bytes — below _MIN_SECRET_LEN
    writer = _RedactingLogWriter(log, [b"", short])
    payload = b"abc is in here"
    writer.write(payload)
    writer.flush_tail()
    writer.close()
    content = log.read_bytes()
    # Short secret must NOT have been redacted (it would break the data)
    assert _REDACTED not in content
    assert b"abc" in content


@pytest.mark.skipif(sys.platform == "win32", reason="chmod not meaningful on Windows")
def test_chmod_0600_after_open(tmp_path):
    _RedactingLogWriter, _ = _import_redactor()
    log = tmp_path / "opencode.log"
    writer = _RedactingLogWriter(log, [])
    writer.close()
    mode = oct(os.stat(log).st_mode)[-4:]  # e.g. '0600'
    assert mode == "0600", f"expected 0600, got {mode}"


# ---------------------------------------------------------------------------
# Unit: _maybe_rotate_log — permission hardening on .log.1
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="chmod not meaningful on Windows")
def test_rotated_log_also_has_0600_permissions(tmp_path, monkeypatch):
    from arail.portal.services import opencode as oc
    monkeypatch.setattr(oc, "_LOG_MAX_BYTES", 0)  # Force rotation of any non-empty file
    log = tmp_path / "opencode.log"
    log.write_bytes(b"old content")
    oc._maybe_rotate_log(log)
    rotated = tmp_path / "opencode.log.1"
    assert rotated.exists()
    mode = oct(os.stat(rotated).st_mode)[-4:]
    assert mode == "0600", f"expected 0600, got {mode}"


# ---------------------------------------------------------------------------
# Unit: tombstone — existing log dropped on _open_log_with_redactor
# ---------------------------------------------------------------------------

def test_existing_log_truncated_on_start(tmp_path):
    """Pre-existing opencode.log content is dropped (tombstone behaviour)."""
    _open_log_with_redactor, _ = _import_pipe_helpers()
    log = tmp_path / "opencode.log"
    log.write_text("old sensitive content")

    write_fd, writer, thread = _open_log_with_redactor(log, {})
    thread.start()
    os.close(write_fd)  # EOF immediately
    thread.join(timeout=2)
    writer.close()

    content = log.read_bytes()
    assert b"old sensitive content" not in content


def test_rotated_log_dropped_on_start(tmp_path):
    """Pre-existing .log.1 is also dropped (may contain old tokens)."""
    _open_log_with_redactor, _ = _import_pipe_helpers()
    log = tmp_path / "opencode.log"
    rotated = tmp_path / "opencode.log.1"
    log.write_bytes(b"")
    rotated.write_text("old rotated content")

    write_fd, writer, thread = _open_log_with_redactor(log, {})
    thread.start()
    os.close(write_fd)
    thread.join(timeout=2)
    writer.close()

    assert not rotated.exists()


# ---------------------------------------------------------------------------
# Integration: subprocess output through redactor
# ---------------------------------------------------------------------------

def test_subprocess_stdout_through_redactor(tmp_path):
    """Spawn a real subprocess that prints a secret; assert it is redacted in log."""
    import subprocess
    _open_log_with_redactor, _REDACTED = _import_pipe_helpers()

    log = tmp_path / "opencode.log"
    secret = "SECRET_TOKEN_INTEGRATION_ABC123"
    env = {**os.environ, "ANTHROPIC_API_KEY": secret}

    write_fd, writer, thread = _open_log_with_redactor(log, env)
    thread.start()
    proc = subprocess.Popen(
        [sys.executable, "-c", f"import sys; sys.stdout.write('{secret}\\n'); sys.stdout.flush()"],
        stdout=write_fd,
        stderr=write_fd,
    )
    os.close(write_fd)
    proc.wait(timeout=5)
    thread.join(timeout=2)
    writer.close()

    content = log.read_bytes()
    assert secret.encode() not in content, "Token must not appear in log"
    assert _REDACTED in content, "Redaction sentinel must appear in log"
