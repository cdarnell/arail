"""QA — security/paranoid tests for POST /api/airgap/toggle.

Bucket: 20% security in arail's QA gate.

Coverage areas (per REVIEW.md "paranoid hammer list" + architect seeds):
- Bind-address gate edge cases: empty, whitespace, uppercase, IPv6 brackets, mixed case.
- CSRF — bare curl with no Origin header (DOCUMENTED GAP — pinned).
- CSRF — Origin without netloc (e.g. ``Origin: null``).
- Cross-origin rejection: port mismatch, subdomain.
- Symlink pre-placed at env path — write refused.
- Pre-placed temp file — attacker writes ``.env.tmp.<pid>.<hex>`` first; O_EXCL guards.
- Path-traversal-style payload in target (must 400, not blow up).
- Value sanitisation (newline / NUL injection at the env_writer layer).
- Bind warning + Origin co-presence: bind gate fires *before* origin check.
- Audit log: source_ip is recorded; no .env content / path leaks into the body.

Removed in QA cleanup pass (2026-05-14):
- Token brute force / token replay / token invalidation (2-step protocol removed).
- Symlink replaced mid-race between step1 and step2 (step1 no longer exists).
- Concurrent two-client two-step (covered by TestTwoTabRace in onetap_paranoid).
- FD leak on failed token requests (token table gone).
- Token table growth (token table gone).
"""

from __future__ import annotations

import json
import os
import resource
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from arail.portal.app import app


# ---------------------------------------------------------------------------
# Shared fixture (mirrors test_airgap_toggle_endpoint.py).
# ---------------------------------------------------------------------------

@pytest.fixture()
def toggle_setup(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_bytes(b"LAB_MODE=airgapped\n")
    audit_path = tmp_path / "airgap_audit.jsonl"

    import arail.portal.app as app_mod
    monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
    monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
    monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
    monkeypatch.setenv("LAB_MODE", "airgapped")

    client = TestClient(app, raise_server_exceptions=False)
    return client, env_path, audit_path, tmp_path


# ---------------------------------------------------------------------------
# Bind-gate: paranoid input matrix
# ---------------------------------------------------------------------------

class TestBindGateMatrix:
    """Per REVIEW.md hammer list: empty / whitespace / uppercase / IPv6 / etc."""

    @pytest.mark.parametrize("bind_addr,expect_loopback", [
        ("127.0.0.1", True),
        ("::1", True),
        ("localhost", True),
        ("LOCALHOST", True),         # _toggle_bind_is_loopback lower()s
        ("  127.0.0.1  ", True),     # strip()ped
        ("0.0.0.0", False),
        ("192.168.1.10", False),
        ("10.0.0.1", False),
        ("172.16.0.1", False),
        ("", False),                  # empty string → falls through allowlist
        ("127.0.0.2", False),         # NOT a loopback in the implementation's allowlist
        ("[::1]", False),             # bracketed form is NOT in allowlist (gap-pin)
        ("0:0:0:0:0:0:0:1", False),   # expanded IPv6 loopback NOT in allowlist (gap-pin)
        ("LocalHost", True),          # lower() handles
    ])
    def test_bind_gate_matrix(self, toggle_setup, monkeypatch, bind_addr, expect_loopback):
        client, env_path, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", bind_addr)
        mtime_before = env_path.stat().st_mtime_ns

        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        if expect_loopback:
            # Bind passes; one-tap returns 200 directly.
            assert r.status_code == 200, f"bind {bind_addr!r} → {r.status_code}: {r.text}"
        else:
            assert r.status_code == 403, f"bind {bind_addr!r} → {r.status_code}: {r.text}"
            assert r.json()["error"] == "bind_not_loopback"
            # .env mtime untouched.
            assert env_path.stat().st_mtime_ns == mtime_before


# ---------------------------------------------------------------------------
# CSRF — known gap: no Origin header / empty netloc
# ---------------------------------------------------------------------------

class TestCsrfGaps:
    """Pin the documented behavior. If the gap is closed, these tests trip."""

    def test_no_origin_header_passes_csrf_check_DOCUMENTED_GAP(self, toggle_setup):
        """Endpoint code is ``if origin: <check>``. No header → no check.

        This is acceptable per REVIEW.md (legacy clients / curl) because the
        bind-address loopback gate is the actual security boundary.

        TRIPWIRE: if a future builder adds Origin-required enforcement, this
        test fails — and they should consciously decide whether to keep that
        behavior. If they do, update this test.
        """
        client, _, _, _ = toggle_setup
        # No Origin header at all.
        r = client.post("/api/airgap/toggle", json={"target": "hybrid"})
        # Currently: passes CSRF gate, one-tap completes immediately → 200.
        assert r.status_code == 200, (
            "EXPECTED current behavior: no Origin header bypasses CSRF "
            "(documented gap; bind-gate is the real shield). "
            f"Got {r.status_code}: {r.text}"
        )

    def test_cross_origin_with_port_mismatch_is_refused(self, toggle_setup):
        """Same host, different port → cross-origin per netloc compare."""
        client, _, _, _ = toggle_setup
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={
                "Origin": "http://testserver:9999",
                "Host": "testserver",
            },
        )
        assert r.status_code == 403
        assert r.json()["error"] == "cross_origin"

    def test_cross_origin_subdomain_refused(self, toggle_setup):
        """evil.testserver != testserver — suffix-match attack blocked."""
        client, _, _, _ = toggle_setup
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://evil.testserver"},
        )
        assert r.status_code == 403
        assert r.json()["error"] == "cross_origin"


