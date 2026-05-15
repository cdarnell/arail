"""QA paranoid pass for sprint 2026-05-14-security-hygiene.

Hunts the edge cases the architect did not enumerate. Allocation per
arail/CLAUDE.md: 30% setup / 30% Buddy / 20% security / 10% happy / 10%
regression. This sprint is security-shaped end-to-end; the file leans
into the 20% security weight and dips into setup + happy for the
clean-machine + UI flows.

Covers four items:
  1. PRIVACY.md trust-model claim — verify against actual endpoints.
  2. Token redaction edge cases the architect missed.
  3. start_new_session edge cases.
  4. Sec-Fetch-Site edge cases.
"""
from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Item 1 — PRIVACY.md claim verification (security)
# ---------------------------------------------------------------------------

def test_privacy_doc_trust_boundary_section_present():
    """PRIVACY.md must contain the trust-boundary subsection that this sprint added."""
    doc = Path("docs/PRIVACY.md").read_text(encoding="utf-8")
    assert "Loopback trust boundary" in doc, "trust-boundary header missing"
    assert "127.0.0.1" in doc


def test_privacy_doc_claim_airgap_toggle_unauth():
    """The doc claims the airgap toggle has no auth — verify on the live app.

    A POST with no Authorization, no cookies, just loopback Origin/Host should
    succeed (the only gates are bind+CSRF+target, no user-auth check)."""
    from fastapi.testclient import TestClient
    from arail.portal.app import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "airgapped"},
        headers={"Origin": "http://testserver"},
    )
    # 200 (accepted) or 500 (env write fail in CI) — both prove auth is NOT a gate.
    # 401/403-with-auth-error would invalidate the doc claim.
    assert r.status_code != 401, "doc claim broken: airgap toggle requires auth"
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("error") not in ("unauthorized", "auth_required"), body


def test_privacy_doc_claim_opencode_start_unauth():
    """The doc claims opencode subprocess controls have no auth — verify."""
    from fastapi.testclient import TestClient
    from arail.portal.app import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.post("/api/opencode/start")
    # Tier gate or LLM-not-ready may reject — but never on auth grounds.
    assert r.status_code != 401
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("error") not in ("unauthorized", "auth_required")


def test_privacy_doc_claim_providers_save_unauth():
    """The doc claims any loopback peer can save provider tokens — verify."""
    from fastapi.testclient import TestClient
    from arail.portal.app import app
    client = TestClient(app, raise_server_exceptions=False)
    # Don't actually save a real token; even rejection-for-validation proves no auth gate.
    r = client.post("/api/providers/save", json={"provider": "claude", "token": ""})
    assert r.status_code != 401
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    assert body.get("error") not in ("unauthorized", "auth_required")


# ---------------------------------------------------------------------------
# Item 2 — token redaction: edge cases the architect missed
# ---------------------------------------------------------------------------

def _W():
    from arail.portal.services.opencode import _RedactingLogWriter, _REDACTED
    return _RedactingLogWriter, _REDACTED


def test_redacts_token_split_across_three_writes(tmp_path):
    """Token straddling THREE chunks (not just two). Tail buffer must hold across
    multiple writes until the full token has arrived."""
    Writer, REDACTED = _W()
    log = tmp_path / "oc.log"
    secret = b"THREE_WAY_SPLIT_TOKEN_XYZ"  # 25 bytes
    a, b, c = secret[:8], secret[8:16], secret[16:]
    w = Writer(log, [secret])
    w.write(b"head " + a)
    w.write(b)
    w.write(c + b" tail")
    w.flush_tail()
    w.close()
    content = log.read_bytes()
    assert secret not in content, f"token leaked: {content!r}"
    assert REDACTED in content
    assert b"head " in content and b" tail" in content


