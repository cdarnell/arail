"""Tests for the Buddy PKB shim written by builtin_seed.ensure_buddy_folder.

Per ARCHITECTURE.md §11.1.B.5:
- ensure_buddy_folder() writes a thin shim, not a full body copy.
- Shim first non-blank line equals the sentinel.
- Shim file is < 60 lines (regression guard).
- Importing the shim yields module.buddy that is the same object as
  arail.agents._builtin_buddy.buddy (identity, not equality).
- With an existing forked file (header != sentinel), ensure_buddy_folder()
  does NOT rewrite it (idempotency for forked users).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────

def _call_ensure_buddy_folder(tmp_path: Path) -> dict:
    from arail.agents.builtin_seed import ensure_buddy_folder
    return ensure_buddy_folder(pkb_root=tmp_path)


def _buddy_py(tmp_path: Path) -> Path:
    return tmp_path / "agents" / "buddy" / "buddy.py"


# ── Tests ─────────────────────────────────────────────────────────────

class TestBuddyShimWritten:
    def test_buddy_py_exists_after_ensure(self, tmp_path):
        _call_ensure_buddy_folder(tmp_path)
        assert _buddy_py(tmp_path).exists()

    def test_first_non_blank_line_is_sentinel(self, tmp_path):
        _call_ensure_buddy_folder(tmp_path)
        content = _buddy_py(tmp_path).read_text(encoding="utf-8")
        non_blank = [ln for ln in content.splitlines() if ln.strip()]
        assert non_blank, "shim file must not be empty"
        assert non_blank[0].startswith('"""Buddy — PKB shim.'), (
            f"First non-blank line of shim was: {non_blank[0]!r}"
        )

    def test_shim_is_under_60_lines(self, tmp_path):
        _call_ensure_buddy_folder(tmp_path)
        lines = _buddy_py(tmp_path).read_text(encoding="utf-8").splitlines()
        assert len(lines) < 60, (
            f"Shim must be < 60 lines to guard against accidental full-body copy; "
            f"got {len(lines)} lines."
        )

    def test_shim_imports_are_identity_preserving(self, tmp_path):
        """The shim's ``buddy`` attribute must be the same object as the
        canonical module's ``buddy`` singleton (not a copy)."""
        _call_ensure_buddy_folder(tmp_path)
        shim_path = _buddy_py(tmp_path)

        unique_name = f"_test_buddy_shim_{id(tmp_path)}"
        spec = importlib.util.spec_from_file_location(unique_name, str(shim_path))
        assert spec is not None and spec.loader is not None, "could not create spec for shim"
        shim_module = importlib.util.module_from_spec(spec)
        sys.modules[unique_name] = shim_module
        try:
            spec.loader.exec_module(shim_module)
        finally:
            sys.modules.pop(unique_name, None)

        from arail.agents import _builtin_buddy as canonical
        assert shim_module.buddy is canonical.buddy, (
            "shim.buddy must be the same object as _builtin_buddy.buddy "
            "(the loader must not fork the singleton)"
        )


class TestBuddyShimIdempotency:
    def test_second_call_does_not_overwrite_shim(self, tmp_path):
        _call_ensure_buddy_folder(tmp_path)
        path = _buddy_py(tmp_path)
        mtime_before = path.stat().st_mtime
        import time; time.sleep(0.01)
        _call_ensure_buddy_folder(tmp_path)
        # File should not be touched — returns early when buddy.py exists.
        mtime_after = path.stat().st_mtime
        assert mtime_after == mtime_before, (
            "ensure_buddy_folder() must not rewrite buddy.py when it already exists"
        )

    def test_forked_file_is_not_rewritten(self, tmp_path):
        """If buddy.py exists and starts with something other than the shim
        sentinel, ensure_buddy_folder() must leave it alone."""
        agents_dir = tmp_path / "agents" / "buddy"
        agents_dir.mkdir(parents=True, exist_ok=True)
        forked_content = "# My custom Buddy — fully forked\nbuddy = None\n"
        buddy_py = agents_dir / "buddy.py"
        buddy_py.write_text(forked_content, encoding="utf-8")

        _call_ensure_buddy_folder(tmp_path)

        assert buddy_py.read_text(encoding="utf-8") == forked_content, (
            "ensure_buddy_folder() must not overwrite a forked buddy.py"
        )
