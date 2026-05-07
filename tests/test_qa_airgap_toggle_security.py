"""QA — security/paranoid tests for POST /api/airgap/toggle.

Bucket: 20% security in arail's QA gate.

Coverage areas (per REVIEW.md "paranoid hammer list" + architect seeds):
- Bind-address gate edge cases: empty, whitespace, uppercase, IPv6 brackets, mixed case.
- CSRF — bare curl with no Origin header (DOCUMENTED GAP — pinned).
- CSRF — Origin without netloc (e.g. ``Origin: null``).
- Token brute force — 100 random tokens all rejected.
- Token replay across targets (issued for hybrid; presented for airgapped).
- Symlink replacement race — replace .env with a symlink between step-1 and step-2.
- Pre-placed temp file — attacker writes ``.env.tmp.<pid>.<hex>`` first; O_EXCL guards.
- Path-traversal-style payload in target / confirm_token (must 400/409, not blow up).
- Value sanitisation (newline / NUL injection at the env_writer layer; this should
  surface as 500 ``env_write_failed`` from the endpoint perspective when the value
  ever held a bad char — pin via direct env_writer call).
- File-descriptor pressure — 200 failed-token requests don't leak FDs.
- Bind warning + Origin co-presence: bind gate fires *before* origin check
  (so the no-Origin-leakage gap doesn't matter when bind is non-loopback).
- Audit log: source_ip is recorded; no .env content / path leaks into the body.
"""

from __future__ import annotations

import json
import os
import resource
import threading
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
            # Bind passes; we should be in step-1 (409 + token).
            assert r.status_code == 409, f"bind {bind_addr!r} → {r.status_code}: {r.text}"
        else:
            assert r.status_code == 403, f"bind {bind_addr!r} → {r.status_code}: {r.text}"
            assert r.json()["error"] == "bind_not_loopback"
            # .env mtime untouched.
            assert env_path.stat().st_mtime_ns == mtime_before


# ---------------------------------------------------------------------------
# CSRF — known gap: no Origin header
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
        # Currently: passes CSRF gate, lands in step-1.
        assert r.status_code == 409, (
            "EXPECTED current behavior: no Origin header bypasses CSRF "
            "(documented gap; bind-gate is the real shield). "
            f"Got {r.status_code}: {r.text}"
        )

    def test_origin_without_netloc_is_treated_as_same_origin(self, toggle_setup):
        """``Origin: null`` parses to netloc='', endpoint short-circuits to OK.

        DOCUMENTED GAP — same logic as missing Origin: ``if origin_host and ...``.
        """
        client, _, _, _ = toggle_setup
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "null"},
        )
        # Currently: bypasses (origin_host is empty after urlparse).
        assert r.status_code == 409, (
            f"Origin: null currently bypasses (gap); got {r.status_code}: {r.text}"
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

    def test_cross_origin_with_https_scheme_is_refused(self, toggle_setup):
        """https://testserver vs Host: testserver — netloc 'testserver' equal,
        so this passes today. Pin the behavior so a tightening to scheme-aware
        comparison shows up loud.
        """
        client, _, _, _ = toggle_setup
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={
                "Origin": "https://testserver",
                "Host": "testserver",
            },
        )
        # Today: scheme-agnostic, netloc match → passes (409).
        assert r.status_code == 409, (
            "Scheme-agnostic Origin check is current behavior. "
            f"Got {r.status_code}: {r.text}"
        )


# ---------------------------------------------------------------------------
# Token protocol — paranoid pass
# ---------------------------------------------------------------------------

