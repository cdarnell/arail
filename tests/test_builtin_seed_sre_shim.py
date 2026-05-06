"""Tests for the SRE PKB shim written by builtin_seed.ensure_sre_folder.

Per ARCHITECTURE.md S.5:
- ensure_sre_folder() writes a thin shim, not a full body copy.
- Shim first non-blank line starts with the sentinel string (SRE PKB shim).
- Shim file is < 80 lines (wider than Buddy's 60 because re-export list is 16 names).
- Importing the shim yields module.sre that is the same object as
  arail.agents._builtin_sre.sre (identity, not equality).
- module._watch_dependency_vulnerabilities is the same callable as the
  canonical one (proves the shim does not fork the watcher functions).
- With an existing forked file (header != sentinel), ensure_sre_folder()
  does NOT rewrite it (idempotency for forked users).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


# ── Helpers ───────────────────────────────────────────────────────────

def _call_ensure_sre_folder(tmp_path: Path) -> dict:
    from arail.agents.builtin_seed import ensure_sre_folder
    return ensure_sre_folder(pkb_root=tmp_path)


def _sre_py(tmp_path: Path) -> Path:
    return tmp_path / "agents" / "sre" / "sre.py"


# ── Tests ─────────────────────────────────────────────────────────────

class TestSreShimWritten:
    def test_sre_py_exists_after_ensure(self, tmp_path):
        _call_ensure_sre_folder(tmp_path)
        assert _sre_py(tmp_path).exists()

    def test_first_non_blank_line_is_sentinel(self, tmp_path):
        _call_ensure_sre_folder(tmp_path)
        content = _sre_py(tmp_path).read_text(encoding="utf-8")
        non_blank = [ln for ln in content.splitlines() if ln.strip()]
        assert non_blank, "shim file must not be empty"
        assert non_blank[0].startswith('"""SRE — PKB shim.'), (
            f"First non-blank line of shim was: {non_blank[0]!r}"
        )

    def test_shim_is_under_80_lines(self, tmp_path):
        _call_ensure_sre_folder(tmp_path)
        lines = _sre_py(tmp_path).read_text(encoding="utf-8").splitlines()
        assert len(lines) < 80, (
            f"Shim must be < 80 lines to guard against accidental full-body copy; "
            f"got {len(lines)} lines."
        )

    def test_shim_imports_are_identity_preserving(self, tmp_path):
        """The shim's ``sre`` attribute must be the same object as the
        canonical module's ``sre`` singleton (not a copy)."""
        _call_ensure_sre_folder(tmp_path)
        shim_path = _sre_py(tmp_path)

        unique_name = f"_test_sre_shim_{id(tmp_path)}"
        spec = importlib.util.spec_from_file_location(unique_name, str(shim_path))
        assert spec is not None and spec.loader is not None, "could not create spec for shim"
        shim_module = importlib.util.module_from_spec(spec)
        sys.modules[unique_name] = shim_module
        try:
            spec.loader.exec_module(shim_module)
        finally:
            sys.modules.pop(unique_name, None)

        from arail.agents import _builtin_sre as canonical
        assert shim_module.sre is canonical.sre, (
            "shim.sre must be the same object as _builtin_sre.sre "
            "(the loader must not fork the singleton)"
        )

    def test_shim_watcher_functions_are_identity_preserving(self, tmp_path):
        """The shim's ``_watch_dependency_vulnerabilities`` must be the same
        callable as the canonical's (proves no fork of watcher logic)."""
        _call_ensure_sre_folder(tmp_path)
        shim_path = _sre_py(tmp_path)

        unique_name = f"_test_sre_shim_watcher_{id(tmp_path)}"
        spec = importlib.util.spec_from_file_location(unique_name, str(shim_path))
        assert spec is not None and spec.loader is not None, "could not create spec for shim"
        shim_module = importlib.util.module_from_spec(spec)
        sys.modules[unique_name] = shim_module
        try:
            spec.loader.exec_module(shim_module)
        finally:
            sys.modules.pop(unique_name, None)

        from arail.agents import _builtin_sre as canonical
        assert shim_module._watch_dependency_vulnerabilities is canonical._watch_dependency_vulnerabilities, (
            "shim._watch_dependency_vulnerabilities must be the same callable as "
            "_builtin_sre._watch_dependency_vulnerabilities"
        )


class TestSreShimIdempotency:
    def test_second_call_does_not_overwrite_shim(self, tmp_path):
        _call_ensure_sre_folder(tmp_path)
        path = _sre_py(tmp_path)
        mtime_before = path.stat().st_mtime
        import time; time.sleep(0.01)
        _call_ensure_sre_folder(tmp_path)
        # File should not be touched — returns early when sre.py exists.
        mtime_after = path.stat().st_mtime
        assert mtime_after == mtime_before, (
            "ensure_sre_folder() must not rewrite sre.py when it already exists"
        )

    def test_forked_file_is_not_rewritten(self, tmp_path):
        """If sre.py exists and starts with something other than the shim
        sentinel, ensure_sre_folder() must leave it alone."""
        agents_dir = tmp_path / "agents" / "sre"
        agents_dir.mkdir(parents=True, exist_ok=True)
        forked_content = "# My custom SRE — fully forked\nsre = None\n"
        sre_py = agents_dir / "sre.py"
        sre_py.write_text(forked_content, encoding="utf-8")

        _call_ensure_sre_folder(tmp_path)

        assert sre_py.read_text(encoding="utf-8") == forked_content, (
            "ensure_sre_folder() must not overwrite a forked sre.py"
        )
