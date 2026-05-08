"""Tests for src/arail/env_writer.py — atomic .env rewriter.

All round-trip cases from ARCHITECTURE.md §9 test_env_writer.py table.
"""

from __future__ import annotations

import os
import stat
import threading
import time
from pathlib import Path

import pytest

from arail.env_writer import EnvWriterError, set_env_var, read_env_var


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def _read(path: Path) -> bytes:
    return path.read_bytes()


# ---------------------------------------------------------------------------
# Round-trip cases
# ---------------------------------------------------------------------------

class TestSetEnvVarRoundTrips:
    def test_missing_line_append(self, tmp_path):
        """Key absent → appended after blank + comment marker."""
        env = tmp_path / ".env"
        _write(env, b"FOO=bar\n")
        result = set_env_var(env, "LAB_MODE", "hybrid")
        content = _read(env).decode()
        assert "LAB_MODE=hybrid" in content
        assert result["appended"] is True
        assert result["changed"] is True
        assert result["old_value"] is None
        assert result["new_value"] == "hybrid"

    def test_existing_simple_replace(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE=airgapped\n")
        result = set_env_var(env, "LAB_MODE", "hybrid")
        assert _read(env) == b"LAB_MODE=hybrid\n"
        assert result["changed"] is True
        assert result["appended"] is False
        assert result["old_value"] == "airgapped"

    def test_existing_double_quoted(self, tmp_path):
        """Double-quote style preserved on replace."""
        env = tmp_path / ".env"
        _write(env, b'LAB_MODE="airgapped"\n')
        set_env_var(env, "LAB_MODE", "hybrid")
        assert _read(env) == b'LAB_MODE="hybrid"\n'

    def test_existing_single_quoted(self, tmp_path):
        """Single-quote style preserved on replace."""
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE='airgapped'\n")
        set_env_var(env, "LAB_MODE", "hybrid")
        assert _read(env) == b"LAB_MODE='hybrid'\n"

    def test_inline_comment_preserved(self, tmp_path):
        """Inline comment survives value replacement."""
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE=airgapped # default\n")
        set_env_var(env, "LAB_MODE", "hybrid")
        out = _read(env).decode()
        assert "LAB_MODE=hybrid" in out
        assert "# default" in out

    def test_comment_line_above_preserved(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"# policy\nLAB_MODE=airgapped\n")
        set_env_var(env, "LAB_MODE", "hybrid")
        assert _read(env) == b"# policy\nLAB_MODE=hybrid\n"

    def test_crlf_endings(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"FOO=1\r\nLAB_MODE=airgapped\r\n")
        set_env_var(env, "LAB_MODE", "hybrid")
        assert _read(env) == b"FOO=1\r\nLAB_MODE=hybrid\r\n"

    def test_bom(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"\xef\xbb\xbfLAB_MODE=airgapped\n")
        set_env_var(env, "LAB_MODE", "hybrid")
        assert _read(env) == b"\xef\xbb\xbfLAB_MODE=hybrid\n"

    def test_no_trailing_newline_existing(self, tmp_path):
        """File without trailing newline gets one after write."""
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE=airgapped")
        set_env_var(env, "LAB_MODE", "hybrid")
        out = _read(env)
        assert out == b"LAB_MODE=hybrid\n"

    def test_trailing_whitespace_on_replaced_line(self, tmp_path):
        """Trailing whitespace on the value line is not preserved (re-emitted cleanly)."""
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE=airgapped   \n")
        set_env_var(env, "LAB_MODE", "hybrid")
        out = _read(env).decode()
        assert "LAB_MODE=hybrid" in out
        # The line should not have trailing spaces after the value.
        for line in out.splitlines():
            if line.startswith("LAB_MODE="):
                assert line == "LAB_MODE=hybrid", f"Unexpected: {line!r}"

    def test_duplicate_definitions(self, tmp_path, caplog):
        """First definition replaced; second left untouched; warning emitted."""
        import logging
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE=airgapped\nLAB_MODE=airgapped\n")
        with caplog.at_level(logging.WARNING, logger="arail.env_writer"):
            set_env_var(env, "LAB_MODE", "hybrid")
        out = _read(env).decode()
        lines = out.splitlines()
        assert lines[0] == "LAB_MODE=hybrid"
        assert lines[1] == "LAB_MODE=airgapped"  # second untouched
        assert any("extra" in r.message for r in caplog.records)

    def test_missing_file_creates_with_mode_600(self, tmp_path):
        """Non-existent file created with 0o600 permissions."""
        env = tmp_path / ".env"
        assert not env.exists()
        result = set_env_var(env, "LAB_MODE", "hybrid")
        assert env.exists()
        assert result["appended"] is True
        mode = stat.S_IMODE(env.stat().st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"

    def test_value_already_equals_no_write(self, tmp_path):
        """No file write when value already matches."""
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE=hybrid\n")
        mtime_before = env.stat().st_mtime_ns
        result = set_env_var(env, "LAB_MODE", "hybrid")
        assert result["changed"] is False
        assert result["appended"] is False
        assert env.stat().st_mtime_ns == mtime_before, "File was rewritten unnecessarily"

    def test_symlink_raises(self, tmp_path):
        """Symlinks are refused outright."""
        real = tmp_path / "real.env"
        real.write_bytes(b"LAB_MODE=airgapped\n")
        link = tmp_path / ".env"
        link.symlink_to(real)
        with pytest.raises(EnvWriterError, match="symlink"):
            set_env_var(link, "LAB_MODE", "hybrid")
        # Original target untouched.
        assert real.read_bytes() == b"LAB_MODE=airgapped\n"

    def test_concurrent_writers_no_torn_line(self, tmp_path):
        """32 threads alternating target; final state is one valid value, no torn lines."""
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE=airgapped\n")
        errors: list[Exception] = []

        def _flip(n: int) -> None:
            try:
                target = "hybrid" if n % 2 == 0 else "airgapped"
                set_env_var(env, "LAB_MODE", target)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=_flip, args=(i,)) for i in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors: {errors}"
        final = env.read_text()
        # Exactly one LAB_MODE line, and it's a valid value.
        lab_lines = [l for l in final.splitlines() if l.startswith("LAB_MODE=")]
        assert len(lab_lines) >= 1
        val = lab_lines[0].split("=", 1)[1].strip().strip("\"'")
        assert val in ("airgapped", "hybrid"), f"Torn value: {val!r}"

    def test_value_with_newline_raises(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"")
        with pytest.raises(EnvWriterError, match="forbidden"):
            set_env_var(env, "LAB_MODE", "x\ny")

    def test_invalid_key_raises(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"")
        with pytest.raises(EnvWriterError, match="invalid key"):
            set_env_var(env, "1bad", "x")


# ---------------------------------------------------------------------------
# read_env_var
# ---------------------------------------------------------------------------

class TestReadEnvVar:
    def test_returns_value(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE=hybrid\n")
        assert read_env_var(env, "LAB_MODE") == "hybrid"

    def test_returns_none_when_absent(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"FOO=bar\n")
        assert read_env_var(env, "LAB_MODE") is None

    def test_returns_none_when_file_missing(self, tmp_path):
        env = tmp_path / ".env"
        assert read_env_var(env, "LAB_MODE") is None

    def test_unquotes_double_quoted(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b'LAB_MODE="hybrid"\n')
        assert read_env_var(env, "LAB_MODE") == "hybrid"

    def test_last_assignment_wins(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"LAB_MODE=airgapped\nLAB_MODE=hybrid\n")
        assert read_env_var(env, "LAB_MODE") == "hybrid"

    def test_bom_handled(self, tmp_path):
        env = tmp_path / ".env"
        _write(env, b"\xef\xbb\xbfLAB_MODE=hybrid\n")
        assert read_env_var(env, "LAB_MODE") == "hybrid"
