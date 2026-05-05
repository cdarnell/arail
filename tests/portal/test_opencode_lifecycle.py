"""Lifecycle tests for opencode service module.

Covers ARCHITECTURE.md must-pass list:
  - test_start_returns_error_if_port_busy     (F-PROC-2)
  - test_restart_after_provider_switch        (F-RESTART-1)
  - test_restart_picks_up_new_env             (F-RESTART-2)
  - test_concurrent_restart_serializes        (F-PROC-4)
  - test_provider_switch_succeeds_when_restart_fails (F-RESTART-1)
  - test_log_rotation_at_10mb                 (F-PROC-6)
  - test_wait_ready_polls_doc_endpoint        (A9)
  - test_wait_ready_timeout                   (F-PROC-1)
"""

from __future__ import annotations

import os
import socket
import threading
import time
import unittest.mock as mock
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# F-PROC-2 — port busy prevents start
# ---------------------------------------------------------------------------

class TestPortBusy:
    def test_start_returns_error_if_port_busy(self, monkeypatch, tmp_path):
        """Bind port 4096 externally; start() must return port-busy error, not kill. (F-PROC-2)"""
        import arail.portal.services.opencode as oc

        # Use a random free port to avoid conflicts in CI
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        bound_port = sock.getsockname()[1]
        try:
            monkeypatch.setattr(oc, "is_installed", lambda: True)
            monkeypatch.setattr(oc, "LOG_PATH", tmp_path / "opencode.log")
            result = oc.start(port=bound_port)
            assert result["ok"] is False
            assert "port busy" in result["error"], (
                f"Expected 'port busy' error, got: {result}"
            )
        finally:
            sock.close()


# ---------------------------------------------------------------------------
# F-RESTART-1 — provider switch fires restart without blocking response
# ---------------------------------------------------------------------------

class TestProviderSwitchRestart:
    def test_restart_after_provider_switch(self, monkeypatch):
        """POST /api/providers/active triggers a restart thread when opencode running (F-RESTART-1)."""
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setenv("LAB_MODE", "hybrid")

        restart_called = threading.Event()

        import arail.portal.services.opencode as oc
        monkeypatch.setattr(oc, "is_running", lambda port=oc.PORT_DEFAULT: True)

        original_restart = oc.restart
        def fake_restart(port=oc.PORT_DEFAULT):
            restart_called.set()
            return {"ok": True}
        monkeypatch.setattr(oc, "restart", fake_restart)

        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/providers/active", json={"provider": "my_machine"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("ok") is True, f"Provider switch failed: {data}"

        # Restart fires asynchronously — give it a moment
        assert restart_called.wait(timeout=3.0), (
            "opencode.restart() was not called within 3 s of provider switch"
        )

    def test_provider_switch_succeeds_when_restart_fails(self, monkeypatch):
        """Provider switch returns ok even when opencode.restart() returns failure (F-RESTART-1)."""
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setenv("LAB_MODE", "hybrid")

        import arail.portal.services.opencode as oc
        monkeypatch.setattr(oc, "is_running", lambda port=oc.PORT_DEFAULT: True)
        # Return error dict (not raise) so the daemon thread doesn't produce unhandled exception
        monkeypatch.setattr(oc, "restart", lambda port=oc.PORT_DEFAULT: {"ok": False, "error": "simulated failure"})

        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/providers/active", json={"provider": "my_machine"})
        assert resp.status_code == 200
        assert resp.json().get("ok") is True


# ---------------------------------------------------------------------------
# F-RESTART-2 — restart picks up new env
# ---------------------------------------------------------------------------

class TestRestartEnv:
    def test_restart_picks_up_new_env(self, monkeypatch, tmp_path):
        """After env changes, second start() Popen call uses updated env (F-RESTART-2)."""
        import arail.portal.services.opencode as oc

        popen_envs: list[dict] = []

        def fake_popen(args, **kwargs):
            popen_envs.append(dict(kwargs.get("env", {})))
            m = mock.Mock()
            m.pid = 99
            return m

        monkeypatch.setattr(oc, "is_installed", lambda: True)
        monkeypatch.setattr(oc, "LOG_PATH", tmp_path / "opencode.log")
        monkeypatch.setattr("arail.portal.services.opencode.subprocess.Popen", fake_popen)

        # First call with MODEL_NAME=modelA
        monkeypatch.setenv("MODEL_NAME", "modelA")
        # Patch is_running to return False initially (no port bound)
        call_count = [0]
        def is_running_fake(port=oc.PORT_DEFAULT):
            call_count[0] += 1
            return False
        monkeypatch.setattr(oc, "is_running", is_running_fake)

        result1 = oc._start_inner(oc.PORT_DEFAULT)
        assert result1["ok"] is True

        # Second call with MODEL_NAME=modelB
        monkeypatch.setenv("MODEL_NAME", "modelB")
        result2 = oc._start_inner(oc.PORT_DEFAULT)
        assert result2["ok"] is True

        assert len(popen_envs) == 2
        assert popen_envs[0].get("MODEL_NAME") == "modelA"
        assert popen_envs[1].get("MODEL_NAME") == "modelB"


# ---------------------------------------------------------------------------
# F-PROC-4 — concurrent restart serializes via lock
# ---------------------------------------------------------------------------

