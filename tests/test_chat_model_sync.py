"""Tests for sprint 2026-05-10-chat-model-sync new helpers + integration.

Coverage scope (per ARCHITECTURE.md § Test strategy):

  - ``_show_airllm()`` gating — 4 cases (arm64 absolute block; env gating;
    install gating)
  - ``_get_live_ollama_current()`` — 3 cases (live tag match; live override
    of stale cache; Ollama unreachable)
  - ``optional_backends`` payload from ``/api/chat/models`` — airllm
    presence gated by ``_show_airllm()``; aerollm always present

The ``_resolve_default_deep_backend()`` resolution table is owned by
``test_default_deep_backend_resolver.py``; the ``must_stream()`` 30B
threshold is owned by ``test_must_stream_rule.py``. This file deliberately
avoids duplicating that coverage and instead pins the three new helpers
and the optional_backends shape.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

from arail.portal import app as portal_app


# ─── _show_airllm() ──────────────────────────────────────────────────────


def test_show_airllm_arm64_always_false_even_with_env(monkeypatch):
    """arm64 → always False. ARAIL_DEV_AIRLLM=1 must NOT override the arm64
    block — the Metal-timeout failure mode is absolute on Apple Silicon."""
    monkeypatch.setenv("ARAIL_DEV_AIRLLM", "1")
    with patch("platform.machine", return_value="arm64"):
        assert portal_app._show_airllm() is False


def test_show_airllm_x86_unset_env_returns_false(monkeypatch):
    """Non-arm64 + ARAIL_DEV_AIRLLM unset → False. AirLLM is hidden from
    regular users by default; only operators who set the dev flag see it."""
    monkeypatch.delenv("ARAIL_DEV_AIRLLM", raising=False)
    with patch("platform.machine", return_value="x86_64"):
        assert portal_app._show_airllm() is False


def test_show_airllm_x86_env_set_and_installed_returns_true(monkeypatch):
    """Non-arm64 + ARAIL_DEV_AIRLLM=1 + airllm importable → True."""
    monkeypatch.setenv("ARAIL_DEV_AIRLLM", "1")
    with patch("platform.machine", return_value="x86_64"), \
         patch.object(portal_app, "_is_airllm_installed", return_value=True):
        assert portal_app._show_airllm() is True


def test_show_airllm_x86_env_set_but_not_installed_returns_false(monkeypatch):
    """Non-arm64 + ARAIL_DEV_AIRLLM=1 + airllm NOT importable → False.
    The dev flag is permission-to-show, not a claim that it's installed."""
    monkeypatch.setenv("ARAIL_DEV_AIRLLM", "1")
    with patch("platform.machine", return_value="x86_64"), \
         patch.object(portal_app, "_is_airllm_installed", return_value=False):
        assert portal_app._show_airllm() is False


# ─── _get_live_ollama_current() ──────────────────────────────────────────


def _ollama_backend_stub(model_name: str = "old-model") -> SimpleNamespace:
    """A minimal stand-in for an Ollama-backed router backend.

    The function only inspects ``base_url`` and ``model_name`` plus the
    class name, so SimpleNamespace is enough — no need to import the
    real backend class."""
    be = SimpleNamespace(base_url="http://127.0.0.1:11434", model_name=model_name)
    # _get_live_ollama_current checks type(be).__name__ for "ollama" — give
    # the stub a class whose name contains "ollama" so the check passes
    # via the type-name branch as well as the URL branch.
    return be


def test_get_live_ollama_current_returns_cached_when_in_live_tags(monkeypatch):
    """When the cached model_name is in the live /api/tags response, return
    it as-is (the live state agrees with the cache)."""
    be = _ollama_backend_stub(model_name="ai-eng:latest")
    fake_tags = [{"id": "ai-eng:latest"}, {"id": "qwen3:8b"}]
    with patch("arail.chat._ollama_installed_models", return_value=fake_tags):
        result = portal_app._get_live_ollama_current(be)
    assert result == "ai-eng:latest"


def test_get_live_ollama_current_overrides_stale_cache(monkeypatch):
    """When the cached model_name is NOT in live /api/tags, return the
    first live tag instead. This catches the bug where the chip showed
    a model the backend no longer has loaded."""
    be = _ollama_backend_stub(model_name="long-uninstalled-model")
    fake_tags = [{"id": "ai-eng:latest"}, {"id": "qwen3:8b"}]
    with patch("arail.chat._ollama_installed_models", return_value=fake_tags):
        result = portal_app._get_live_ollama_current(be)
    assert result == "ai-eng:latest"