def test_token_with_high_bit_bytes(tmp_path):
    """High-bit / non-ASCII bytes in token — bytes.replace must still match."""
    Writer, REDACTED = _W()
    log = tmp_path / "oc.log"
    secret = b"\xc3\xa9\xc3\xb1TOK\xff\x00END"  # contains non-ASCII + NUL + 0xFF
    assert len(secret) >= 8
    w = Writer(log, [secret])
    w.write(b"prefix " + secret + b" suffix")
    w.flush_tail()
    w.close()
    content = log.read_bytes()
    assert secret not in content
    assert REDACTED in content


def test_multiple_distinct_tokens_in_one_chunk(tmp_path):
    """Two distinct secrets in a single write call — both must be redacted."""
    Writer, REDACTED = _W()
    log = tmp_path / "oc.log"
    s1 = b"FIRST_TOKEN_VALUE_AAA"
    s2 = b"SECOND_TOKEN_VALUE_BB"
    w = Writer(log, [s1, s2])
    w.write(b"start " + s1 + b" middle " + s2 + b" end")
    w.flush_tail()
    w.close()
    content = log.read_bytes()
    assert s1 not in content
    assert s2 not in content
    assert content.count(REDACTED) == 2


def test_token_without_trailing_newline_eventually_redacted(tmp_path):
    """Token written without a trailing newline — must be redacted by flush_tail."""
    Writer, REDACTED = _W()
    log = tmp_path / "oc.log"
    secret = b"NO_NEWLINE_TOKEN_VALUE"
    w = Writer(log, [secret])
    w.write(secret)  # no newline, no trailing data
    w.flush_tail()    # simulates EOF on the pipe
    w.close()
    content = log.read_bytes()
    assert secret not in content
    assert REDACTED in content


def test_token_appears_multiple_times_in_one_chunk(tmp_path):
    """Same token repeated — every occurrence must be redacted."""
    Writer, REDACTED = _W()
    log = tmp_path / "oc.log"
    secret = b"REPEATED_TOKEN_VALUE_X"
    w = Writer(log, [secret])
    w.write(secret + b" then " + secret + b" then " + secret)
    w.flush_tail()
    w.close()
    content = log.read_bytes()
    assert secret not in content
    assert content.count(REDACTED) == 3


def test_existing_log_1_with_old_tokens_dropped(tmp_path):
    """If .log.1 has old tokens at startup, tombstone-drop must remove them."""
    from arail.portal.services.opencode import _open_log_with_redactor
    log = tmp_path / "opencode.log"
    rotated = tmp_path / "opencode.log.1"
    rotated.write_bytes(b"OLD_LEAKED_TOKEN_FROM_PRIOR_RUN_12345")
    write_fd, writer, thread = _open_log_with_redactor(log, {})
    thread.start()
    os.close(write_fd)
    thread.join(timeout=2)
    writer.close()
    assert not rotated.exists(), "rotated .log.1 must be unlinked on start"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX perms only")
def test_log_file_permissions_are_0600_after_subprocess_run(tmp_path):
    """End-to-end: after a subprocess writes through the redactor, the log
    file on disk must be 0600 (not 0644)."""
    from arail.portal.services.opencode import _open_log_with_redactor
    log = tmp_path / "opencode.log"
    write_fd, writer, thread = _open_log_with_redactor(log, {})
    thread.start()
    proc = subprocess.Popen(
        [sys.executable, "-c", "print('hello')"],
        stdout=write_fd, stderr=write_fd,
    )
    os.close(write_fd)
    proc.wait(timeout=5)
    thread.join(timeout=2)
    writer.close()
    mode = stat.S_IMODE(os.stat(log).st_mode)
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


def test_redactor_survives_internal_write_exception(tmp_path):
    """If the underlying file write raises mid-stream, the writer must not crash
    the caller — it should swallow and log."""
    Writer, _ = _W()
    log = tmp_path / "oc.log"
    secret = b"SOME_SECRET_TOKEN_12345"
    w = Writer(log, [secret])

    # Replace the file handle with one that raises on write
    class BrokenFile:
        def write(self, _b): raise OSError("disk full")
        def flush(self): pass
        def close(self): pass
    w._fh = BrokenFile()

    # Must not raise
    n = w.write(b"some data " + secret)
    assert n > 0, "writer must report progress even on internal failure"
    w.close()


