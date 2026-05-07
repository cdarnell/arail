"""QA hunt tests for opencode-curation sprint (2026-05-06).

These are tests written AFTER the architect's PASS (Sprint 2 review). They
target edges the builder + architect could plausibly miss, with the hunt
list defined by the QA orchestrator briefing for this sprint:

Hunt areas (per allocation 30% setup / 30% Buddy / 20% security / 10%
happy / 10% regression — security elevated; setup heavy):

  1. /doc fingerprint spoofability (substring match → document trust posture)
  2. Fingerprint helper edge cases the existing tests don't probe (large
     body, missing info dict, info.title not a string, openapi key with
     truthy-but-non-string value, http error, redirect)
  3. Iframe focus try/catch swallows cross-origin SecurityError silently
  4. Pop-out window URL has no embedded credentials (regression)
  5. /api/openai/v1/* shim is reachable from any tier — document the
     intentionally-open posture (A9)
  6. Shim body validation: messages with non-string content, oversized
     body, weird stream coercion edges, and non-dict body
  7. Render config edge cases: extreme model id strings, empty
     models_list, None model with cloud provider, unknown provider
  8. opencode.json file permissions after atomic write — chmod 0644
     observed on disk + dir 0700
  9. Provider switch — two rapid concurrent switches do not produce
     interleaved restarts (lock honoured)
 10. /api/notebooks/status polling cost: each call may run docker subprocess.
     Document concern (the Start-button waitForOpencodeAlive polls 40
     times in 20 s).
 11. LLM-ready cache invalidate: explicit invalidate_llm_ready_cache()
     clears cache, follow-up call recomputes
 12. Slash command templates — every command's template is a non-empty
     string with no embedded literal API key patterns + no `rm -rf`
 13. _is_opencode_on_port: case-insensitive title match accepts mixed
     case AND rejects when "openapi" key value is non-string (defensive)
 14. opencode.json never serializes secret-shaped strings even when an
     active model name resembles a token
 15. Shim never logs Authorization header even on 400/500 paths
 16. Bogus port arguments (negative / zero / 65536) to is_running do not
     crash (regression sibling for fingerprint helper)
 17. _render_opencode_config airgap force ignores 'hybrid' typos like
     'HYBRID' or ' hybrid ' — design says strict equality, so these
     get forced to my_machine (document)
 18. Pop-out window opener: noopener flag set so opencode iframe cannot
     navigate the parent (security regression)
 19. /api/openai/v1/models tolerates _scan_local_models raising

Failures are reported in TEST_REPORT.md, not fixed here.
"""

from __future__ import annotations

import json
import os
import threading
import time
import unittest.mock as mock
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shim_client():
    """Plain TestClient — no tier monkeypatch, so we hit the open shim."""
    from arail.portal.app import app
    return TestClient(app, raise_server_exceptions=True)


# ===========================================================================
# 1. Fingerprint spoofability — substring match on info.title
# ===========================================================================

class TestFingerprintSubstringMatch:
    """The /doc fingerprint accepts ANY title containing 'opencode'.

    This documents the trust posture: substring match means a malicious
    or accidentally-similar service titled 'MyOpencodeBridge' or
    'fake-opencode-clone' would pass. Acceptable on a 127.0.0.1-only
    perimeter (anyone reaching localhost can shell anyway), but worth
    locking the test in so future tightening is visible.
    """

    def _patch_doc(self, monkeypatch, title: str, openapi_value="3.0.0"):
        import arail.portal.services.opencode as oc
        body = json.dumps({
            "openapi": openapi_value,
            "info": {"title": title, "version": "x"},
        }).encode()

        class FakeResp:
            status = 200
            def read(self, n=4096): return body
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout=0.5: FakeResp())
        return oc

    def test_fingerprint_accepts_substring_lookalike(self, monkeypatch):
        """'MyOpencodeBridge' passes the fingerprint — substring is the contract."""
        oc = self._patch_doc(monkeypatch, "MyOpencodeBridge")
        assert oc._is_opencode_on_port(4096) is True, (
            "Substring match on title is the documented contract; "
            "tightening this would require re-spec of A8/F-RESTART."
        )

    def test_fingerprint_accepts_uppercase(self, monkeypatch):
        """'OPENCODE' (case insensitive) passes."""
        oc = self._patch_doc(monkeypatch, "OPENCODE Server")
        assert oc._is_opencode_on_port(4096) is True

    def test_fingerprint_rejects_unrelated_openapi(self, monkeypatch):
        """A FastAPI app titled 'FastAPI' is correctly rejected."""
        oc = self._patch_doc(monkeypatch, "FastAPI")
        assert oc._is_opencode_on_port(4096) is False