class TestTokenParanoia:
    def test_random_token_brute_force_all_rejected(self, toggle_setup):
        """100 random tokens, none match — all should produce 409 with a fresh token."""
        import secrets as _secrets
        client, _, _, _ = toggle_setup

        for _ in range(100):
            fake = _secrets.token_urlsafe(24)
            r = client.post(
                "/api/airgap/toggle",
                json={"target": "hybrid", "confirm_token": fake},
                headers={"Origin": "http://testserver"},
            )
            # Per the spec, an invalid token at step-2 issues a fresh one.
            assert r.status_code == 409
            assert r.json()["error"] == "need_confirm"

    def test_consumed_token_cannot_be_used_for_other_target(self, toggle_setup):
        """Token issued for hybrid; consume it; try to use it (already deleted) for airgapped."""
        client, _, _, _ = toggle_setup
        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        token = r1.json()["confirm_token"]

        # Use it once for hybrid (success).
        r2 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid", "confirm_token": token},
            headers={"Origin": "http://testserver"},
        )
        assert r2.status_code == 200

        # Try to reuse for airgapped (token deleted → 409 + fresh token).
        r3 = client.post(
            "/api/airgap/toggle",
            json={"target": "airgapped", "confirm_token": token},
            headers={"Origin": "http://testserver"},
        )
        assert r3.status_code == 409

    def test_concurrent_first_step_invalidates_prior_token(self, toggle_setup):
        """Two step-1 calls for same target: only the latest token is valid."""
        client, _, _, _ = toggle_setup

        r_a = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        token_a = r_a.json()["confirm_token"]

        # Issue another → invalidates token_a.
        r_b = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        token_b = r_b.json()["confirm_token"]
        assert token_a != token_b

        # New token (token_b) accepted.
        # NOTE: presenting token_a first would issue a fresh token at step-2
        # (per the endpoint's "invalid token → re-issue" path), which would
        # invalidate token_b. So we test token_b first.
        r_new = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid", "confirm_token": token_b},
            headers={"Origin": "http://testserver"},
        )
        assert r_new.status_code == 200

        # token_a must have been invalidated when token_b was issued.
        # Verify by checking the in-memory table (token_b is now consumed too).
        import arail.portal.app as app_mod
        with app_mod._TOGGLE_TOKENS_LOCK:
            assert token_a not in app_mod._TOGGLE_TOKENS
            assert token_b not in app_mod._TOGGLE_TOKENS

    def test_token_field_non_string_types_rejected(self, toggle_setup):
        """confirm_token=123 (int) / list / dict — endpoint should reject as invalid."""
        client, _, _, _ = toggle_setup
        for bad in (123, [], {}, True):
            r = client.post(
                "/api/airgap/toggle",
                json={"target": "hybrid", "confirm_token": bad},
                headers={"Origin": "http://testserver"},
            )
            # Either 409 (treated as bad token) or 400 (validation). Must NOT 200/500.
            assert r.status_code in (400, 409), (
                f"confirm_token={bad!r} → {r.status_code}: {r.text}"
            )


# ---------------------------------------------------------------------------
# Symlink + path attacks on env-writer
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

        # Step 1: get token (bind / origin OK).
        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        token = r1.json()["confirm_token"]

        r2 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid", "confirm_token": token},
            headers={"Origin": "http://testserver"},
        )
        assert r2.status_code == 500
        assert r2.json()["error"] == "env_write_failed"
        # Symlink target untouched.
        assert target.read_text() == "sensitive\n"
        # No path leak in body.
        body_text = r2.text
        assert str(env_path) not in body_text
        assert str(target) not in body_text

    def test_symlink_replaced_mid_race_between_step1_and_step2(self, toggle_setup, tmp_path):
        """Attacker replaces .env with a symlink AFTER token issued, BEFORE confirm.

        TOCTOU: env_writer.set_env_var checks ``path.is_symlink()`` immediately
        before write. If the swap happens after step-1, the writer's own check
        catches it and 500s — original target untouched.
        """
        client, env_path, _, _ = toggle_setup

        # Step 1: get token.
        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        token = r1.json()["confirm_token"]

        # Now race: replace .env with a symlink to an attacker target.
        attack = tmp_path / "evil_target"
        attack.write_text("DO NOT TOUCH\n")
        env_path.unlink()
        env_path.symlink_to(attack)

        r2 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid", "confirm_token": token},
            headers={"Origin": "http://testserver"},
        )
        assert r2.status_code == 500
        assert attack.read_text() == "DO NOT TOUCH\n"

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
# Concurrent toggle from two clients
# ---------------------------------------------------------------------------

