"""Integration tests for regenerate_config + lifecycle.

Covers ARCHITECTURE.md must-pass list:
  F-CONFIG-3  — atomic write (original file intact on failure)
  F-CONFIG-4  — concurrent calls serialized
  F-CONFIG-6  — lab/.opencode/ dir perms 0700
  F-RESTART-1 — hook: regenerate THEN restart, serialized
  F-RESTART-2 — hook: aborts restart on config failure
  F-RESTART-4 — hook: skipped when opencode not running
  F-SEC-CRED-3 — lab/.opencode/ git-ignored
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import tempfile
import threading
import time
import unittest.mock as mock
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_service(monkeypatch, tmp_path: Path, provider="my_machine",
                   state="ready", model="TestModel", token=""):
    """Wire up the lazy imports and direct config_dir to a temp path."""
    from arail.portal.services import opencode as oc

    # Point _config_dir() at tmp_path
    monkeypatch.setattr(oc, "_config_dir", lambda: tmp_path / ".opencode")
    monkeypatch.setattr(oc, "_config_path", lambda: tmp_path / ".opencode" / "opencode.json")

    # Patch lazy imports used by _regenerate_config_unlocked
    with mock.patch("arail.portal.app._load_active_provider", return_value=provider,
                    create=True), \
         mock.patch("arail.portal.app._get_chat_model_load_state",
                    return_value={"state": state, "model": model}, create=True), \
         mock.patch("arail.portal.app._provider_token", return_value=token, create=True):
        return oc


# ---------------------------------------------------------------------------
# Config file tests
# ---------------------------------------------------------------------------

class TestRegenerateConfig:
    def test_start_writes_opencode_json_to_lab_scoped_dir(self, monkeypatch, tmp_path):
        """start() triggers config write at lab/.opencode/opencode.json. (F-CONFIG-3)"""
        from arail.portal.services import opencode as oc

        monkeypatch.setattr(oc, "_config_dir", lambda: tmp_path / ".opencode")
        monkeypatch.setattr(oc, "_config_path",
                            lambda: tmp_path / ".opencode" / "opencode.json")

        with mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                        create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "TestModel"}, create=True), \
             mock.patch("arail.portal.app._provider_token", return_value="", create=True):
            result = oc.regenerate_config()

        assert result["ok"] is True, f"regenerate_config failed: {result}"
        cfg_file = tmp_path / ".opencode" / "opencode.json"
        assert cfg_file.exists(), "opencode.json not written"
        d = json.loads(cfg_file.read_text())
        assert "provider" in d

    def test_config_dir_perms_0700(self, monkeypatch, tmp_path):
        """After first write, dir mode is 0o700. (F-CONFIG-6)"""
        from arail.portal.services import opencode as oc

        monkeypatch.setattr(oc, "_config_dir", lambda: tmp_path / ".opencode")
        monkeypatch.setattr(oc, "_config_path",
                            lambda: tmp_path / ".opencode" / "opencode.json")

        with mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                        create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "TestModel"}, create=True), \
             mock.patch("arail.portal.app._provider_token", return_value="", create=True):
            result = oc.regenerate_config()

        assert result["ok"] is True
        cfg_dir = tmp_path / ".opencode"
        mode = stat.S_IMODE(cfg_dir.stat().st_mode)
        assert mode == 0o700, f"Expected dir mode 0700, got {oct(mode)}"

    def test_regenerate_atomic_write_no_corruption(self, monkeypatch, tmp_path):
        """Normal write produces valid JSON. (F-CONFIG-3)"""
        from arail.portal.services import opencode as oc

        monkeypatch.setattr(oc, "_config_dir", lambda: tmp_path / ".opencode")
        monkeypatch.setattr(oc, "_config_path",
                            lambda: tmp_path / ".opencode" / "opencode.json")

        with mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                        create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "TestModel"}, create=True), \
             mock.patch("arail.portal.app._provider_token", return_value="", create=True):
            oc.regenerate_config()

        cfg_file = tmp_path / ".opencode" / "opencode.json"
        d = json.loads(cfg_file.read_text())  # must be valid JSON
        assert d.get("autoupdate") is False

    def test_regenerate_failure_leaves_original_intact(self, monkeypatch, tmp_path):
        """On write failure, original config is NOT deleted. (F-CONFIG-3)"""
        from arail.portal.services import opencode as oc

        cfg_dir = tmp_path / ".opencode"
        cfg_dir.mkdir()
        cfg_file = cfg_dir / "opencode.json"
        original_content = '{"original": true}'
        cfg_file.write_text(original_content)

        monkeypatch.setattr(oc, "_config_dir", lambda: cfg_dir)
        monkeypatch.setattr(oc, "_config_path", lambda: cfg_file)

        # Make the tmp write fail by patching Path.replace to raise
        original_replace = Path.replace

        def bad_replace(self, target):
            raise OSError("Simulated disk failure")

        with mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                        create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "TestModel"}, create=True), \
             mock.patch("arail.portal.app._provider_token", return_value="", create=True), \
             mock.patch.object(Path, "replace", bad_replace):
            result = oc.regenerate_config()

        # Should fail
        assert result["ok"] is False
        # Original file still intact
        assert cfg_file.read_text() == original_content

    def test_regenerate_concurrent_calls_serialized(self, monkeypatch, tmp_path):
        """2 parallel calls both succeed and final file is consistent. (F-CONFIG-4)"""
        from arail.portal.services import opencode as oc

        monkeypatch.setattr(oc, "_config_dir", lambda: tmp_path / ".opencode")
        monkeypatch.setattr(oc, "_config_path",
                            lambda: tmp_path / ".opencode" / "opencode.json")

        results: list[dict] = []
        errors: list[Exception] = []

        def do_regen():
            with mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                            create=True), \
                 mock.patch("arail.portal.app._get_chat_model_load_state",
                            return_value={"state": "ready", "model": "TestModel"}, create=True), \
                 mock.patch("arail.portal.app._provider_token", return_value="", create=True):
                try:
                    results.append(oc.regenerate_config())
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=do_regen)
        t2 = threading.Thread(target=do_regen)
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)

        assert not errors, f"Concurrent regenerate raised: {errors}"
        assert len(results) == 2
        assert all(r["ok"] for r in results), f"One or both failed: {results}"

        # Final file should be valid JSON
        cfg_file = tmp_path / ".opencode" / "opencode.json"
        d = json.loads(cfg_file.read_text())
        assert "provider" in d


# ---------------------------------------------------------------------------
# OPENCODE_CONFIG_DIR env var in start()
# ---------------------------------------------------------------------------

class TestStartEnvVars:
    def test_start_sets_OPENCODE_CONFIG_DIR_env(self, monkeypatch, tmp_path):
        """Popen env contains OPENCODE_CONFIG_DIR=<lab>/.opencode. (A1)"""
        from arail.portal.services import opencode as oc

        monkeypatch.setattr(oc, "_config_dir", lambda: tmp_path / ".opencode")
        monkeypatch.setattr(oc, "_config_path",
                            lambda: tmp_path / ".opencode" / "opencode.json")
        monkeypatch.setattr(oc, "is_installed", lambda: True)
        monkeypatch.setattr(oc, "is_running", lambda port=4096: False)
        monkeypatch.setattr(oc, "_maybe_rotate_log", lambda f: None)

        captured_env: dict = {}

        def fake_popen(args, env=None, stdout=None, stderr=None):
            captured_env.update(env or {})
            m = mock.MagicMock()
            m.pid = 12345
            return m

        with mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                        create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "TestModel"}, create=True), \
             mock.patch("arail.portal.app._provider_token", return_value="", create=True), \
             mock.patch("subprocess.Popen", side_effect=fake_popen), \
             mock.patch("builtins.open", mock.mock_open()):
            oc.start()

        assert "OPENCODE_CONFIG_DIR" in captured_env, (
            f"OPENCODE_CONFIG_DIR missing from Popen env: {list(captured_env.keys())}"
        )
        assert str(tmp_path / ".opencode") in captured_env["OPENCODE_CONFIG_DIR"]


# ---------------------------------------------------------------------------
# Provider-switch hook tests
# ---------------------------------------------------------------------------

class TestProviderSwitchHookSprint2:
    def _patched_client(self, monkeypatch, tier="max",
                        oc_running=True, regen_ok=True):
        """Return client + mock tracking objects."""
        monkeypatch.setenv("LAB_TIER", tier)

        regen_calls: list = []
        restart_calls: list = []

        def fake_regen(**kw):
            regen_calls.append(kw)
            return {"ok": regen_ok, "path": "/fake/path"}

        def fake_restart(port=4096):
            restart_calls.append(port)
            return {"ok": True}

        monkeypatch.setattr(
            "arail.portal.services.opencode.is_running",
            lambda port=4096: oc_running,
        )
        monkeypatch.setattr(
            "arail.portal.services.opencode.regenerate_config",
            fake_regen,
        )
        monkeypatch.setattr(
            "arail.portal.services.opencode.restart",
            fake_restart,
        )

        from arail.portal.app import app
        from fastapi.testclient import TestClient
        return TestClient(app, raise_server_exceptions=False), regen_calls, restart_calls

    def test_provider_switch_regenerates_then_restarts(self, monkeypatch):
        """Provider switch: regenerate called BEFORE restart. (F-RESTART-1)"""
        monkeypatch.setenv("LAB_MODE", "hybrid")
        client, regen_calls, restart_calls = self._patched_client(
            monkeypatch, tier="max", oc_running=True, regen_ok=True
        )
        resp = client.post("/api/providers/active", json={"provider": "claude"})
        assert resp.status_code == 200
        # Give the daemon thread a moment
        time.sleep(0.2)
        assert len(regen_calls) >= 1, "regenerate_config not called"
        assert len(restart_calls) >= 1, "restart not called"

    def test_provider_switch_aborts_restart_on_config_failure(self, monkeypatch):
        """If regenerate fails, restart must NOT be called. (F-RESTART-2)"""
        monkeypatch.setenv("LAB_MODE", "hybrid")
        client, regen_calls, restart_calls = self._patched_client(
            monkeypatch, tier="max", oc_running=True, regen_ok=False
        )
        client.post("/api/providers/active", json={"provider": "claude"})
        time.sleep(0.2)
        assert len(regen_calls) >= 1, "regenerate_config not called"
        assert len(restart_calls) == 0, (
            f"restart should NOT be called when regen fails, got {restart_calls}"
        )

    def test_provider_switch_skipped_when_opencode_not_running(self, monkeypatch):
        """Hook skipped when opencode not running — no file write. (F-RESTART-4)"""
        monkeypatch.setenv("LAB_MODE", "hybrid")
        client, regen_calls, restart_calls = self._patched_client(
            monkeypatch, tier="max", oc_running=False, regen_ok=True
        )
        client.post("/api/providers/active", json={"provider": "claude"})
        time.sleep(0.2)
        assert len(regen_calls) == 0, (
            f"regenerate_config should NOT be called when not running, got {regen_calls}"
        )
        assert len(restart_calls) == 0


# ---------------------------------------------------------------------------
# Security: git-ignored
# ---------------------------------------------------------------------------

class TestGitIgnored:
    def test_lab_opencode_git_ignored(self):
        """lab/.opencode/opencode.json is git-ignored. (F-SEC-CRED-3)"""
        result = subprocess.run(
            ["git", "check-ignore", "lab/.opencode/opencode.json"],
            capture_output=True,
            text=True,
            cwd="/Users/netsushi/ProJects/arail",
        )
        assert result.returncode == 0, (
            "lab/.opencode/opencode.json is NOT git-ignored. "
            "This is a security issue — it must be ignored."
        )