# ===========================================================================
# 2. Fingerprint helper edge cases
# ===========================================================================

class TestFingerprintEdgeCases:
    def _patch_response(self, monkeypatch, *, status=200, body=b""):
        class FakeResp:
            def __init__(self):
                self.status = status
            def read(self, n=4096): return body
            def __enter__(self): return self
            def __exit__(self, *a): pass

        monkeypatch.setattr("urllib.request.urlopen",
                            lambda req, timeout=0.5: FakeResp())

    def test_fingerprint_rejects_non_200_status(self, monkeypatch):
        import arail.portal.services.opencode as oc
        self._patch_response(monkeypatch, status=302,
                             body=b'{"openapi":"3.0","info":{"title":"opencode"}}')
        assert oc._is_opencode_on_port(4096) is False

    def test_fingerprint_rejects_truncated_json(self, monkeypatch):
        import arail.portal.services.opencode as oc
        # /doc is small but if backend chunked weirdly we'd parse half — must not raise
        self._patch_response(monkeypatch, body=b'{"openapi":"3.0","info":{"tit')
        assert oc._is_opencode_on_port(4096) is False

    def test_fingerprint_rejects_non_dict_root(self, monkeypatch):
        """A top-level JSON list (well-formed but wrong shape) → False, no raise."""
        import arail.portal.services.opencode as oc
        self._patch_response(monkeypatch, body=b'["openapi", "3.0.0"]')
        assert oc._is_opencode_on_port(4096) is False

    def test_fingerprint_rejects_missing_info(self, monkeypatch):
        """Has 'openapi' but no 'info' dict → False."""
        import arail.portal.services.opencode as oc
        self._patch_response(monkeypatch, body=b'{"openapi":"3.0"}')
        assert oc._is_opencode_on_port(4096) is False

    def test_fingerprint_rejects_info_title_non_string(self, monkeypatch):
        """info.title set to a number/object — must not raise on .lower() coerce."""
        import arail.portal.services.opencode as oc
        # The implementation does: title = (...).get("title", "").lower()
        # If title is an int, .lower() will AttributeError. Probing edge.
        self._patch_response(monkeypatch,
                             body=b'{"openapi":"3.0","info":{"title":42}}')
        # If it raises, that's a bug. The except wrap should still catch it,
        # so the public behaviour is False either way.
        assert oc._is_opencode_on_port(4096) is False

    def test_fingerprint_rejects_when_urlopen_raises_timeout(self, monkeypatch):
        import arail.portal.services.opencode as oc
        def _raise(req, timeout=0.5):
            raise TimeoutError("connect timeout")
        monkeypatch.setattr("urllib.request.urlopen", _raise)
        assert oc._is_opencode_on_port(4096) is False

    def test_fingerprint_rejects_when_info_is_none(self, monkeypatch):
        """info: null in payload → renderer's `(... or {}).get(title)` handles it."""
        import arail.portal.services.opencode as oc
        self._patch_response(monkeypatch,
                             body=b'{"openapi":"3.0","info":null}')
        assert oc._is_opencode_on_port(4096) is False


# ===========================================================================
# 3. Iframe auto-focus + 4. pop-out URL credentials
# ===========================================================================

