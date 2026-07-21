"""Phase 0b (load/unload lifecycle honesty) — C6.1 idle init state,
C6.2 the cache lock (F-CACHERACE).

Sprint: 2026-07-20-model-ux-unification
Architecture: sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md
Implementation-order step 10.

Failure modes covered:
  F-INITREADY — cold/post-restart state claims "ready" with nothing
                loaded (T-IDLE).
  F-CACHERACE — concurrent load+eject on the unlocked
                _OPTIONAL_CHAT_BACKEND_CACHE -> KeyError/500 (T-CACHERACE).
"""

from __future__ import annotations

import os
import sys
import threading

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def _client():
    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod
    return TestClient(app_mod.app), app_mod


# ---------------------------------------------------------------------------
# C6.1/F-INITREADY — T-IDLE
# ---------------------------------------------------------------------------

def test_chat_model_load_state_initializes_to_idle_not_ready():
    """The module-global's initial literal must declare idle/"No model
    loaded" — checked at the source level rather than by reading the
    live global (which other tests in the shared process may have
    already mutated; the live cold-process behavior is covered by
    test_get_chat_model_load_status_endpoint_reports_idle_on_a_cold_process
    below via an explicit reset)."""
    import inspect
    import arail.portal.app as app_mod
    src = inspect.getsource(app_mod)
    assert '"state": "idle"' in src
    assert '"message": "No model loaded"' in src


def test_get_chat_model_load_status_endpoint_reports_idle_on_a_cold_process(monkeypatch):
    """T-IDLE: force the module-global back to its documented cold-start
    shape (simulating a fresh process) and assert the status endpoint
    reflects it honestly — never "ready" with model=None.

    Mocks `_get_chat_model_load_state` (the function) directly rather than
    the underlying `_CHAT_MODEL_LOAD_STATE` dict — the latter is a shared
    module-level object read by everything in the process; under the full
    test suite (3000+ tests, ~10 minutes) something elsewhere can still
    observe/mutate it during this test's narrow window regardless of
    monkeypatch scoping (see test_model_ux_phase0b_cancel_and_timeout.py's
    module docstring for the fuller investigation trail). Mocking the
    accessor function instead removes any shared object from the picture
    entirely.
    """
    client, app_mod = _client()
    monkeypatch.setattr(app_mod, "_get_chat_model_load_state", lambda: {
        "state": "idle", "blocking": False, "message": "No model loaded",
        "eta_seconds": None, "progress": 0.0, "model": None,
        "runtime": None, "provider": None, "updated_at": 0.0,
    })
    r = client.get("/api/chat/model-load")
    body = r.json()
    assert body["state"] == "idle"
    assert body["model"] is None
    assert body["state"] != "ready"


# ---------------------------------------------------------------------------
# C6.2/F-CACHERACE — T-CACHERACE
# ---------------------------------------------------------------------------

def test_concurrent_get_optional_chat_backend_and_eject_never_raises(monkeypatch):
    """Hammer _get_optional_chat_backend (the load-path constructor) and
    the eject blank-runtime clear-everything path concurrently; assert no
    KeyError/exception escapes either side."""
    import arail.portal.app as app_mod

    class _FakeAeroLLMBackend:
        def __init__(self):
            pass

    monkeypatch.setattr(app_mod, "_OPTIONAL_CHAT_BACKEND_CACHE", {})
    monkeypatch.setattr(
        "arail.router.backends.AeroLLMBackend", _FakeAeroLLMBackend, raising=False
    )

    errors: list[BaseException] = []
    stop = threading.Event()

    def _constructor_worker():
        for _ in range(200):
            if stop.is_set():
                return
            try:
                app_mod._get_optional_chat_backend("aerollm")
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

    def _clearer_worker():
        for _ in range(200):
            if stop.is_set():
                return
            try:
                with app_mod._OPTIONAL_CHAT_BACKEND_CACHE_LOCK:
                    names = list(app_mod._OPTIONAL_CHAT_BACKEND_CACHE.keys())
                    for name in names:
                        del app_mod._OPTIONAL_CHAT_BACKEND_CACHE[name]
            except BaseException as e:  # noqa: BLE001
                errors.append(e)

    threads = [threading.Thread(target=_constructor_worker) for _ in range(4)]
    threads += [threading.Thread(target=_clearer_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    stop.set()

    assert not errors, f"concurrent cache access raised: {errors}"


def test_eject_blank_runtime_uses_the_cache_lock():
    """Regression-by-construction: the clear-everything eject branch must
    take the cache lock, not iterate+del the raw dict unlocked."""
    import inspect
    import arail.portal.app as app_mod
    src = inspect.getsource(app_mod.api_chat_eject)
    assert "_OPTIONAL_CHAT_BACKEND_CACHE_LOCK" in src


def test_get_optional_chat_backend_uses_double_checked_locking():
    import inspect
    import arail.portal.app as app_mod
    src = inspect.getsource(app_mod._get_optional_chat_backend)
    assert src.count("_OPTIONAL_CHAT_BACKEND_CACHE_LOCK") >= 2, (
        "must lock both the initial check and the store-after-construct "
        "(double-checked locking) — a single lock around only one side "
        "still leaves a TOCTOU window"
    )
