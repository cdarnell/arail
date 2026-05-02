"""SRE new-watcher tests — dependency-vulnerabilities + lab-cleanup.

Architect MUST-HIT #4: SRE CVE watcher branches (a/b/c):
  (a) summary.critical + summary.high > 0 → severity="error" Observation
  (b) summary.medium > 0 only → severity="warn" Observation
  (c) Stale scan (>24h old) AND LAB_MODE=hybrid AND no findings →
      "you should run a scan" Observation
  Plus cooldown_key fingerprinting: re-running with identical scan → None.

Other coverage:
  - LAB_MODE → ARAIL_MODE → "airgapped" fallback chain (E5).
  - Cleanup watcher threshold respect (LAB_CLEANUP_CACHE_MAX_GB).
  - Watcher returns None gracefully when files / dirs missing (E1).
  - WATCHERS list still includes the 3 pre-existing watchers (regression).
"""
from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixture — fresh sre module + isolated DATA_DIR + LAB_ROOT
# ---------------------------------------------------------------------------

@pytest.fixture()
def sre(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    lab_root = tmp_path / "lab"
    pkb_root = lab_root / "pkb"
    cache_root = pkb_root / ".wiki-cache"
    for p in (data_dir / "security", cache_root):
        p.mkdir(parents=True)
    monkeypatch.setenv("ARAIL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("LAB_ROOT", str(lab_root))
    monkeypatch.setenv("LAB_PKB", str(pkb_root))

    import importlib.util  # bring submodule in BEFORE reload-shadowing
    import sys as _sys
    import arail.config as _cfg
    importlib.reload(_cfg)

    # Import sre.py from the on-disk path; it lives in lab/pkb/agents/sre/
    # outside the importable arail package.
    sre_path = Path(__file__).resolve().parent.parent / "lab" / "pkb" / "agents" / "sre" / "sre.py"
    assert sre_path.exists(), f"sre.py missing at {sre_path}"
    spec = importlib.util.spec_from_file_location("_sre_under_test", sre_path)
    mod = importlib.util.module_from_spec(spec)
    _sys.modules["_sre_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod, data_dir, cache_root


# ---------------------------------------------------------------------------
# CVE watcher branches
# ---------------------------------------------------------------------------

def _write_scan(data_dir: Path, **scan_overrides) -> dict:
    base = {
        "available": True,
        "last_run_ts": datetime.now(timezone.utc).isoformat(),
        "trigger": "manual",
        "summary": {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0},
        "findings": [],
        "tool": "pip-audit",
        "tool_version": "2.7.3",
        "auto_scan_enabled": False,
        "error": None,
    }
    base.update(scan_overrides)
    p = data_dir / "security" / "last_scan.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(base))
    return base


def test_cve_watcher_branch_a_high_critical(sre):
    """Branch (a): critical + high > 0 → severity='error'."""
    mod, data_dir, _ = sre
    _write_scan(data_dir, summary={"critical": 1, "high": 2, "medium": 0, "low": 0, "total": 3})
    obs = mod._watch_dependency_vulnerabilities()
    assert obs is not None
    assert obs.watcher == "dependency-vulnerabilities"
    assert obs.severity == "error"
    assert "3 High/Critical" in obs.fact
    # cooldown_key must include the timestamp + counts
    assert obs.cooldown_key.startswith("cve::")
    assert "::1::2" in obs.cooldown_key  # n_crit::n_high


def test_cve_watcher_branch_b_medium_only(sre):
    """Branch (b): medium > 0 only → severity='warn'."""
    mod, data_dir, _ = sre
    _write_scan(data_dir, summary={"critical": 0, "high": 0, "medium": 4, "low": 0, "total": 4})
    obs = mod._watch_dependency_vulnerabilities()
    assert obs is not None
    assert obs.severity == "warn"
    assert "4 Medium" in obs.fact
    assert obs.cooldown_key.startswith("cve::med::")


def test_cve_watcher_branch_c_no_scan_file_in_hybrid(monkeypatch, sre):
    """Branch (c) — variant 1: no last_scan.json AND hybrid → nudge."""
    mod, data_dir, _ = sre
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    # Don't write the file.
    (data_dir / "security" / "last_scan.json").unlink(missing_ok=True)

    obs = mod._watch_dependency_vulnerabilities()
    assert obs is not None
    assert obs.severity == "warn"
    assert "No security scan in 24h+" in obs.fact
    assert obs.cooldown_key.startswith("cve::nag::")


def test_cve_watcher_branch_c_stale_scan_in_hybrid(monkeypatch, sre):
    """Branch (c) — variant 2: scan exists but >24h old in hybrid → nudge."""
    mod, data_dir, _ = sre
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    old_ts = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
    _write_scan(data_dir, last_run_ts=old_ts,
                summary={"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0})

    obs = mod._watch_dependency_vulnerabilities()
    assert obs is not None
    assert obs.severity == "warn"
    assert "No security scan" in obs.fact


def test_cve_watcher_no_nudge_in_airgapped_when_no_scan(monkeypatch, sre):
    """Airgapped + no scan → None (no nudge — airgapped doesn't expect scans)."""
    mod, data_dir, _ = sre
    monkeypatch.setenv("LAB_MODE", "airgapped")
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    (data_dir / "security" / "last_scan.json").unlink(missing_ok=True)

    obs = mod._watch_dependency_vulnerabilities()
    assert obs is None


def test_cve_watcher_no_obs_when_recent_clean_scan(monkeypatch, sre):
    """Clean scan in the last hour → None even in hybrid (no nudge needed)."""
    mod, data_dir, _ = sre
    monkeypatch.setenv("LAB_MODE", "hybrid")
    _write_scan(data_dir,
                last_run_ts=datetime.now(timezone.utc).isoformat(),
                summary={"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0})
    obs = mod._watch_dependency_vulnerabilities()
    assert obs is None


# ---------------------------------------------------------------------------
# Cooldown fingerprint behaviour
# ---------------------------------------------------------------------------

def test_cve_watcher_identical_scan_yields_identical_cooldown_key(sre):
    """Two invocations with identical scan content → identical cooldown_key.

    The SRE loop suppresses the second emit by comparing the key against
    the last-said timestamp.  Identical key → cooldown holds → no re-emit.
    """
    mod, data_dir, _ = sre
    ts = "2026-05-01T12:00:00+00:00"
    _write_scan(data_dir, last_run_ts=ts,
                summary={"critical": 1, "high": 0, "medium": 0, "low": 0, "total": 1})
    obs1 = mod._watch_dependency_vulnerabilities()
    obs2 = mod._watch_dependency_vulnerabilities()
    assert obs1.cooldown_key == obs2.cooldown_key


def test_cve_watcher_new_scan_changes_cooldown_key(sre):
    """A new scan timestamp re-fires (different cooldown_key)."""
    mod, data_dir, _ = sre
    _write_scan(data_dir, last_run_ts="2026-05-01T12:00:00+00:00",
                summary={"critical": 1, "high": 0, "medium": 0, "low": 0, "total": 1})
    obs1 = mod._watch_dependency_vulnerabilities()
    _write_scan(data_dir, last_run_ts="2026-05-01T13:00:00+00:00",
                summary={"critical": 1, "high": 0, "medium": 0, "low": 0, "total": 1})
    obs2 = mod._watch_dependency_vulnerabilities()
    assert obs1.cooldown_key != obs2.cooldown_key


def test_cve_watcher_same_ts_diff_counts_changes_key(sre):
    """Different finding counts → different key (re-fires)."""
    mod, data_dir, _ = sre
    _write_scan(data_dir, last_run_ts="2026-05-01T12:00:00+00:00",
                summary={"critical": 1, "high": 0, "medium": 0, "low": 0, "total": 1})
    obs1 = mod._watch_dependency_vulnerabilities()
    _write_scan(data_dir, last_run_ts="2026-05-01T12:00:00+00:00",
                summary={"critical": 1, "high": 5, "medium": 0, "low": 0, "total": 6})
    obs2 = mod._watch_dependency_vulnerabilities()
    assert obs1.cooldown_key != obs2.cooldown_key


# ---------------------------------------------------------------------------
# E5 — LAB_MODE → ARAIL_MODE → airgapped fallback chain
# ---------------------------------------------------------------------------

def test_sre_lab_mode_reads_lab_mode_first(monkeypatch, sre):
    mod, _, _ = sre
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ARAIL_MODE", "airgapped")
    assert mod._sre_lab_mode() == "hybrid"


def test_sre_lab_mode_falls_back_to_arail_mode(monkeypatch, sre):
    mod, _, _ = sre
    monkeypatch.delenv("LAB_MODE", raising=False)
    monkeypatch.setenv("ARAIL_MODE", "hybrid")
    assert mod._sre_lab_mode() == "hybrid"


def test_sre_lab_mode_defaults_to_airgapped(monkeypatch, sre):
    mod, _, _ = sre
    monkeypatch.delenv("LAB_MODE", raising=False)
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    assert mod._sre_lab_mode() == "airgapped"


def test_sre_lab_mode_normalises_case_and_whitespace(monkeypatch, sre):
    mod, _, _ = sre
    monkeypatch.setenv("LAB_MODE", "  HYBRID  ")
    assert mod._sre_lab_mode() == "hybrid"


# ---------------------------------------------------------------------------
# Robustness: bad input
# ---------------------------------------------------------------------------

def test_cve_watcher_unreadable_scan_returns_none(sre):
    """Corrupt JSON in last_scan.json → return None, never raise."""
    mod, data_dir, _ = sre
    (data_dir / "security" / "last_scan.json").write_text("{not-json")
    obs = mod._watch_dependency_vulnerabilities()
    assert obs is None


def test_cve_watcher_bad_timestamp_does_not_crash(monkeypatch, sre):
    """E2: parse-error on last_run_ts → treat as unknown age, no crash."""
    mod, data_dir, _ = sre
    monkeypatch.setenv("LAB_MODE", "hybrid")
    _write_scan(data_dir, last_run_ts="not-an-iso-string",
                summary={"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0})
    # Should not raise; behaviour is to skip the nudge branch on bad ts.
    obs = mod._watch_dependency_vulnerabilities()
    # Either None (no findings, unknown age) or the nudge — both are
    # acceptable as long as nothing crashed.
    assert obs is None or obs.severity == "warn"


# ---------------------------------------------------------------------------
# Cleanup watcher threshold
# ---------------------------------------------------------------------------

def _write_bytes(path: Path, n_bytes: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        # Write in chunks to avoid 100GB-of-zero memory issues; here n_bytes
        # is small enough.
        f.write(b"\0" * n_bytes)


def test_cleanup_watcher_below_threshold_returns_none(monkeypatch, sre):
    """cache_gb < threshold → None."""
    mod, _, cache_root = sre
    monkeypatch.setenv("LAB_CLEANUP_CACHE_MAX_GB", "5")
    _write_bytes(cache_root / "small.bin", 1024 * 1024)  # 1 MB
    assert mod._watch_lab_cleanup() is None


def test_cleanup_watcher_above_threshold_warn(monkeypatch, sre):
    """cache_gb > threshold (but <2x) → warn."""
    mod, _, cache_root = sre
    # 2 MB file with a 1.5 MB threshold: above threshold, below 2x.
    one_mb = 1024 * 1024
    threshold_gb = 1.5 * one_mb / (2 ** 30)  # 1.5 MB expressed in GB
    monkeypatch.setenv("LAB_CLEANUP_CACHE_MAX_GB", str(threshold_gb))
    _write_bytes(cache_root / "blob.bin", 2 * one_mb)  # 2 MB
    obs = mod._watch_lab_cleanup()
    assert obs is not None
    assert obs.watcher == "lab-cleanup"
    assert obs.severity == "warn", (
        f"expected warn for 2MB > 1.5MB (less than 2x); got {obs.severity}"
    )
    assert "[CLEANUP]" in obs.fact


def test_cleanup_watcher_double_threshold_error(monkeypatch, sre):
    """cache_gb > 2 * threshold → error."""
    mod, _, cache_root = sre
    monkeypatch.setenv("LAB_CLEANUP_CACHE_MAX_GB", "0.0001")  # 100 KB
    _write_bytes(cache_root / "huge.bin", 4 * 1024 * 1024)  # 4 MB >> 2*threshold
    obs = mod._watch_lab_cleanup()
    assert obs is not None
    assert obs.severity == "error"


def test_cleanup_watcher_no_cache_dir_returns_none(monkeypatch, sre):
    """cache_root missing entirely → None, no crash."""
    mod, _, cache_root = sre
    # Remove the cache root.
    import shutil as _sh
    _sh.rmtree(cache_root)
    assert mod._watch_lab_cleanup() is None


def test_cleanup_watcher_garbage_threshold_falls_back_to_5gb(monkeypatch, sre):
    """LAB_CLEANUP_CACHE_MAX_GB=garbage → default 5 GB threshold."""
    mod, _, cache_root = sre
    monkeypatch.setenv("LAB_CLEANUP_CACHE_MAX_GB", "not-a-float")
    _write_bytes(cache_root / "small.bin", 1024)  # 1 KB; well under 5 GB
    # Should NOT alert at 5 GB default.
    assert mod._watch_lab_cleanup() is None


# ---------------------------------------------------------------------------
# Regression: pre-existing watchers still in WATCHERS
# ---------------------------------------------------------------------------

def test_existing_three_watchers_still_present(sre):
    """Regression: the 3 pre-existing watchers must NOT have been removed."""
    mod, _, _ = sre
    names = [w.__name__ for w in mod.WATCHERS]
    for required in ("_watch_recent_errors", "_watch_crash_recurrence", "_watch_service_health"):
        assert required in names, f"Pre-existing watcher {required} missing from WATCHERS"


def test_new_two_watchers_in_watchers_list(sre):
    mod, _, _ = sre
    names = [w.__name__ for w in mod.WATCHERS]
    assert "_watch_dependency_vulnerabilities" in names
    assert "_watch_lab_cleanup" in names


def test_watchers_total_count(sre):
    """5 watchers total: 3 original + 2 new."""
    mod, _, _ = sre
    assert len(mod.WATCHERS) == 5