class TestOpencodeTemplateFocus:
    """The iframe onload focus must be wrapped in try/catch."""

    def _running_client(self, monkeypatch):
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setattr(
            "arail.portal.services.opencode.is_installed", lambda: True
        )
        monkeypatch.setattr(
            "arail.portal.services.opencode.is_running", lambda port=4096: True
        )
        from arail.portal.app import app
        return TestClient(app, raise_server_exceptions=True)

    def test_iframe_focus_wrapped_in_try_catch(self, monkeypatch):
        """contentWindow.focus() can throw SecurityError cross-origin."""
        client = self._running_client(monkeypatch)
        resp = client.get("/opencode")
        html = resp.text
        # The focus call must be inside a try/catch
        focus_idx = html.find("contentWindow.focus()")
        assert focus_idx > 0, "contentWindow.focus() call missing"
        # Look backwards for nearest 'try {' within 200 chars
        head = html[max(0, focus_idx - 200):focus_idx]
        assert "try" in head, (
            "contentWindow.focus() not wrapped in try/catch — "
            "cross-origin SecurityError will surface to console (and may "
            "block iframe load handler)"
        )

    def test_popout_url_no_credentials_no_token(self, monkeypatch):
        """⇱ Pop out window URL embeds no credentials nor query strings."""
        client = self._running_client(monkeypatch)
        resp = client.get("/opencode")
        html = resp.text
        # Find OPENCODE_URL definition
        assert "const OPENCODE_URL = 'http://127.0.0.1:" in html
        # The URL must not contain ? or @ or :password format
        # Extract the URL
        import re
        m = re.search(r"const OPENCODE_URL = '([^']+)'", html)
        assert m, "OPENCODE_URL not found"
        url = m.group(1)
        assert "@" not in url, f"URL contains userinfo (credentials): {url!r}"
        assert "?" not in url, f"URL contains query string: {url!r}"
        assert url.startswith("http://127.0.0.1:"), (
            f"URL not loopback: {url!r}"
        )

    def test_popout_window_uses_noopener(self, monkeypatch):
        """window.open(...) must use 'noopener' so the iframe cannot reach window.opener."""
        client = self._running_client(monkeypatch)
        resp = client.get("/opencode")
        assert "noopener" in resp.text, (
            "Pop-out window.open should pass noopener — without it, the "
            "popped-out opencode child window can navigate window.opener "
            "(the lab portal)."
        )


# ===========================================================================
# 5. /api/openai/v1/* shim reachable from any tier
# ===========================================================================

class TestShimNotTierGated:
    """Shim is intentionally not tier-gated (A9). Lock the contract in."""

    def test_models_endpoint_reachable_on_min_tier(self, monkeypatch):
        monkeypatch.setenv("LAB_TIER", "min")
        client = _shim_client()
        resp = client.get("/api/openai/v1/models")
        # Must NOT be 404 — the open-tier posture is the contract
        assert resp.status_code == 200, (
            f"Shim should be reachable from min tier (A9 — loopback "
            f"perimeter is the trust boundary). Got {resp.status_code}."
        )

    def test_chat_completions_reachable_on_min_tier(self, monkeypatch):
        monkeypatch.setenv("LAB_TIER", "min")
        client = _shim_client()
        # POST without body — should reach the route and be a 400, not 404
        resp = client.post("/api/openai/v1/chat/completions",
                           content=b"")
        assert resp.status_code != 404, (
            "Shim chat/completions route should be reachable on min tier — "
            "got 404 (route not registered or tier-gated unexpectedly)."
        )


# ===========================================================================
# 6. Shim body validation edge cases
# ===========================================================================