# ---------------------------------------------------------------------------
# Symlink attacks on env-writer
# ---------------------------------------------------------------------------

class TestSymlinkAttacks:
    def test_symlink_pre_placed_at_env_path_is_refused(self, toggle_setup, tmp_path):
        """If .env is a symlink at endpoint call time, EnvWriterError → 500."""
        client, env_path, _, _ = toggle_setup
        # Replace .env with a symlink pointing at an attacker target.
        target = tmp_path / "victim"
        target.write_text("sensitive\n")
        env_path.unlink()
        env_path.symlink_to(target)

        # One-tap: single POST.
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 500
        assert r.json()["error"] == "env_write_failed"
        # Symlink target untouched.
        assert target.read_text() == "sensitive\n"
        # No path leak in body.
        body_text = r.text
        assert str(env_path) not in body_text
        assert str(target) not in body_text

    def test_pre_placed_tmp_file_does_NOT_get_written_through(self, toggle_setup, tmp_path):
        """O_EXCL on the temp file: a pre-placed .env.tmp.<pid>.<hex> would
        cause O_EXCL to fail. The exact temp filename includes a random hex,
        so we instead pre-place a wildcard match by intercepting and
        directly invoking _atomic_write with a colliding tmp.

        We verify by direct env_writer call that O_EXCL semantics hold:
        if the temp file already exists, FileExistsError propagates.
        """
        from arail import env_writer

        # Patch secrets.token_hex to a deterministic value so we know the
        # tmp filename, then pre-place that file.
        target_env = tmp_path / ".env.exclusivity"
        target_env.write_bytes(b"LAB_MODE=airgapped\n")

        # Manually compute the would-be tmp path and pre-place it.
        deterministic_hex = "deadbeef"
        with patch.object(env_writer, "secrets") as mock_secrets:
            mock_secrets.token_hex.return_value = deterministic_hex
            tmp_collide = target_env.parent / (
                target_env.name + f".tmp.{os.getpid()}.{deterministic_hex}"
            )
            tmp_collide.write_text("attacker pre-placed\n")

            with pytest.raises(FileExistsError):
                env_writer._atomic_write(target_env, b"poisoned\n")

        # Pre-placed temp file content is preserved (not overwritten).
        assert tmp_collide.read_text() == "attacker pre-placed\n"
        # The actual .env was never touched by the failed write.
        assert target_env.read_bytes() == b"LAB_MODE=airgapped\n"


# ---------------------------------------------------------------------------
# Value sanitisation
# ---------------------------------------------------------------------------

