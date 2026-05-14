"""Concurrency tests for the airgap toggle endpoint + env_writer.

Sprint 2026-05-14-airgap-onetap-toggle — simplified to one-shot POST.
Each thread does a single POST /api/airgap/toggle {target}. No step-1 /
step-2 token dance; that protocol was removed.

Key assertions:
  - No torn .env write (file always parseable with valid LAB_MODE).
  - At least one thread completes a successful toggle.
  - Audit lines are individually valid JSON with required fields.
  - test_env_writer_concurrent_no_torn_file: 32 direct env_writer calls;
    no torn lines (exercises the per-path lock directly).
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
    """Return (env_path, audit_path) wired into the endpoint via module override."""
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
    def test_8_threads_one_shot(self, env_and_audit):
        """8 threads each issue a single one-tap POST concurrently.

        Assertions:
        - No thread crashes.
        - .env remains parseable with a valid LAB_MODE value (no torn write).
        - At least one thread gets 200.
        - All audit lines are valid JSON with ts/from/to fields.
        """
        env_path, audit_path = env_and_audit

        client = TestClient(app, raise_server_exceptions=False)

        successes: list[str] = []
        errors: list[str] = []
        lock = threading.Lock()

        def _do_toggle(thread_idx: int) -> None:
            target = "hybrid" if thread_idx % 2 == 0 else "airgapped"
            try:
                r = client.post(
                    "/api/airgap/toggle",
                    json={"target": target},
                    headers={"Origin": "http://testserver"},
                )
                if r.status_code == 200:
                    with lock:
                        successes.append(r.json().get("lab_mode", "?"))
                elif r.status_code not in (200,):
                    # Any non-200 that isn't a known gate response is unexpected.
                    with lock:
                        errors.append(
                            f"thread {thread_idx}: unexpected {r.status_code}: {r.text}"
                        )
            except Exception as exc:
                with lock:
                    errors.append(f"thread {thread_idx}: exception {exc}")

        threads = [threading.Thread(target=_do_toggle, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, "Thread errors:\n" + "\n".join(errors)

        # At least one thread succeeded.
        assert len(successes) >= 1, "No thread completed a successful toggle"

        # .env is parseable and LAB_MODE has a valid value.
        final_text = env_path.read_text()
        lab_lines = [l for l in final_text.splitlines() if l.startswith("LAB_MODE=")]
        assert lab_lines, "LAB_MODE missing from .env after concurrent toggling"
        val = lab_lines[0].split("=", 1)[1].strip().strip("\"'")
        assert val in ("airgapped", "hybrid"), f"Torn LAB_MODE value: {val!r}"

        # Audit lines: each is valid JSON with required fields.
        if audit_path.exists():
            audit_lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
            assert len(audit_lines) >= 1, "Expected at least one audit line"
            for line in audit_lines:
                entry = json.loads(line)
                assert "ts" in entry
                assert "from" in entry
                assert "to" in entry

    def test_two_threads_opposite_targets(self, env_and_audit):
        """Two threads POST opposite targets; exactly one of {airgapped, hybrid} ends up
        persisted; exactly 2 audit lines; no torn write."""
        env_path, audit_path = env_and_audit

        client = TestClient(app, raise_server_exceptions=False)
        results: list[int] = []
        lock = threading.Lock()

        def _do(target: str) -> None:
            r = client.post(
                "/api/airgap/toggle",
                json={"target": target},
                headers={"Origin": "http://testserver"},
            )
            with lock:
                results.append(r.status_code)

        t1 = threading.Thread(target=_do, args=("hybrid",))
        t2 = threading.Thread(target=_do, args=("airgapped",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both should return 200 (the per-path lock serializes writes).
        assert results.count(200) == 2, f"Expected 2 x 200, got: {results}"

        # Final disk state is valid.
        final_text = env_path.read_text()
        lab_lines = [l for l in final_text.splitlines() if l.startswith("LAB_MODE=")]
        assert lab_lines
        val = lab_lines[0].split("=", 1)[1].strip().strip("\"'")
        assert val in ("airgapped", "hybrid"), f"Torn value: {val!r}"

        # Exactly 2 audit lines (one per successful flip).
        assert audit_path.exists()
        audit_lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(audit_lines) == 2, f"Expected 2 audit lines, got {len(audit_lines)}"

    def test_env_writer_concurrent_no_torn_file(self, env_and_audit):
        """32 threads writing LAB_MODE via env_writer directly — no torn lines.

        Exercises the env_writer per-path lock independent of the HTTP layer.
        """
        from arail.env_writer import set_env_var
        env_path, _ = env_and_audit

        errors: list[Exception] = []
        err_lock = threading.Lock()

        def _flip(n: int) -> None:
            try:
                target = "hybrid" if n % 2 == 0 else "airgapped"
                set_env_var(env_path, "LAB_MODE", target)
            except Exception as e:
                with err_lock:
                    errors.append(e)

        threads = [threading.Thread(target=_flip, args=(i,)) for i in range(32)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Writer errors: {errors}"
        final = env_path.read_text()
        lab_lines = [l for l in final.splitlines() if l.startswith("LAB_MODE=")]
        assert lab_lines
        val = lab_lines[0].split("=", 1)[1].strip().strip("\"'")
        assert val in ("airgapped", "hybrid"), f"Torn value: {val!r}"
