"""QA — CVE/cleanup watcher mode-gating equivalence (architect priority #2).

The SRE repave (Loopback 2) moved the LAB_MODE read out of the PKB-only
``_sre_lab_mode`` (which did its own ``os.getenv`` chain) and into a
delegation: ``_sre_lab_mode()`` now calls ``arail.airgap.lab_mode()``.

The architect flagged this as the most likely place for a regression
to hide. These tests pin the equivalence — that mode-gating semantics
are unchanged from the pre-port behavior:

  Branch (a) — High/Critical CVE present → fires unconditionally
  Branch (b) — Medium-only → fires unconditionally
  Branch (c) — No-scan-in-24h+ → fires only in HYBRID mode
  Lab cleanup watcher → mode-agnostic (fires in either mode)

Test strategy: monkeypatch the data dir, write fixtures that trigger
each branch, then flip LAB_MODE between airgapped and hybrid and assert
the right Observation comes back.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


def _seed_scan(data_dir: Path, payload: dict) -> Path:
    """Write a fake last_scan.json under data_dir/security/."""
    sec = data_dir / "security"
    sec.mkdir(parents=True, exist_ok=True)
    p = sec / "last_scan.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _patch_data_dir(monkeypatch, tmp_path: Path) -> None:
    """Make ``_sre_data_dir()`` return tmp_path."""
    import arail.agents._builtin_sre as sre_mod
    monkeypatch.setattr(sre_mod, "_sre_data_dir", lambda: tmp_path)


# ──────────────────────────────────────────────────────────────────────
# Branch (a) — High/Critical present → fires regardless of mode
# ──────────────────────────────────────────────────────────────────────

class TestCveBranchA_HighCritical:
    def test_fires_in_airgapped_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_data_dir(monkeypatch, tmp_path)
        _seed_scan(tmp_path, {
            "last_run_ts": datetime.now(timezone.utc).isoformat(),
            "summary": {"critical": 1, "high": 0, "medium": 0},
        })

        from arail.agents._builtin_sre import _watch_dependency_vulnerabilities
        obs = _watch_dependency_vulnerabilities()
        assert obs is not None, "Branch (a) must fire in airgapped"
        assert obs.severity == "error"
        assert "Critical" in obs.fact or "critical" in obs.fact.lower() or "1" in obs.fact

    def test_fires_in_hybrid_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "hybrid")
        _patch_data_dir(monkeypatch, tmp_path)
        _seed_scan(tmp_path, {
            "last_run_ts": datetime.now(timezone.utc).isoformat(),
            "summary": {"critical": 0, "high": 2, "medium": 5},
        })

        from arail.agents._builtin_sre import _watch_dependency_vulnerabilities
        obs = _watch_dependency_vulnerabilities()
        assert obs is not None, "Branch (a) must fire in hybrid"
        assert obs.severity == "error"


# ──────────────────────────────────────────────────────────────────────
# Branch (b) — Medium-only → fires regardless of mode
# ──────────────────────────────────────────────────────────────────────

class TestCveBranchB_MediumOnly:
    def test_fires_in_airgapped_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_data_dir(monkeypatch, tmp_path)
        _seed_scan(tmp_path, {
            "last_run_ts": datetime.now(timezone.utc).isoformat(),
            "summary": {"critical": 0, "high": 0, "medium": 3},
        })

        from arail.agents._builtin_sre import _watch_dependency_vulnerabilities
        obs = _watch_dependency_vulnerabilities()
        assert obs is not None, "Branch (b) must fire in airgapped"
        assert obs.severity == "warn"

    def test_fires_in_hybrid_mode(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "hybrid")
        _patch_data_dir(monkeypatch, tmp_path)
        _seed_scan(tmp_path, {
            "last_run_ts": datetime.now(timezone.utc).isoformat(),
            "summary": {"critical": 0, "high": 0, "medium": 3},
        })

        from arail.agents._builtin_sre import _watch_dependency_vulnerabilities
        obs = _watch_dependency_vulnerabilities()
        assert obs is not None, "Branch (b) must fire in hybrid"
        assert obs.severity == "warn"


# ──────────────────────────────────────────────────────────────────────
# Branch (c) — No-scan-in-24h → fires ONLY in hybrid (architect priority)
# ──────────────────────────────────────────────────────────────────────

class TestCveBranchC_NoScan24h:
    """Branch (c) is the load-bearing mode-gating test: in airgapped,
    we don't expect users to run cloud-dependent CVE scans, so the
    nag must NOT fire. In hybrid, scan freshness is the user's
    responsibility and the nag fires."""

    def test_no_file_silent_in_airgapped(self, monkeypatch, tmp_path):
        """Airgapped + no last_scan.json → no nag (file-missing branch)."""
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_data_dir(monkeypatch, tmp_path)
        # Don't seed a scan file.
        from arail.agents._builtin_sre import _watch_dependency_vulnerabilities
        obs = _watch_dependency_vulnerabilities()
        assert obs is None, (
            "Branch (c) must NOT fire in airgapped (no nag when no scan ever ran)"
        )

    def test_no_file_nags_in_hybrid(self, monkeypatch, tmp_path):
        """Hybrid + no last_scan.json → nag fires."""
        monkeypatch.setenv("LAB_MODE", "hybrid")
        _patch_data_dir(monkeypatch, tmp_path)
        from arail.agents._builtin_sre import _watch_dependency_vulnerabilities
        obs = _watch_dependency_vulnerabilities()
        assert obs is not None, "Branch (c) must fire in hybrid (no scan)"
        assert obs.severity == "warn"
        assert "scan" in obs.fact.lower()

    def test_stale_scan_silent_in_airgapped(self, monkeypatch, tmp_path):
        """Airgapped + scan older than 24h with no findings → no nag."""
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_data_dir(monkeypatch, tmp_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _seed_scan(tmp_path, {
            "last_run_ts": old_ts,
            "summary": {"critical": 0, "high": 0, "medium": 0},
        })

        from arail.agents._builtin_sre import _watch_dependency_vulnerabilities
        obs = _watch_dependency_vulnerabilities()
        assert obs is None, (
            "Stale scan in airgapped must NOT nag (offline-friendly)"
        )

    def test_stale_scan_nags_in_hybrid(self, monkeypatch, tmp_path):
        """Hybrid + scan older than 24h with no findings → nag fires."""
        monkeypatch.setenv("LAB_MODE", "hybrid")
        _patch_data_dir(monkeypatch, tmp_path)
        old_ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        _seed_scan(tmp_path, {
            "last_run_ts": old_ts,
            "summary": {"critical": 0, "high": 0, "medium": 0},
        })

        from arail.agents._builtin_sre import _watch_dependency_vulnerabilities
        obs = _watch_dependency_vulnerabilities()
        assert obs is not None, "Branch (c) must nag in hybrid for stale scan"
        assert obs.severity == "warn"


# ──────────────────────────────────────────────────────────────────────
# _sre_lab_mode delegates to arail.airgap.lab_mode (canonical SoT)
# ──────────────────────────────────────────────────────────────────────

class TestSreLabModeDelegation:
    """The repave moved _sre_lab_mode() from a self-contained
    os.getenv chain to a delegation. Verify the delegation is correct."""

    def test_returns_airgapped_when_lab_mode_unset(self, monkeypatch):
        monkeypatch.delenv("LAB_MODE", raising=False)
        monkeypatch.delenv("ARAIL_MODE", raising=False)
        from arail.agents._builtin_sre import _sre_lab_mode
        assert _sre_lab_mode() == "airgapped"

    def test_returns_airgapped_for_unknown_value(self, monkeypatch):
        # Per arail.airgap.lab_mode: anything not 'hybrid' → 'airgapped'.
        monkeypatch.setenv("LAB_MODE", "weirdvalue")
        from arail.agents._builtin_sre import _sre_lab_mode
        assert _sre_lab_mode() == "airgapped"

    def test_returns_hybrid_when_explicit(self, monkeypatch):
        monkeypatch.setenv("LAB_MODE", "hybrid")
        from arail.agents._builtin_sre import _sre_lab_mode
        assert _sre_lab_mode() == "hybrid"

    def test_arail_mode_fallback_works(self, monkeypatch):
        """ARAIL_MODE is the secondary env per the canonical fallback chain."""
        monkeypatch.delenv("LAB_MODE", raising=False)
        monkeypatch.setenv("ARAIL_MODE", "hybrid")
        from arail.agents._builtin_sre import _sre_lab_mode
        assert _sre_lab_mode() == "hybrid"

    def test_uppercase_HYBRID_collapses_to_hybrid(self, monkeypatch):
        """Per arail.airgap.lab_mode strip+lower normalization."""
        monkeypatch.setenv("LAB_MODE", "  HYBRID  ")
        from arail.agents._builtin_sre import _sre_lab_mode
        assert _sre_lab_mode() == "hybrid"

    def test_delegation_uses_canonical_module(self, monkeypatch):
        """Pin: _sre_lab_mode reaches into arail.airgap.lab_mode (not its
        own env-read). If a future refactor inlines the env reads back
        into SRE, this test fails."""
        from arail.agents import _builtin_sre
        from arail import airgap

        # Use a sentinel to verify the delegation path.
        called = {"n": 0}
        original = airgap.lab_mode

        def _spy():
            called["n"] += 1
            return original()

        monkeypatch.setattr(airgap, "lab_mode", _spy)
        _builtin_sre._sre_lab_mode()
        assert called["n"] >= 1, (
            "_sre_lab_mode must delegate to airgap.lab_mode — "
            "otherwise canonical-vs-PKB drift returns"
        )


# ──────────────────────────────────────────────────────────────────────
# Lab cleanup watcher — mode-agnostic
# ──────────────────────────────────────────────────────────────────────

class TestLabCleanupWatcherModeAgnostic:
    """``_watch_lab_cleanup`` does NOT inspect lab_mode. Pin: fires in
    both modes when threshold exceeded; doesn't fire when threshold
    not exceeded — regardless of mode."""

    def test_no_cache_returns_none_in_airgapped(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        # Point LAB_ROOT at tmp_path so .wiki-cache won't exist.
        import arail.config
        monkeypatch.setattr(arail.config, "LAB_ROOT", str(tmp_path))
        from arail.agents._builtin_sre import _watch_lab_cleanup
        assert _watch_lab_cleanup() is None

    def test_no_cache_returns_none_in_hybrid(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "hybrid")
        import arail.config
        monkeypatch.setattr(arail.config, "LAB_ROOT", str(tmp_path))
        from arail.agents._builtin_sre import _watch_lab_cleanup
        assert _watch_lab_cleanup() is None

    def test_threshold_exceeded_fires_in_airgapped(self, monkeypatch, tmp_path):
        """Pin: cleanup watcher is mode-agnostic; fires in airgapped too."""
        monkeypatch.setenv("LAB_MODE", "airgapped")
        monkeypatch.setenv("LAB_CLEANUP_CACHE_MAX_GB", "0.0000001")  # ~107 bytes
        import arail.config
        monkeypatch.setattr(arail.config, "LAB_ROOT", str(tmp_path))
        cache = tmp_path / "pkb" / ".wiki-cache"
        cache.mkdir(parents=True, exist_ok=True)
        # Write a small file > 107 bytes.
        (cache / "junk.bin").write_bytes(b"x" * 1024)

        from arail.agents._builtin_sre import _watch_lab_cleanup
        obs = _watch_lab_cleanup()
        assert obs is not None, "Cleanup watcher must fire in airgapped too"
        assert "Wiki cache" in obs.fact

    def test_threshold_exceeded_fires_in_hybrid(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "hybrid")
        monkeypatch.setenv("LAB_CLEANUP_CACHE_MAX_GB", "0.0000001")
        import arail.config
        monkeypatch.setattr(arail.config, "LAB_ROOT", str(tmp_path))
        cache = tmp_path / "pkb" / ".wiki-cache"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "junk.bin").write_bytes(b"x" * 1024)

        from arail.agents._builtin_sre import _watch_lab_cleanup
        obs = _watch_lab_cleanup()
        assert obs is not None, "Cleanup watcher must fire in hybrid too"