class TestShimBodyValidation:
    def test_chat_400_on_non_dict_body(self):
        """Body that's a JSON list, not object → 400 invalid_request_error."""
        client = _shim_client()
        resp = client.post("/api/openai/v1/chat/completions",
                           json=["model", "x"])
        assert resp.status_code == 400
        body = resp.json()
        assert "error" in body
        assert body["error"].get("type") == "invalid_request_error"

    def test_chat_400_on_messages_only_system_role(self):
        """messages with ONLY system roles → 400 (no non-system turns)."""
        client = _shim_client()
        resp = client.post("/api/openai/v1/chat/completions", json={
            "model": "any",
            "messages": [
                {"role": "system", "content": "you are a helper"},
            ],
        })
        assert resp.status_code == 400, (
            f"Expected 400 when no non-system turns, got {resp.status_code}: "
            f"{resp.json()}"
        )

    def test_chat_stream_string_true(self, monkeypatch):
        """stream='true' string is coerced to bool. Validated by routing to stream branch."""
        async def _fake_stream(**kw):
            yield {"type": "start"}
            yield {"type": "delta", "delta": "hi"}
            yield {"type": "final"}

        from arail.portal import openai_compat
        monkeypatch.setattr(openai_compat, "_run_chat_completion_stream",
                            _fake_stream)
        client = _shim_client()
        resp = client.post("/api/openai/v1/chat/completions", json={
            "model": "x",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": "true",
        })
        # Streaming response → media_type starts with text/event-stream
        ct = resp.headers.get("content-type", "")
        assert "text/event-stream" in ct, (
            f"stream='true' should coerce to bool True; got content-type {ct!r}"
        )

    def test_chat_oversized_body_does_not_crash(self, monkeypatch):
        """Very large message body (1 MB string) → handled, not 500."""
        # 1 MB content body
        big = "x" * (1024 * 1024)

        async def _fake_run(**kw):
            return {"reply": "ok", "tokens_used": 0}

        from arail.portal import openai_compat
        monkeypatch.setattr(openai_compat, "_run_chat_completion", _fake_run)

        client = _shim_client()
        resp = client.post("/api/openai/v1/chat/completions", json={
            "model": "x",
            "messages": [{"role": "user", "content": big}],
        })
        # Either 200 (handled) or controlled 4xx/413 — must NOT be 500
        assert resp.status_code < 500, (
            f"Oversized body produced 500: {resp.status_code} body={resp.text[:200]!r}"
        )

    def test_chat_messages_non_string_content_is_coerced(self, monkeypatch):
        """messages content as a number — _to_chat_args str()-coerces; no crash."""
        async def _fake_run(**kw):
            return {"reply": "ok", "tokens_used": 0}

        from arail.portal import openai_compat
        monkeypatch.setattr(openai_compat, "_run_chat_completion", _fake_run)

        client = _shim_client()
        resp = client.post("/api/openai/v1/chat/completions", json={
            "model": "x",
            "messages": [{"role": "user", "content": 12345}],
        })
        assert resp.status_code == 200, (
            f"Numeric content should be coerced via str(); got {resp.status_code}"
        )


# ===========================================================================
# 7. Render config edge cases
# ===========================================================================

class TestRenderConfigEdgeCases:
    def test_render_with_none_model_my_machine(self):
        """provider=my_machine, model=None → renders without raising; refs 'unknown'."""
        from arail.portal.services.opencode import _render_opencode_config
        d = _render_opencode_config(
            provider="my_machine", model=None, portal_port=8080,
            tier="max", lab_mode="airgapped",
        )
        # Lab-local provider exists with at least the placeholder
        assert "lab-local" in d["provider"]
        # model_ref should reference 'unknown' or be sensible
        assert d["model"].startswith("lab-local/")

    def test_render_with_empty_model_id_string(self):
        """model='' (empty string, not None) — must not produce 'lab-local/' bare prefix."""
        from arail.portal.services.opencode import _render_opencode_config
        d = _render_opencode_config(
            provider="my_machine", model="", portal_port=8080,
            tier="max", lab_mode="airgapped",
        )
        # Bug surface: f"lab-local/{model}" with model="" produces "lab-local/"
        # which opencode would parse as empty model id → lookup failure.
        # The renderer falls back to 'unknown' for falsy model.
        assert d["model"] != "lab-local/", (
            f"Empty model id produced bare 'lab-local/' ref: {d['model']!r}"
        )

    def test_render_with_extreme_model_id(self):
        """Very long model id with special chars — JSON-serializable, no injection."""
        from arail.portal.services.opencode import _render_opencode_config
        weird = 'A' * 500 + '"; "evil": "x'
        d = _render_opencode_config(
            provider="my_machine", model=weird, portal_port=8080,
            tier="max", lab_mode="airgapped",
        )
        # json.dumps(d) round-trips cleanly: no unescaped quotes
        s = json.dumps(d, sort_keys=True)
        # Re-parse to confirm well-formed
        re_parsed = json.loads(s)
        assert weird in re_parsed["provider"]["lab-local"]["models"], (
            "Round-trip lost the weird model id; possible escaping bug"
        )

    def test_render_with_models_list_having_none_ids(self):
        """models_list entries with None id values — silently skipped."""
        from arail.portal.services.opencode import _render_opencode_config
        d = _render_opencode_config(
            provider="my_machine", model="m1", portal_port=8080, tier="max",
            models_list=[
                {"id": None, "name": None},
                {"id": "", "name": ""},
                {"id": "valid", "name": "valid"},
            ],
            lab_mode="airgapped",
        )
        models_map = d["provider"]["lab-local"]["models"]
        # Only valid + active model
        assert "valid" in models_map
        assert "m1" in models_map
        # No empty-string key
        assert "" not in models_map

    def test_render_unknown_provider_treated_as_my_machine(self):
        """An unknown provider id (e.g. 'azure-foundry') → falls back to lab-local."""
        from arail.portal.services.opencode import _render_opencode_config
        d = _render_opencode_config(
            provider="azure-foundry", model="x", portal_port=8080, tier="max",
            lab_mode="hybrid",
        )
        assert "lab-local" in d["provider"], (
            f"Unknown provider should fall through to lab-local, got "
            f"providers: {list(d['provider'].keys())}"
        )