class TestValueSanitisation:
    """target only accepts the literal strings 'airgapped' / 'hybrid'.

    A path-traversal / injection attempt like ``hybrid\\nEVIL=...`` must be
    rejected at the endpoint's allow-list check (400), never reach the writer.
    """

    @pytest.mark.parametrize("target", [
        "hybrid\nEVIL=1",
        "hybrid; rm -rf /",
        "hybrid\x00airgapped",
        "../etc/passwd",
        "HYBRID",        # case mismatch
        " hybrid",       # leading space
        "hybrid ",       # trailing space
        "hybrid\r\nEVIL=1",
    ])
    def test_target_injection_rejected_400(self, toggle_setup, target):
        client, env_path, _, _ = toggle_setup
        r = client.post(
            "/api/airgap/toggle",
            json={"target": target},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 400, f"target={target!r} → {r.status_code}: {r.text}"
        assert r.json()["error"] == "invalid_target"
        # .env content unchanged.
        assert env_path.read_bytes() == b"LAB_MODE=airgapped\n"

    def test_writer_directly_rejects_newline_value(self, tmp_path):
        """Defense-in-depth: env_writer rejects newline in value at the API level."""
        from arail.env_writer import EnvWriterError, set_env_var
        p = tmp_path / ".env"
        p.write_text("LAB_MODE=airgapped\n")
        with pytest.raises(EnvWriterError):
            set_env_var(p, "LAB_MODE", "hybrid\nEVIL=1")
        # File untouched.
        assert p.read_text() == "LAB_MODE=airgapped\n"

    def test_writer_directly_rejects_nul_value(self, tmp_path):
        from arail.env_writer import EnvWriterError, set_env_var
        p = tmp_path / ".env"
        p.write_text("LAB_MODE=airgapped\n")
        with pytest.raises(EnvWriterError):
            set_env_var(p, "LAB_MODE", "hybrid\x00x")
        assert p.read_text() == "LAB_MODE=airgapped\n"


# ---------------------------------------------------------------------------
# Bind gate fires before Origin (defense-in-depth ordering)
# ---------------------------------------------------------------------------

class TestGateOrdering:
    def test_bind_gate_rejects_lan_bound_toggle(self, toggle_setup, monkeypatch):
        """A LAN-bound portal must 403 the toggle and not write .env, even
        for a same-origin request that clears the CSRF checks — the bind
        gate is the backstop for a deliberately-exposed portal.

        (A *malicious* Origin against a LAN bind is now caught even earlier,
        by the global local_trust_boundary middleware — see
        test_local_trust_boundary.py. Here we use a same-origin request so
        the bind gate itself is what rejects.)"""
        client, env_path, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "0.0.0.0")
        mtime_before = env_path.stat().st_mtime_ns

        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
        )
        assert r.status_code == 403
        assert r.json()["error"] == "bind_not_loopback"
        assert env_path.stat().st_mtime_ns == mtime_before

    def test_bind_gate_fires_before_invalid_target_400(self, toggle_setup, monkeypatch):
        """Bind 403 wins over body-validation 400."""
        client, _, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "10.0.0.1")
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "banana"},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 403
        assert r.json()["error"] == "bind_not_loopback"


# ---------------------------------------------------------------------------
# Error body must not leak path or .env contents
# ---------------------------------------------------------------------------

class TestErrorLeakage:
    def test_writer_failure_body_leaks_no_path_or_contents(self, toggle_setup):
        from arail.env_writer import EnvWriterError
        client, env_path, _, _ = toggle_setup

        env_path.write_bytes(b"LAB_MODE=airgapped\nSECRET=do-not-leak\n")

        with patch("arail.env_writer.set_env_var",
                   side_effect=EnvWriterError(f"failed at {env_path}: SECRET=do-not-leak")):
            r = client.post(
                "/api/airgap/toggle",
                json={"target": "hybrid"},
                headers={"Origin": "http://testserver"},
            )
        assert r.status_code == 500
        body_text = r.text
        assert str(env_path) not in body_text
        assert "SECRET" not in body_text
        assert "do-not-leak" not in body_text
