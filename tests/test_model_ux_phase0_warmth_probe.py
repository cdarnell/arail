"""Phase 0 (display fidelity) — F-WARMDOT: the warm-dot / badge tracks
real residency, never `installed` or client-side in-memory state.

Sprint: 2026-07-20-model-ux-unification
Architecture: sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md
Implementation-order step 8 (warmth probe).

  - Ollama rows: real, live `ollama ps` (never `/api/tags`'s "installed",
    never a client-only Set that starts empty every page load).
  - aeroLLM: `model_warmth._tier1_resident()` — inspects
    `AeroLLMBackend._shared` without constructing anything.
  - AirLLM: presence in the thin wrapper cache (best-effort — AirLLM is
    subprocess-isolated and has no equivalent of `_shared`).

Also covers C5/finding 6's UI half: deep rows (aeroLLM/AirLLM) never
render an Unload/Eject affordance in the rail or active-card — only
Load, since the singleton cannot be hot-freed this sprint (A3).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

_CHAT_HTML = os.path.join(
    _REPO_ROOT, "src", "arail", "portal", "templates", "chat.html"
)


def _chat_html_text() -> str:
    with open(_CHAT_HTML, "r", encoding="utf-8") as f:
        return f.read()


def _client():
    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod
    return TestClient(app_mod.app), app_mod


# ---------------------------------------------------------------------------
# Server: _ollama_ps_resident_ids — live probe, short timeout, cached
# fallback on failure
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, payload: dict, status: int = 200):
        self._body = json.dumps(payload).encode()
        self.status = status

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ollama_ps_resident_ids_reads_live_ps_not_tags(monkeypatch):
    import arail.portal.app as app_mod

    calls = []

    def _fake_urlopen(req, timeout=None):
        calls.append((req.full_url, timeout))
        return _FakeResp({"models": [{"name": "llama3.2:1b"}, {"model": "qwen2.5:7b"}]})

    import urllib.request as _ureq
    monkeypatch.setattr(_ureq, "urlopen", _fake_urlopen)

    ids = app_mod._ollama_ps_resident_ids()
    assert ids == {"llama3.2:1b", "qwen2.5:7b"}
    assert calls, "must actually make a request"
    assert "/api/ps" in calls[0][0], "must probe /api/ps (live), not /api/tags (installed)"
    assert calls[0][1] <= 1.0, "Performance guard: probe timeout must be <=1s"


def test_ollama_ps_resident_ids_falls_back_to_last_known_on_timeout(monkeypatch):
    import arail.portal.app as app_mod
    import urllib.request as _ureq

    # First call succeeds and populates the last-known cache.
    monkeypatch.setattr(_ureq, "urlopen", lambda req, timeout=None: _FakeResp(
        {"models": [{"name": "gemma-4-26b-a4b:latest"}]}
    ))
    first = app_mod._ollama_ps_resident_ids()
    assert first == {"gemma-4-26b-a4b:latest"}

    # Second call times out — must NOT silently report everything cold.
    def _boom(req, timeout=None):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(_ureq, "urlopen", _boom)
    second = app_mod._ollama_ps_resident_ids()
    assert second == {"gemma-4-26b-a4b:latest"}, (
        "a failed/timed-out probe must fall back to the last-known reading, "
        "not silently claim every row is cold"
    )


def test_build_local_model_entry_warm_field_reflects_the_probe():
    import arail.portal.app as app_mod

    warm_entry = app_mod._build_local_model_entry(
        "gemma-4-26b-a4b:latest", runtime="ollama", size_gb=14.4, modified="",
        endpoint="http://127.0.0.1:11434/v1", current=None,
        detected_gb=24.0, free_gb=6.0, warm=True,
    )
    cold_entry = app_mod._build_local_model_entry(
        "gemma-4-26b-a4b:latest", runtime="ollama", size_gb=14.4, modified="",
        endpoint="http://127.0.0.1:11434/v1", current=None,
        detected_gb=24.0, free_gb=6.0, warm=False,
    )
    assert warm_entry["warm"] is True
    assert cold_entry["warm"] is False


# ---------------------------------------------------------------------------
# Server: optional_backends carries a real `resident` probe, never
# `installed`, and aeroLLM is never marked `streamed`
# ---------------------------------------------------------------------------

def test_optional_backends_aerollm_resident_is_tier1_resident_not_installed(monkeypatch, tmp_path):
    client, app_mod = _client()
    import arail.chat as chat_mod
    from arail.portal import model_warmth

    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(app_mod, "_local_memory_snapshot", lambda: {
        "label": "Apple M5", "gpu_label": None,
        "total_gb": 24.0, "used_gb": 6.0, "free_gb": 18.0,
    })
    monkeypatch.setattr(chat_mod, "gallery_view", lambda: {
        "installed": [], "catalog": [], "runtime_counts": {},
    })
    monkeypatch.setattr(app_mod, "_is_aerollm_installed", lambda: True)
    monkeypatch.setattr(model_warmth, "_tier1_resident", lambda: True)
    # app.py imports the symbol locally at call time via
    # `from arail.portal.model_warmth import _tier1_resident`, so patching
    # the module attribute above is what the running code actually sees.

    r = client.get("/api/chat/models")
    body = r.json()
    aerollm_entry = next(b for b in body["optional_backends"] if b["id"] == "aerollm")

    assert aerollm_entry["resident"] is True
    assert aerollm_entry["streamed"] is False, (
        "F-OVERSELL: aeroLLM must never be marked streamed — it keeps its "
        "model resident once loaded"
    )


def test_optional_backends_aerollm_resident_false_when_cold(monkeypatch, tmp_path):
    client, app_mod = _client()
    import arail.chat as chat_mod
    from arail.portal import model_warmth

    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setattr(app_mod, "_local_memory_snapshot", lambda: {
        "label": "Apple M5", "gpu_label": None,
        "total_gb": 24.0, "used_gb": 6.0, "free_gb": 18.0,
    })
    monkeypatch.setattr(chat_mod, "gallery_view", lambda: {
        "installed": [], "catalog": [], "runtime_counts": {},
    })
    monkeypatch.setattr(app_mod, "_is_aerollm_installed", lambda: True)
    monkeypatch.setattr(model_warmth, "_tier1_resident", lambda: False)

    r = client.get("/api/chat/models")
    body = r.json()
    aerollm_entry = next(b for b in body["optional_backends"] if b["id"] == "aerollm")
    assert aerollm_entry["resident"] is False, (
        "installed-but-cold must not report resident=True — a cold "
        "singleton must not claim residency"
    )


# ---------------------------------------------------------------------------
# Frontend: deep rows never render an eject/unload affordance; badge
# copy is warmth-driven and backend-accurate
# ---------------------------------------------------------------------------

def test_chat_html_rail_card_never_renders_eject_for_deep_rows():
    text = _chat_html_text()
    assert "const isDeep = m.badge === 'deep';" in text
    assert "isDeep ? null : card.querySelector('[data-act=\"eject\"]')" in text


def test_chat_html_active_card_never_renders_eject_for_deep_active_model():
    text = _chat_html_text()
    assert "const isDeepActive = m.badge === 'deep';" in text
    assert "isDeepActive ? '' : '<button class=\"mc-act eject\" data-eject=\"A\"" in text


def test_chat_html_deep_row_badge_text_is_warmth_driven_and_backend_accurate():
    text = _chat_html_text()
    assert "resident (${deepBackendLabel})" in text
    assert "installed (${deepBackendLabel}) · load to warm" in text
    assert (
        "const deepBackendLabel = m.runtime === 'aerollm' ? 'aeroLLM'"
    ) in text


def test_chat_html_seeds_warm_models_from_server_truth_not_only_client_actions():
    text = _chat_html_text()
    assert "if (m.warm || m.resident) State.warmModels.add(m.id);" in text


def test_chat_html_warm_deep_row_explains_why_it_cant_be_unloaded():
    """A WARM deep row (aeroLLM/AirLLM) must never render a bare "load"
    button with zero unload signal — that's silent, not honest, and a
    real operator flagged it as indistinguishable from a missing/broken
    eject button. It should get the same disabled "can't hot-free"
    affordance a warm mlx/cpu/cuda row gets, not go quiet instead."""
    text = _chat_html_text()
    assert "if (isDeep && isWarm) return" in text
    assert "keeps its model resident once loaded" in text
    assert "can't be hot-freed in-process" in text