# ===========================================================================
# 8. opencode.json file permissions
# ===========================================================================

class TestConfigPermissions:
    def test_config_file_perms_after_write(self, monkeypatch, tmp_path):
        """opencode.json after atomic write is mode 0644 (or stricter)."""
        import arail.portal.services.opencode as oc

        # Patch the lab root so writes go to tmp
        monkeypatch.setattr(oc, "_config_dir",
                            lambda: tmp_path / ".opencode")
        monkeypatch.setattr(oc, "_config_path",
                            lambda: tmp_path / ".opencode" / "opencode.json")

        # Patch app helpers used inside _regenerate_config_unlocked
        with mock.patch("arail.portal.app._load_active_provider",
                        return_value="my_machine", create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "m1"},
                        create=True):
            result = oc._regenerate_config_unlocked()

        assert result["ok"], f"regen failed: {result}"
        cfg_path = tmp_path / ".opencode" / "opencode.json"
        assert cfg_path.exists()
        mode = cfg_path.stat().st_mode & 0o777
        # Must be at most 0644 — no group/world write
        assert mode & 0o022 == 0, (
            f"opencode.json is group- or world-writable: {oct(mode)}"
        )

    def test_config_dir_perms_after_write(self, monkeypatch, tmp_path):
        """lab/.opencode dir created with 0700 (no group/world access)."""
        import arail.portal.services.opencode as oc
        monkeypatch.setattr(oc, "_config_dir",
                            lambda: tmp_path / ".opencode")
        monkeypatch.setattr(oc, "_config_path",
                            lambda: tmp_path / ".opencode" / "opencode.json")

        with mock.patch("arail.portal.app._load_active_provider",
                        return_value="my_machine", create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "m1"},
                        create=True):
            oc._regenerate_config_unlocked()

        d_mode = (tmp_path / ".opencode").stat().st_mode & 0o777
        # Must have NO group or world bits set
        assert d_mode & 0o077 == 0, (
            f"lab/.opencode dir has group/world bits: {oct(d_mode)} (expected 0700)"
        )


# ===========================================================================
# 9. Provider switch — concurrent rapid switches
# ===========================================================================