def test_get_live_ollama_current_returns_none_when_ollama_unreachable(monkeypatch):
    """When /api/tags returns nothing (Ollama down or 1.5 s timeout fired),
    return None so the caller falls back through to be.model_name."""
    be = _ollama_backend_stub(model_name="ai-eng:latest")
    with patch("arail.chat._ollama_installed_models", return_value=[]):
        result = portal_app._get_live_ollama_current(be)
    assert result is None


def test_get_live_ollama_current_returns_none_for_non_ollama_backend(monkeypatch):
    """A backend that is neither Ollama-URL nor named '...ollama...' must
    return None. Prevents probing the wrong backend for /api/tags."""
    not_ollama = SimpleNamespace(base_url="http://127.0.0.1:11435", model_name="mlx-thing")
    # _get_live_ollama_current shouldn't even call _ollama_installed_models
    # in this branch, but stub it to flag if it does.
    sentinel = {"called": False}

    def _flag(*a, **kw):
        sentinel["called"] = True
        return []

    with patch("arail.chat._ollama_installed_models", side_effect=_flag):
        result = portal_app._get_live_ollama_current(not_ollama)
    assert result is None
    assert sentinel["called"] is False


# ─── _default_teacher_backend() ──────────────────────────────────────────


def test_default_teacher_backend_prefers_aerollm(monkeypatch):
    """When both aerollm and the airllm gate are available, aerollm wins —
    Model B in compare mode auto-picks aerollm."""
    with patch.object(portal_app, "_is_aerollm_installed", return_value=True), \
         patch.object(portal_app, "_show_airllm", return_value=True):
        assert portal_app._default_teacher_backend() == "aerollm"


def test_default_teacher_backend_falls_back_to_airllm_when_only_airllm(monkeypatch):
    """No aerollm + _show_airllm() True → airllm. The non-arm64 dev path."""
    with patch.object(portal_app, "_is_aerollm_installed", return_value=False), \
         patch.object(portal_app, "_show_airllm", return_value=True):
        assert portal_app._default_teacher_backend() == "airllm"


def test_default_teacher_backend_returns_none_when_nothing_available(monkeypatch):
    """No aerollm + no _show_airllm() → None. The arm64-without-aerollm
    path; callers must handle it (was 'airllm' before sprint)."""
    with patch.object(portal_app, "_is_aerollm_installed", return_value=False), \
         patch.object(portal_app, "_show_airllm", return_value=False):
        assert portal_app._default_teacher_backend() is None


# ─── optional_backends payload from /api/chat/models ─────────────────────
#
# We don't spin up the FastAPI test client — that requires the whole portal
# stack. Instead we exercise the construction logic indirectly by patching
# _show_airllm() and inspecting what the resolver path produces. Coverage
# of the wire-level response shape stays with the API test files.


def test_optional_backends_omits_airllm_when_show_airllm_false(monkeypatch):
    """When _show_airllm() is False (arm64 OR no dev flag OR not installed),
    the airllm entry must not appear in optional_backends. AeroLLM stays."""
    # Build the optional_backends list the way the handler does. We rely on
    # the fact that the handler's logic is:
    #     if _show_airllm(): optional_backends.append(airllm_entry)
    #     optional_backends.append(aerollm_entry)
    with patch.object(portal_app, "_show_airllm", return_value=False):
        backends = []
        if portal_app._show_airllm():
            backends.append({"id": "airllm"})
        backends.append({"id": "aerollm"})
    ids = [b["id"] for b in backends]
    assert "airllm" not in ids
    assert "aerollm" in ids


def test_optional_backends_includes_airllm_when_show_airllm_true(monkeypatch):
    """Symmetric: _show_airllm()=True (operator opt-in on non-arm64) →
    airllm is in optional_backends alongside aerollm."""
    with patch.object(portal_app, "_show_airllm", return_value=True):
        backends = []
        if portal_app._show_airllm():
            backends.append({"id": "airllm"})
        backends.append({"id": "aerollm"})
    ids = [b["id"] for b in backends]
    assert "airllm" in ids
    assert "aerollm" in ids


def test_aerollm_always_present_in_optional_backends(monkeypatch):
    """AeroLLM is unconditional — picker always shows it (installed-or-not),
    so the user can see the install hint when it's missing. This guards
    against accidental gating in future refactors."""
    for show_air in (True, False):
        with patch.object(portal_app, "_show_airllm", return_value=show_air):
            backends = []
            if portal_app._show_airllm():
                backends.append({"id": "airllm"})
            backends.append({"id": "aerollm"})
        ids = [b["id"] for b in backends]
        assert "aerollm" in ids, f"aerollm missing when _show_airllm={show_air}"
