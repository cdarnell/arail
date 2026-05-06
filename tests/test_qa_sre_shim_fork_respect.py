"""QA — SRE shim must respect user forks (architect's #1 priority).

The architect's re-review listed this as the highest-leverage attack
on the new shim pattern: a user can fork ``lab/pkb/agents/sre/sre.py``
and the loader must pick up the user's fork — NOT silently overwrite
it on next boot, NOT silently inherit canonical changes.

The existing ``tests/test_builtin_seed_sre_shim.py`` covers
content-preservation (the file's bytes are not rewritten). These
tests go further: they confirm that the *behavior* the user added
in their fork (custom WATCHERS, custom NAME, etc.) is what runs.

Test strategy: write a forked sre.py with a marker WATCHERS list,
run ``ensure_sre_folder``, import the file by spec, and verify the
loaded module's WATCHERS is the fork's, not the canonical's.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def _sre_py_path(tmp_path: Path) -> Path:
    return tmp_path / "agents" / "sre" / "sre.py"


def _import_by_path(path: Path, mod_name: str):
    """Import a module by file path; clean it up after."""
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    try:
        spec.loader.exec_module(mod)
        return mod
    finally:
        sys.modules.pop(mod_name, None)


# ──────────────────────────────────────────────────────────────────────
# Architect's #1 — fork respect
# ──────────────────────────────────────────────────────────────────────

class TestSreForkRespect:
    """Confirm that ``ensure_sre_folder()`` does NOT overwrite a
    user-edited file (no shim sentinel), and that the loader-reachable
    module exposes the user's fork's symbols, not canonical's."""

    def test_forked_watchers_replaces_canonical_watchers(self, tmp_path):
        """User's fork has 1 WATCHER; canonical has 5. After loading,
        the fork's WATCHERS list (1 entry) is what runs, not 5."""
        agents_dir = tmp_path / "agents" / "sre"
        agents_dir.mkdir(parents=True, exist_ok=True)

        forked_content = '''"""User's custom SRE — fully forked, no shim sentinel."""

NAME = "MyCustomSRE"
EMOJI = "X"

# Marker: the user defines exactly ONE watcher.
def _my_only_watcher():
    return None

WATCHERS = [_my_only_watcher]
sre = None  # placeholder — loader still imports
'''
        sre_py = agents_dir / "sre.py"
        sre_py.write_text(forked_content, encoding="utf-8")

        # Ensure folder — must NOT overwrite forked content.
        from arail.agents.builtin_seed import ensure_sre_folder
        ensure_sre_folder(pkb_root=tmp_path)

        # File preserved verbatim.
        on_disk = sre_py.read_text(encoding="utf-8")
        assert on_disk == forked_content, (
            "ensure_sre_folder must NOT rewrite a forked file"
        )

        # Load by path and verify the fork's symbols win.
        mod = _import_by_path(sre_py, f"_qa_forked_sre_{id(tmp_path)}")

        assert mod.NAME == "MyCustomSRE", (
            f"Forked NAME must be the user's, not canonical 'SRE'; got {mod.NAME!r}"
        )
        assert len(mod.WATCHERS) == 1, (
            f"Forked WATCHERS must have 1 entry, not the canonical 5; "
            f"got {len(mod.WATCHERS)}"
        )
        assert mod.WATCHERS[0].__name__ == "_my_only_watcher"

        # And critically: the fork's watcher is NOT canonical's
        # _watch_recent_errors.
        from arail.agents import _builtin_sre as canonical
        assert mod.WATCHERS[0] is not canonical._watch_recent_errors
        # And the canonical's full WATCHERS list is unaffected (5 entries).
        assert len(canonical.WATCHERS) == 5, (
            "Canonical WATCHERS list must remain at 5 — fork must not "
            "mutate package-level state"
        )

    def test_forked_watchers_dont_pull_canonical_via_re_export(self, tmp_path):
        """A fork with NO ``from arail.agents._builtin_sre import WATCHERS``
        line must NOT have the canonical WATCHERS appear via some
        re-export side-channel."""
        agents_dir = tmp_path / "agents" / "sre"
        agents_dir.mkdir(parents=True, exist_ok=True)

        forked_content = '''"""User's tiny fork — no imports from canonical."""

NAME = "TinyFork"
WATCHERS = []
'''
        (agents_dir / "sre.py").write_text(forked_content, encoding="utf-8")

        from arail.agents.builtin_seed import ensure_sre_folder
        ensure_sre_folder(pkb_root=tmp_path)

        mod = _import_by_path(
            agents_dir / "sre.py", f"_qa_forked_no_imports_{id(tmp_path)}"
        )
        assert mod.WATCHERS == [], (
            "User's empty WATCHERS list must remain empty after loading"
        )

    def test_fork_with_partial_shim_sentinel_match_still_preserved(
        self, tmp_path
    ):
        """Edge case: a fork file that happens to have a docstring
        starting with the SAME prefix the shim does (but is otherwise
        a full body) must not be considered a shim and overwritten.

        This protects against a shim-replacement detection that's too
        loose. Per ``_SRE_PKB_SHIM_SENTINEL = '\"\"\"SRE — PKB shim.\"\"\"'``,
        the sentinel is a specific string. We don't actually use that
        sentinel for overwrite-or-leave decisions — ``ensure_sre_folder``
        bails on file existence alone — so this test PINS that simpler
        contract.
        """
        agents_dir = tmp_path / "agents" / "sre"
        agents_dir.mkdir(parents=True, exist_ok=True)

        # Looks superficially shim-like but is a full body fork.
        forked_content = '''"""SRE — PKB shim.

But actually this is a user fork — they kept the docstring.
"""

NAME = "ForkPretendingToBeShim"
WATCHERS = []
'''
        sre_py = agents_dir / "sre.py"
        sre_py.write_text(forked_content, encoding="utf-8")
        original_content = sre_py.read_text(encoding="utf-8")

        from arail.agents.builtin_seed import ensure_sre_folder
        ensure_sre_folder(pkb_root=tmp_path)

        # File must still match what the user wrote.
        assert sre_py.read_text(encoding="utf-8") == original_content, (
            "ensure_sre_folder bails on existence alone — must not "
            "overwrite even if the file resembles the shim"
        )

    def test_canonical_watchers_unchanged_after_fork_imported(self, tmp_path):
        """Importing a fork must NOT mutate the canonical module's
        WATCHERS list (no module-level side-effects via the fork)."""
        from arail.agents import _builtin_sre as canonical
        canonical_watchers_before = list(canonical.WATCHERS)

        agents_dir = tmp_path / "agents" / "sre"
        agents_dir.mkdir(parents=True, exist_ok=True)

        forked_content = '''"""Fork that does some import-time work."""

# This is a malicious-ish import that might mutate canonical.
# The fork-respect contract says canonical is untouched.
WATCHERS = []
'''
        (agents_dir / "sre.py").write_text(forked_content, encoding="utf-8")
        _import_by_path(
            agents_dir / "sre.py", f"_qa_forked_no_mutate_{id(tmp_path)}"
        )

        # Canonical WATCHERS list must be unchanged.
        canonical_watchers_after = list(canonical.WATCHERS)
        assert canonical_watchers_after == canonical_watchers_before, (
            "Importing a forked sre.py must NOT mutate canonical.WATCHERS"
        )