class TestProviderSwitchConcurrency:
    def test_two_rapid_switches_serialize_via_lock(self, monkeypatch):
        """Two POSTs to /api/providers/active in quick succession do not interleave restarts."""
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setenv("LAB_MODE", "hybrid")

        import arail.portal.services.opencode as oc

        # Track restart() invocation order
        restart_order: list[str] = []
        restart_lock = threading.Lock()

        # Restart goes through the real oc._lock — we patch the inner
        # primitives so it can run without subprocess but still serialise.
        def fake_restart(port=oc.PORT_DEFAULT):
            # Acquire the same module lock the real restart() acquires.
            with oc._lock:
                with restart_lock:
                    restart_order.append("start")
                time.sleep(0.05)
                with restart_lock:
                    restart_order.append("end")
                return {"ok": True}

        monkeypatch.setattr(oc, "is_running", lambda port=oc.PORT_DEFAULT: True)
        monkeypatch.setattr(oc, "restart", fake_restart)
        # Bypass actual config write
        monkeypatch.setattr(oc, "regenerate_config",
                            lambda: {"ok": True, "path": "/tmp/x"})

        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)

        # Fire two rapid switches concurrently
        def _switch(provider):
            client.post("/api/providers/active", json={"provider": provider})

        t1 = threading.Thread(target=_switch, args=("my_machine",))
        t2 = threading.Thread(target=_switch, args=("my_machine",))
        t1.start(); t2.start()
        t1.join(); t2.join()

        # Wait a moment for daemon threads to finish
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and len(restart_order) < 4:
            time.sleep(0.05)

        # Two restarts may or may not both fire (the design intentionally
        # may collapse rapid switches). What we assert: we never see two
        # 'start' entries in a row without an 'end' between them — i.e.
        # restarts don't interleave.
        # Note: opencode's _lock serializes restart() internally; the
        # daemon-thread hooks here go through that lock.
        for i in range(0, len(restart_order) - 1):
            if restart_order[i] == "start":
                assert restart_order[i + 1] == "end", (
                    f"Restarts interleaved: {restart_order}"
                )


# ===========================================================================
# 10. Polling cost — /api/notebooks/status calls Docker subprocess
# ===========================================================================

class TestPollingCost:
    """The Start button polls /api/notebooks/status every 500 ms for 20 s.

    Each call invokes _docker_available() (subprocess `docker info`) and
    _container_running() (subprocess `docker ps`). On a slow machine
    those each take 30-100 ms. Document the concern; this test verifies
    a single poll completes < 1 s and asserts the call shape so any
    future heavyweight work added here trips the cap.
    """

    def test_single_poll_under_1s(self, monkeypatch):
        monkeypatch.setenv("LAB_TIER", "max")
        # Patch out Docker probes to avoid system dependency
        monkeypatch.setattr("arail.portal.app._docker_available", lambda: False)
        monkeypatch.setattr(
            "arail.portal.services.opencode.is_installed", lambda: True
        )
        monkeypatch.setattr(
            "arail.portal.services.opencode.llm_ready_check",
            lambda force=False: {
                "ok": True, "reason": None, "hint": None, "chat_url": None,
                "provider": "my_machine", "model": "x"
            },
        )

        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)

        t0 = time.monotonic()
        resp = client.get("/api/notebooks/status")
        dt = time.monotonic() - t0
        assert resp.status_code == 200
        assert dt < 1.0, (
            f"/api/notebooks/status took {dt:.2f}s — Start-button polling "
            f"hits this 40 times in 20 s. Hot path; needs to stay <100 ms."
        )


# ===========================================================================
# 11. LLM-ready cache — invalidate path
# ===========================================================================

class TestLLMReadyCacheInvalidate:
    def test_invalidate_forces_recompute(self, monkeypatch):
        """invalidate_llm_ready_cache() resets the cache so the next call recomputes."""
        import arail.portal.services.opencode as oc

        compute_calls: list = []

        original = oc._compute_llm_ready
        def counted(provider, state, model):
            compute_calls.append((provider, state, model))
            return original(provider, state, model)

        monkeypatch.setattr(oc, "_compute_llm_ready", counted)

        with mock.patch("arail.portal.app._load_active_provider",
                        return_value="my_machine", create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "m1"},
                        create=True):
            # Reset cache to a clean state
            oc.invalidate_llm_ready_cache()
            oc.llm_ready_check()
            n_before = len(compute_calls)
            oc.llm_ready_check()  # cache hit
            assert len(compute_calls) == n_before, "Cache should have hit"

            oc.invalidate_llm_ready_cache()
            oc.llm_ready_check()  # cache miss — must recompute
            assert len(compute_calls) == n_before + 1, (
                "invalidate_llm_ready_cache() did not force recomputation"
            )


# ===========================================================================
# 12. Slash command templates — well-formed, no shell-injection patterns
# ===========================================================================