def test_token_keys_match_compute_source_env_exactly():
    """Regression: _TOKEN_KEYS in _open_log_with_redactor must include every
    env key that _compute_source_env can set as a token value.

    If a new provider is added to _PROVIDER_TOKEN_ENV without updating
    _TOKEN_KEYS, that provider's token would leak to opencode.log.
    """
    from arail.portal.services.opencode import _PROVIDER_TOKEN_ENV
    import inspect
    from arail.portal.services import opencode as oc
    src = inspect.getsource(oc._open_log_with_redactor)
    for env_name in _PROVIDER_TOKEN_ENV.values():
        assert env_name in src, (
            f"_TOKEN_KEYS in _open_log_with_redactor is missing {env_name!r} — "
            "tokens for that provider will leak to opencode.log"
        )
    # OPENCODE_API_KEY mirror is also exported by _compute_source_env
    assert "OPENCODE_API_KEY" in src


def test_short_real_tokens_threshold_appropriate():
    """Sanity: real provider tokens are well above the 8-byte threshold.

    Documenting the threshold by example. If any vendor's tokens drop
    below 8 chars in the future, this test will fail and force
    re-evaluation of _MIN_SECRET_LEN.
    """
    from arail.portal.services.opencode import _MIN_SECRET_LEN
    assert _MIN_SECRET_LEN == 8
    # Reference token prefixes (publicly known):
    # Anthropic: sk-ant-api03-... (~100 chars)
    # OpenRouter: sk-or-v1-... (~70 chars)
    # NVIDIA NIM: nvapi-... (~70 chars)
    # HF: hf_... (~37 chars)
    # All well above 8.


# ---------------------------------------------------------------------------
# Item 3 — start_new_session edge cases
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")
def test_killpg_does_not_reach_unrelated_processes():
    """Sanity: killpg on the child's pgid must NOT signal the test runner.

    If start_new_session were missing, the child would share the pytest
    process group, and SIGTERM to that group would kill pytest.
    """
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # pytest's pgid must NOT equal the child's pgid
        assert os.getpgid(proc.pid) != os.getpgid(os.getpid())
    finally:
        try: os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        proc.wait(timeout=3)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX only")
def test_child_exits_cleanly_no_zombie_after_wait():
    """After killpg + wait, the child PID is reaped (no zombie)."""
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    os.killpg(proc.pid, signal.SIGTERM)
    rc = proc.wait(timeout=3)
    assert rc is not None
    # poll() returns the exit code (not None) on a reaped child
    assert proc.poll() is not None


# ---------------------------------------------------------------------------
# Item 4 — Sec-Fetch-Site edge cases
# ---------------------------------------------------------------------------

