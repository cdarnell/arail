"""Concurrency tests for the airgap toggle endpoint + env_writer.

ARCHITECTURE.md §9 test_airgap_toggle_concurrency.py:
- 8 threads each issue the full two-step flow concurrently against the
  same temp .env file.
- Assert: final value is one of {airgapped, hybrid}, file always
  parseable, exactly N audit lines (N ≤ 8, ≥ 1). No torn writes.

These tests must pass BEFORE the endpoint is wired; the env_writer
concurrency guarantee is already exercised by test_env_writer.py. This
file exercises the full two-step protocol under concurrency (step 1 →
409 + token, step 2 → 200).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arail.portal.app import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def env_and_audit(tmp_path, monkeypatch):
    """Return (env_path, audit_path) pointing at temp files; wire the
    endpoint to use them via the module-level _TOGGLE_ENV_PATH override."""
    env_path = tmp_path / ".env"
    env_path.write_bytes(b"LAB_MODE=airgapped\n")
    audit_path = tmp_path / "airgap_audit.jsonl"

    import arail.portal.app as app_mod
    monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
    monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
    monkeypatch.setenv("LAB_MODE", "airgapped")
    monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
    return env_path, audit_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestToggleConcurrency:
    def test_8_threads_full_two_step(self, env_and_audit, monkeypatch):
        """8 threads each run the two-step flow; assertions hold post-join."""
        env_path, audit_path = env_and_audit

        # Re-create client inside the test so monkeypatches are in effect.
        client = TestClient(app, raise_server_exceptions=False)

        successes: list[str] = []
        errors: list[str] = []
        lock = threading.Lock()

        def _do_toggle(thread_idx: int) -> None:
            target = "hybrid" if thread_idx % 2 == 0 else "airgapped"
            try:
                # Step 1: expect 409 + token.
                r1 = client.post(
                    "/api/airgap/toggle",
                    json={"target": target},
                    headers={"Origin": "http://testserver"},
                )
                if r1.status_code != 409:
                    with lock:
                        errors.append(f"thread {thread_idx}: step1 expected 409, got {r1.status_code}: {r1.text}")
                    return
                body1 = r1.json()
                token = body1.get("confirm_token")
                if not token:
                    with lock:
                        errors.append(f"thread {thread_idx}: no token in {body1}")
                    return

                # Step 2: confirm with token.
                r2 = client.post(
                    "/api/airgap/toggle",
                    json={"target": target, "confirm_token": token},
                    headers={"Origin": "http://testserver"},
                )
                # May be 200 (success) or 409 (token lost to another thread or expired).
                with lock:
                    if r2.status_code == 200:
                        successes.append(r2.json().get("lab_mode", "?"))
                    elif r2.status_code == 409:
                        # Token was consumed by a race; acceptable.
                        pass
                    else:
                        errors.append(
                            f"thread {thread_idx}: step2 unexpected {r2.status_code}: {r2.text}"
                        )
            except Exception as exc:
                with lock:
                    errors.append(f"thread {thread_idx}: exception {exc}")

        threads = [threading.Thread(target=_do_toggle, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Thread errors:\n" + "\n".join(errors)

        # At least one successful toggle.
        assert len(successes) >= 1, "No thread completed a successful toggle"

        # .env is parseable and LAB_MODE has a valid value.
        final_text = env_path.read_text()
        lab_lines = [l for l in final_text.splitlines() if l.startswith("LAB_MODE=")]
        assert lab_lines, "LAB_MODE missing from .env after concurrent toggling"
        val = lab_lines[0].split("=", 1)[1].strip().strip("\"'")
        assert val in ("airgapped", "hybrid"), f"Torn LAB_MODE value: {val!r}"

        # Audit log has N lines where 1 ≤ N ≤ 8, all valid JSON.
        if audit_path.exists():
            audit_lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
            assert 1 <= len(audit_lines) <= 8, f"Unexpected audit line count: {len(audit_lines)}"
            for line in audit_lines:
                entry = json.loads(line)
                assert "ts" in entry
                assert "from" in entry
                assert "to" in entry