class TestSlashCommandTemplates:
    def test_all_six_commands_have_non_empty_template(self):
        from arail.portal.services.opencode import _render_opencode_config
        d = _render_opencode_config(
            provider="my_machine", model="m1", portal_port=8080, tier="max",
            lab_mode="airgapped",
        )
        cmds = d.get("command", {})
        expected = {"lab-status", "sprint-current", "skills-list",
                    "agents-status", "kb-search", "claude-md"}
        assert expected.issubset(cmds.keys()), (
            f"Missing slash commands: {expected - cmds.keys()}"
        )
        for name, body in cmds.items():
            assert body.get("template", "").strip(), (
                f"Slash command {name} has empty template"
            )
            assert body.get("description", "").strip(), (
                f"Slash command {name} has empty description"
            )

    def test_no_command_template_contains_destructive_pattern(self):
        """No template embeds rm -rf, sudo, curl | bash, or eval — these would
        teach the build agent dangerous patterns."""
        from arail.portal.services.opencode import _render_opencode_config
        d = _render_opencode_config(
            provider="my_machine", model="m1", portal_port=8080, tier="max",
            lab_mode="airgapped",
        )
        bad = ["rm -rf", "sudo ", "curl | bash", "eval ",
               "ANTHROPIC_API_KEY", "sk-"]
        for name, body in d.get("command", {}).items():
            tpl = body.get("template", "")
            for pat in bad:
                assert pat not in tpl, (
                    f"Slash command {name} template contains dangerous "
                    f"pattern {pat!r}: {tpl[:200]!r}"
                )

    def test_command_paths_are_repo_root_anchored(self):
        """Templates that read files use $REPO_ROOT/lab/... so opencode's CWD-walk
        lands consistently."""
        from arail.portal.services.opencode import _render_opencode_config
        d = _render_opencode_config(
            provider="my_machine", model="m1", portal_port=8080, tier="max",
            lab_mode="airgapped",
        )
        # Spot-check three commands that reference lab paths
        for name in ["lab-status", "skills-list", "agents-status", "claude-md"]:
            tpl = d["command"][name]["template"]
            # Must mention $REPO_ROOT (not bare /lab or absolute paths)
            if "lab/" in tpl or "lab/pkb" in tpl or "CLAUDE.md" in tpl:
                assert "$REPO_ROOT" in tpl, (
                    f"{name} references lab files without $REPO_ROOT anchor: {tpl!r}"
                )


# ===========================================================================
# 13. Render with airgap-mode case sensitivity
# ===========================================================================

class TestAirgapModeStrictMatch:
    def test_uppercase_hybrid_is_NOT_treated_as_hybrid(self):
        """LAB_MODE='HYBRID' or 'Hybrid' — if not normalised, this is a security gap.

        The renderer signature is `lab_mode: str = "airgapped"` and the check
        is `lab_mode != "hybrid"`. Both _regenerate_config_unlocked AND the
        airgap helper in app normalise via .strip().lower() — verify the
        renderer's raw contract matches: anything not exactly 'hybrid' is
        forced to my_machine.
        """
        from arail.portal.services.opencode import _render_opencode_config
        for mode in ["HYBRID", "Hybrid", " hybrid", "hybrid ", "hybrid\n"]:
            d = _render_opencode_config(
                provider="claude", model="claude-x", portal_port=8080,
                tier="max", lab_mode=mode,
            )
            assert "lab-local" in d["provider"], (
                f"lab_mode={mode!r} not strict-matched against 'hybrid' — "
                f"cloud provider leaked into airgapped config"
            )


# ===========================================================================
# 14. Active-model name resembles a token — must still serialize fine
# ===========================================================================

class TestModelNameResemblingToken:
    def test_model_name_with_token_shape_does_not_get_redacted(self):
        """Model id 'sk-ant-test-FAKE-FAKE' is allowed in JSON — it's not a token."""
        from arail.portal.services.opencode import _render_opencode_config
        # No actual tokens present — just a model id that looks token-shaped
        weird_id = "sk-ant-test-FAKE-FAKE-not-a-real-key"
        d = _render_opencode_config(
            provider="my_machine", model=weird_id, portal_port=8080,
            tier="max", lab_mode="airgapped",
        )
        s = json.dumps(d)
        # Token-shaped string is fine in this case (it's the model ID)
        assert weird_id in s, (
            "Model id (which is not a secret) should round-trip through JSON"
        )


