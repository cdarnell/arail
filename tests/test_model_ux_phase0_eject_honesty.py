"""Phase 0 (display fidelity) — C5: `/api/chat/eject` terminal return is
honest — `ok` and `requires_restart` track what actually happened, never
an unconditional `{"ok": True}`.

Sprint: 2026-07-20-model-ux-unification
Architecture: sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md
Implementation-order step 5 (§2.3).

Failure modes covered:
  F-EJECTLIE              — aeroLLM/AirLLM eject reports success while the
                             multi-GB singleton stays pinned (T-EJECT-AERO).
  F-EJECT-OLLAMA-FALSE    — `ollama stop` fails/non-zero but eject used to
                             return `ok:true` regardless (T-EJECT-OLLAMA-FAIL).

Not covered here (needs a real `ollama` daemon, out of unit-test reach):
  F-EJECTREAL / T-EJECT-OLLAMA — the happy-path "ollama stop succeeds and
  the model really drops off `ollama ps`" cross-process check. QA's
  Persistence & Honesty suite runs this on real hardware per
  ARCHITECTURE.md's Test Strategy.
"""

from __future__ import annotations

import os
import subprocess
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def _client():
    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod
    return TestClient(app_mod.app), app_mod


# ---------------------------------------------------------------------------
# F-EJECTLIE — aeroLLM / AirLLM eject is never a false success
# ---------------------------------------------------------------------------

def test_eject_aerollm_never_reports_ok_true_and_names_the_real_backend(monkeypatch):
    client, app_mod = _client()
    # Simulate a resident aeroLLM backend sitting in the wrapper cache.
    sentinel = object()
    monkeypatch.setitem(app_mod._OPTIONAL_CHAT_BACKEND_CACHE, "aerollm", sentinel)

    r = client.post("/api/chat/eject", json={"runtime": "aerollm"})
    assert r.status_code == 200
    body = r.json()

    assert body["ok"] is False, "aeroLLM eject must never report ok:true (A3 — cannot hot-free this sprint)"
    assert body["requires_restart"] is True
    assert body["freed"] == [], "dropping the wrapper cache frees nothing real — must not be claimed as freed"
    assert any("AeroLLM" in n for n in body["notes"]), body["notes"]
    # The wrapper cache is untouched — a stale/direct call must not corrupt
    # state the load path relies on.
    assert app_mod._OPTIONAL_CHAT_BACKEND_CACHE.get("aerollm") is sentinel


def test_eject_airllm_names_airllm_not_aerollm(monkeypatch):
    """Finding 5: AirLLM is AirLLM, not aeroLLM — the note must name the
    row's real backend, not a generic/wrong one."""
    client, app_mod = _client()
    monkeypatch.setitem(app_mod._OPTIONAL_CHAT_BACKEND_CACHE, "airllm", object())

    r = client.post("/api/chat/eject", json={"runtime": "airllm"})
    body = r.json()

    assert body["ok"] is False
    assert body["requires_restart"] is True
    assert any("AirLLM" in n for n in body["notes"]), body["notes"]
    assert not any("aeroLLM" in n for n in body["notes"]), (
        "AirLLM eject must not stamp aeroLLM copy onto the note"
    )


def test_eject_aerollm_when_not_loaded_says_so_and_still_refuses(monkeypatch):
    client, app_mod = _client()
    monkeypatch.delitem(app_mod._OPTIONAL_CHAT_BACKEND_CACHE, "aerollm", raising=False)

    r = client.post("/api/chat/eject", json={"runtime": "aerollm"})
    body = r.json()
    assert body["ok"] is False
    assert body["requires_restart"] is True
    assert body["freed"] == []


# ---------------------------------------------------------------------------
# F-EJECT-OLLAMA-FALSE — ok tracks the real subprocess result
# ---------------------------------------------------------------------------

def test_eject_ollama_nonzero_returncode_is_ok_false(monkeypatch):
    client, app_mod = _client()
    monkeypatch.setattr(
        app_mod, "_validate_local_model_id_relaxed", lambda model_id: (True, "")
    )

    class _FakeCompleted:
        returncode = 1
        stderr = "Error: model 'ghost:latest' not found"
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeCompleted())

    r = client.post("/api/chat/eject", json={"runtime": "ollama", "model": "ghost:latest"})
    assert r.status_code == 200
    body = r.json()

    assert body["ok"] is False, "a non-zero `ollama stop` return code must not report ok:true"
    assert body["freed"] == []
    assert any("1" in n or "not found" in n for n in body["notes"])


def test_eject_ollama_daemon_unreachable_is_ok_false_not_raised(monkeypatch):
    client, app_mod = _client()
    monkeypatch.setattr(
        app_mod, "_validate_local_model_id_relaxed", lambda model_id: (True, "")
    )

    def _boom(*a, **kw):
        raise ConnectionRefusedError("ollama daemon not reachable")

    monkeypatch.setattr(subprocess, "run", _boom)

    r = client.post("/api/chat/eject", json={"runtime": "ollama", "model": "llama3.2:1b"})
    assert r.status_code == 200
    body = r.json()

    assert body["ok"] is False
    assert body["freed"] == []
    assert body["requires_restart"] is False


def test_eject_ollama_success_reports_ok_true_and_freed(monkeypatch):
    client, app_mod = _client()
    monkeypatch.setattr(
        app_mod, "_validate_local_model_id_relaxed", lambda model_id: (True, "")
    )

    class _FakeCompleted:
        returncode = 0
        stderr = ""
        stdout = "stopped"

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeCompleted())

    r = client.post("/api/chat/eject", json={"runtime": "ollama", "model": "llama3.2:1b"})
    body = r.json()

    assert body["ok"] is True
    assert body["freed"] == ["ollama:llama3.2:1b"]
    assert body["requires_restart"] is False


def test_eject_ollama_rejects_unvalidated_model_id():
    """Security: the model id reaches subprocess.run as an argv element,
    but must still be gated by the relaxed local-id validator before we
    even try — a stray path-traversal string must not reach `ollama stop`."""
    client, _ = _client()
    r = client.post("/api/chat/eject", json={"runtime": "ollama", "model": "../../etc/passwd"})
    body = r.json()
    assert body["ok"] is False
    assert "error" in body


def test_eject_terminal_return_always_has_requires_restart_key(monkeypatch):
    """C5: `{"ok": ok, "freed": freed, "notes": notes, "requires_restart":
    requires_restart}` — never a bare ok:true missing the new key, across
    every runtime branch."""
    client, app_mod = _client()
    for runtime in ("aerollm", "airllm", "mlx-openai", "mlx", "cpu", "cuda", ""):
        r = client.post("/api/chat/eject", json={"runtime": runtime})
        body = r.json()
        assert "requires_restart" in body, f"runtime={runtime!r} missing requires_restart"
        assert "ok" in body and "freed" in body and "notes" in body


def test_eject_blank_runtime_clears_cache_and_notes_restart_need(monkeypatch):
    client, app_mod = _client()
    monkeypatch.setitem(app_mod._OPTIONAL_CHAT_BACKEND_CACHE, "aerollm", object())

    r = client.post("/api/chat/eject", json={})
    body = r.json()

    assert body["ok"] is True
    assert body["freed"] == ["aerollm cache"]
    assert body["requires_restart"] is True
    assert any("restart" in n for n in body["notes"])
    assert "aerollm" not in app_mod._OPTIONAL_CHAT_BACKEND_CACHE