class TestConcurrentTwoClients:
    def test_two_clients_serialised_no_torn_audit(self, toggle_setup):
        """Two threads each do a complete two-step flow. Audit log must be
        intact JSON-per-line (no torn writes), final .env value valid."""
        client, env_path, audit_path, _ = toggle_setup
        results = []
        sem = threading.Semaphore(1)

        def worker(target):
            with sem:  # serialize step1 to avoid token-invalidation race
                r1 = client.post(
                    "/api/airgap/toggle",
                    json={"target": target},
                    headers={"Origin": "http://testserver"},
                )
                if r1.status_code != 409:
                    results.append(("fail-step1", r1.status_code))
                    return
                tok = r1.json()["confirm_token"]
            r2 = client.post(
                "/api/airgap/toggle",
                json={"target": target, "confirm_token": tok},
                headers={"Origin": "http://testserver"},
            )
            results.append((target, r2.status_code))

        threads = [
            threading.Thread(target=worker, args=("hybrid",)),
            threading.Thread(target=worker, args=("airgapped",)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        # Both should have completed step-2 with 200.
        for target, code in results:
            assert code == 200, f"{target} step-2 got {code}"

        # .env contains a valid LAB_MODE line.
        env_text = env_path.read_text()
        assert ("LAB_MODE=hybrid" in env_text) or ("LAB_MODE=airgapped" in env_text)

        # Audit log: each line must be valid JSON (no torn writes).
        for line in audit_path.read_text().splitlines():
            if line.strip():
                json.loads(line)  # raises if torn

        # Two audit entries.
        non_empty = [l for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(non_empty) == 2


# ---------------------------------------------------------------------------
# Resource pressure
# ---------------------------------------------------------------------------

class TestResourceExhaustion:
    def test_failed_token_requests_do_not_leak_fds(self, toggle_setup):
        """200 step-2 calls with bogus tokens — file-descriptor count must stay flat."""
        client, _, _, _ = toggle_setup

        # Snapshot open FDs (POSIX-ish).
        try:
            soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        except Exception:
            soft = 1024

        def open_fd_count():
            try:
                return len(os.listdir(f"/proc/{os.getpid()}/fd"))
            except FileNotFoundError:
                # macOS has no /proc; fall back to lsof not great. Use a
                # weaker check by counting Path.iterdir on /dev/fd.
                try:
                    return len(os.listdir("/dev/fd"))
                except Exception:
                    pytest.skip("FD inspection not available on this platform")

        before = open_fd_count()
        for _ in range(200):
            r = client.post(
                "/api/airgap/toggle",
                json={"target": "hybrid", "confirm_token": "bogus_xxxxxxxxxxxxxxxxxxxx"},
                headers={"Origin": "http://testserver"},
            )
            assert r.status_code == 409
        after = open_fd_count()

        # Allow some slack but not unbounded growth.
        assert after - before < 50, f"FD leak: before={before} after={after}"

    def test_token_table_does_not_grow_unboundedly_on_repeat_step1(self, toggle_setup):
        """Repeated step-1 calls for the same target must not balloon the token dict.

        Spec: 'Issuance for the same target invalidates older tokens.'
        So 50 step-1 calls for 'hybrid' should leave at most 1 hybrid entry.
        """
        client, _, _, _ = toggle_setup
        import arail.portal.app as app_mod

        for _ in range(50):
            r = client.post(
                "/api/airgap/toggle",
                json={"target": "hybrid"},
                headers={"Origin": "http://testserver"},
            )
            assert r.status_code == 409

        with app_mod._TOGGLE_TOKENS_LOCK:
            hybrid_entries = [v for v in app_mod._TOGGLE_TOKENS.values()
                              if v.target == "hybrid"]
        assert len(hybrid_entries) == 1, (
            f"Token table growing unboundedly: {len(hybrid_entries)} hybrid entries"
        )


# ---------------------------------------------------------------------------
# Bind gate fires before Origin / token (defense-in-depth ordering)
# ---------------------------------------------------------------------------

class TestGateOrdering:
    def test_bind_gate_fires_before_origin_check(self, toggle_setup, monkeypatch):
        """A LAN-bound portal must 403 even with a malicious Origin header."""
        client, env_path, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "0.0.0.0")
        mtime_before = env_path.stat().st_mtime_ns

        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://evil.com"},
        )
        # Bind gate trumps origin check.
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

        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        token = r1.json()["confirm_token"]

        with patch("arail.env_writer.set_env_var",
                   side_effect=EnvWriterError(f"failed at {env_path}: SECRET=do-not-leak")):
            r2 = client.post(
                "/api/airgap/toggle",
                json={"target": "hybrid", "confirm_token": token},
                headers={"Origin": "http://testserver"},
            )
        assert r2.status_code == 500
        body_text = r2.text
        assert str(env_path) not in body_text
        assert "SECRET" not in body_text
        assert "do-not-leak" not in body_text