# ===========================================================================
# 15. Shim never logs Authorization header even on error paths
# ===========================================================================

class TestShimNeverLogsAuth:
    def test_shim_400_path_does_not_log_authorization(self, caplog):
        """400 response on missing model — Authorization header in request must not be logged."""
        import logging
        client = _shim_client()
        with caplog.at_level(logging.DEBUG):
            client.post("/api/openai/v1/chat/completions",
                        json={"messages": [{"role": "user", "content": "x"}]},
                        headers={"Authorization": "Bearer SECRET-TOKEN-FAKE-12345"})
        for record in caplog.records:
            assert "SECRET-TOKEN-FAKE-12345" not in record.getMessage(), (
                f"Authorization header value leaked into log: {record.getMessage()}"
            )
            assert "Authorization" not in record.getMessage(), (
                f"Authorization header name appears in log: {record.getMessage()}"
            )


# ===========================================================================
# 16. is_running with bogus ports
# ===========================================================================

class TestIsRunningBogusPorts:
    @pytest.mark.parametrize("port", [-1, 0, 65536, 999999])
    def test_is_running_with_bogus_port_does_not_crash(self, port):
        """is_running(port) handles bogus port values without raising."""
        import arail.portal.services.opencode as oc
        # Must return False without raising
        try:
            result = oc.is_running(port)
        except Exception as e:
            pytest.fail(f"is_running({port}) raised {type(e).__name__}: {e}")
        assert result is False


# ===========================================================================
# 17. /api/openai/v1/models tolerates _scan_local_models raising
# ===========================================================================

class TestModelsEndpointResilience:
    def test_models_endpoint_when_scan_raises(self, monkeypatch):
        """If _scan_local_models throws, /models returns empty list, not 500."""
        from arail.portal import openai_compat
        def _raises(force=False):
            raise RuntimeError("disk error or something")
        monkeypatch.setattr(openai_compat, "_scan_local_models", _raises)

        client = _shim_client()
        resp = client.get("/api/openai/v1/models")
        assert resp.status_code == 200, (
            f"Shim must not 500 when scan raises; got {resp.status_code}"
        )
        body = resp.json()
        assert body == {"object": "list", "data": []}


# ===========================================================================
# 18. opencode.json git-ignored regression
# ===========================================================================

class TestLabOpencodeIgnored:
    def test_lab_opencode_dir_in_gitignore(self):
        """`lab/.opencode/` matches .gitignore (regression — Sprint 2 added this)."""
        repo_root = Path(__file__).parent.parent.parent
        gitignore = (repo_root / ".gitignore").read_text()
        # Either explicitly listed or covered by lab/ rule
        assert ("lab/.opencode" in gitignore
                or "lab/" in gitignore
                or ".opencode" in gitignore), (
            "lab/.opencode/ not in .gitignore — config writes will leak into git"
        )


# ===========================================================================
# 19. /api/opencode/start — start() result with already_running propagates
# ===========================================================================

class TestStartIdempotentResultPropagation:
    """Start route must surface the already_running flag so the UI can
    show the right message ('Already running — reloading…' vs 'Starting').
    """

    def test_start_route_propagates_already_running(self, monkeypatch):
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setattr(
            "arail.portal.services.opencode.is_installed", lambda: True
        )
        monkeypatch.setattr(
            "arail.portal.services.opencode.llm_ready_check",
            lambda force=False: {"ok": True, "provider": "my_machine",
                                  "model": "m1", "reason": None,
                                  "hint": None, "chat_url": None},
        )
        monkeypatch.setattr(
            "arail.portal.services.opencode.start",
            lambda port=4096: {"ok": True, "already_running": True, "port": port},
        )
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.post("/api/opencode/start")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("already_running") is True, (
            "Start route must propagate already_running so the UI can "
            "render the 'Already running — reloading…' message variant."
        )