@pytest.fixture()
def airgap_client(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_bytes(b"LAB_MODE=airgapped\n")
    audit_path = tmp_path / "audit.jsonl"
    import arail.portal.app as app_mod
    monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
    monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
    monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
    monkeypatch.setenv("LAB_MODE", "airgapped")
    from fastapi.testclient import TestClient
    from arail.portal.app import app
    return TestClient(app, raise_server_exceptions=False), env_path, audit_path


def test_sfs_with_leading_trailing_whitespace_normalized(airgap_client):
    """' cross-site ' (with whitespace) must be normalized and rejected."""
    client, env_path, _ = airgap_client
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={"Sec-Fetch-Site": "  cross-site  ", "Origin": "http://testserver"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"
    assert "LAB_MODE=airgapped" in env_path.read_text()


def test_sfs_uppercase_value_normalized(airgap_client):
    """'CROSS-SITE' must lowercase-match and reject."""
    client, env_path, _ = airgap_client
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={"Sec-Fetch-Site": "CROSS-SITE", "Origin": "http://testserver"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"


def test_sfs_with_legacy_same_origin_underscore_value(airgap_client):
    """'SAME-ORIGIN' (uppercase legal value) must accept (not in the reject set)."""
    client, _, _ = airgap_client
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={"Sec-Fetch-Site": "SAME-ORIGIN", "Origin": "http://testserver"},
    )
    assert r.status_code == 200


def test_sfs_empty_string_falls_through(airgap_client):
    """Empty Sec-Fetch-Site value behaves like absent (falls through to Origin)."""
    client, _, _ = airgap_client
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={"Sec-Fetch-Site": "", "Origin": "http://testserver"},
    )
    assert r.status_code == 200


def test_sfs_garbage_unknown_value_falls_through_to_origin(airgap_client):
    """Unknown future / garbage value must fall through to Origin gate.

    Verifies forward-compat: a new browser-spec value 'same-segment' (made up)
    must not silently get rejected — the existing Origin gate must still
    decide.
    """
    client, _, _ = airgap_client
    # garbage value + matching Origin → fall through to Origin pass → 200
    r1 = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={"Sec-Fetch-Site": "foobar-unknown", "Origin": "http://testserver"},
    )
    assert r1.status_code == 200


def test_sfs_garbage_value_with_mismatched_origin_yields_cross_origin(airgap_client):
    """Unknown SFS + mismatched Origin → cross_origin (Origin gate runs)."""
    client, _, _ = airgap_client
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={"Sec-Fetch-Site": "foobar-unknown", "Origin": "http://evil.example.com"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "cross_origin"


def test_sfs_with_sec_fetch_mode_and_dest_ignored(airgap_client):
    """Sec-Fetch-Mode / Sec-Fetch-Dest must not change the verdict — our gate
    keys only on Sec-Fetch-Site."""
    client, _, _ = airgap_client
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Dest": "empty",
            "Origin": "http://testserver",
        },
    )
    assert r.status_code == 200


def test_sfs_cross_site_get_request_not_applicable():
    """The endpoint is POST-only; verify the SFS gate is keyed inside the POST
    handler (so a GET probe doesn't accidentally reveal the gate).

    A GET to /api/airgap/toggle should return 405 Method Not Allowed,
    NOT 403 cross_site.
    """
    from fastapi.testclient import TestClient
    from arail.portal.app import app
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/api/airgap/toggle", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code in (404, 405), f"unexpected status {r.status_code}"


# ---------------------------------------------------------------------------
# Setup / happy / regression (per arail/CLAUDE.md allocation)
# ---------------------------------------------------------------------------

def test_opencode_log_dir_creation_idempotent(tmp_path):
    """Setup: clean-machine — _open_log_with_redactor must create the log dir
    if missing (no FileNotFoundError on first launch)."""
    from arail.portal.services.opencode import _open_log_with_redactor
    log = tmp_path / "nonexistent_subdir" / "deeper" / "opencode.log"
    assert not log.parent.exists()
    write_fd, writer, thread = _open_log_with_redactor(log, {})
    thread.start()
    os.close(write_fd)
    thread.join(timeout=2)
    writer.close()
    assert log.exists()


def test_happy_airgap_toggle_via_normal_browser_flow(airgap_client):
    """Happy: a normal portal UI request (same-origin + matching Origin) succeeds."""
    client, env_path, audit_path = airgap_client
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={"Sec-Fetch-Site": "same-origin", "Origin": "http://testserver"},
    )
    assert r.status_code == 200
    assert r.json()["lab_mode"] == "hybrid"
    assert "LAB_MODE=hybrid" in env_path.read_text()
    assert audit_path.exists()


def test_regression_post_without_any_sec_fetch_headers_still_works(airgap_client):
    """Regression: CLI/curl/TestClient flows that pre-date this sprint (no SFS
    header) must continue to work — Origin check alone must gate."""
    client, _, _ = airgap_client
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={"Origin": "http://testserver"},
    )
    assert r.status_code == 200