class TestConcurrentRestart:
    def test_concurrent_restart_serializes(self, monkeypatch, tmp_path):
        """Two concurrent restart() calls must not overlap (Lock enforces serialization)."""
        import arail.portal.services.opencode as oc

        # Track when each restart holds the lock
        order: list[str] = []
        lock_times: list[float] = []

        original_stop_unlocked = oc._stop_unlocked
        original_start_inner = oc._start_inner
        original_wait_ready = oc._wait_ready

        def fake_stop(port):
            order.append(f"stop-{threading.current_thread().name}")
            time.sleep(0.1)  # simulate work
            return {"ok": True, "killed": []}

        def fake_start(port):
            order.append(f"start-{threading.current_thread().name}")
            return {"ok": True, "pid": 1}

        def fake_wait_ready(port, timeout_s):
            return True

        monkeypatch.setattr(oc, "_stop_unlocked", fake_stop)
        monkeypatch.setattr(oc, "_start_inner", fake_start)
        monkeypatch.setattr(oc, "_wait_ready", fake_wait_ready)
        monkeypatch.setattr(oc, "is_running", lambda port=oc.PORT_DEFAULT: False)

        results: list[dict] = []

        def run_restart():
            r = oc.restart()
            results.append(r)

        t1 = threading.Thread(target=run_restart, name="T1")
        t2 = threading.Thread(target=run_restart, name="T2")
        t1.start()
        time.sleep(0.01)  # slight offset to ensure both reach the lock
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert len(results) == 2
        # Both should succeed (fake functions never fail)
        for r in results:
            assert r.get("ok") is True, f"Restart failed: {r}"

        # Verify operations didn't interleave: all T1 ops before all T2 ops
        # (or vice versa) — no mixing of stop/start across threads
        assert len(order) == 4, f"Expected 4 ordered events, got {order}"
        # T1's stop must complete before T2's stop starts
        t1_ops = [i for i, o in enumerate(order) if "T1" in o]
        t2_ops = [i for i, o in enumerate(order) if "T2" in o]
        # No interleaving: T1 finishes before T2 starts (or vice versa)
        assert max(t1_ops) < min(t2_ops) or max(t2_ops) < min(t1_ops), (
            f"Restart calls interleaved — lock not working: {order}"
        )


# ---------------------------------------------------------------------------
# F-PROC-6 — log rotation at 10 MB
# ---------------------------------------------------------------------------

class TestLogRotation:
    def test_log_rotation_at_10mb(self, monkeypatch, tmp_path):
        """If log > 10 MB on start(), it's rotated to .log.1 before new log opens."""
        import arail.portal.services.opencode as oc

        log_file = tmp_path / "opencode.log"
        # Pre-seed a file larger than 10 MB
        log_file.write_bytes(b"x" * (11 * 1024 * 1024))
        assert log_file.stat().st_size > 10 * 1024 * 1024

        monkeypatch.setattr(oc, "LOG_PATH", log_file)
        monkeypatch.setattr(oc, "is_installed", lambda: True)
        monkeypatch.setattr(oc, "is_running", lambda port=oc.PORT_DEFAULT: False)

        def fake_popen(args, **kwargs):
            m = mock.Mock()
            m.pid = 42
            return m

        monkeypatch.setattr("arail.portal.services.opencode.subprocess.Popen", fake_popen)

        result = oc.start()
        assert result["ok"] is True

        rotated = log_file.with_suffix(".log.1")
        assert rotated.exists(), "Log was not rotated to .log.1"
        assert rotated.stat().st_size > 10 * 1024 * 1024, "Rotated file has wrong size"


# ---------------------------------------------------------------------------
# A9, F-PROC-1 — _wait_ready polls /doc endpoint
# ---------------------------------------------------------------------------

class TestWaitReady:
    """Spin up a tiny in-process HTTP server to test readiness polling."""

    def _run_fake_server(self, response_sequence: list[int], host="127.0.0.1"):
        """Return (server, port, thread). Server responds with each status_code in sequence."""
        responses = list(response_sequence)

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                code = responses.pop(0) if responses else 503
                self.send_response(code)
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass  # suppress output

        server = HTTPServer((host, 0), Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server, port, t

    def test_wait_ready_polls_doc_endpoint(self, monkeypatch):
        """503 then 200: _wait_ready should return True within timeout (A9)."""
        import arail.portal.services.opencode as oc

        server, port, _ = self._run_fake_server([503, 503, 200])
        try:
            result = oc._wait_ready(port=port, timeout_s=5.0)
            assert result is True, "_wait_ready should return True after 200 from /doc"
        finally:
            server.shutdown()

    def test_wait_ready_timeout(self, monkeypatch):
        """Server stays 503: _wait_ready returns False after timeout (F-PROC-1)."""
        import arail.portal.services.opencode as oc

        # Server returns 503 indefinitely
        server, port, _ = self._run_fake_server([503] * 100)
        try:
            start = time.monotonic()
            result = oc._wait_ready(port=port, timeout_s=0.8)
            elapsed = time.monotonic() - start
            assert result is False, "_wait_ready should return False on timeout"
            assert elapsed < 3.0, f"_wait_ready took too long: {elapsed:.1f}s"
        finally:
            server.shutdown()
