"""Phase 0b (load/unload lifecycle honesty) — regression for a deadlock
discovered while implementing C6.2/F-LOADRACE (step 11).

Sprint: 2026-07-20-model-ux-unification
Architecture: sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md

`scheduler.inference_slot()` is backed by ONE process-wide semaphore
shared across every label — not one semaphore per label
(`arail/portal/scheduler.py`: `_SEM: asyncio.Semaphore | None`, module-
level, `_get_semaphore()` returns the same object regardless of
`label`). `/api/admin/models/load`'s non-streamed branch already runs
inside `async with scheduler.inference_slot("admin-model-load")` and
then calls `_prepare_chat_model_load(...)` — which, after this sprint's
C6.2 fix, ALSO does `async with scheduler.inference_slot("chat-model-
load")` internally. Nesting two acquisitions of the same (non-reentrant)
`asyncio.Semaphore` on the same task self-deadlocks: the outer holder
blocks forever awaiting a permit only its own release could free.

Fixed with a `_caller_holds_inference_slot` kwarg the admin call site
sets to skip the internal (redundant, and now correctness-breaking)
acquisition. This test proves the admin non-streamed load path
completes rather than hanging — a bare deadlock has no natural
assertion, so the proof is a tight `asyncio.wait_for` timeout.
"""

from __future__ import annotations

import asyncio
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def test_prepare_chat_model_load_skips_the_slot_when_caller_already_holds_it(monkeypatch):
    """Direct unit proof: with `_caller_holds_inference_slot=True`, a
    SECOND, independent holder of the semaphore (simulating the admin
    endpoint's own outer `admin-model-load` acquisition) does not block
    this call — because this call never tries to acquire it again."""
    import arail.portal.app as app_mod
    from arail.portal import scheduler

    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_STATE", dict(app_mod._CHAT_MODEL_LOAD_STATE))
    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_INFLIGHT", asyncio.Lock())
    monkeypatch.setattr(scheduler, "_SEM", None)
    monkeypatch.delenv("ARAIL_INFERENCE_CONCURRENCY", raising=False)
    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: object())

    async def _scenario():
        # Simulate the admin endpoint's outer acquisition — capacity is 1
        # by default, so this permanently occupies the sole permit for
        # the duration of the `async with` block below.
        async with scheduler.inference_slot("admin-model-load"):
            result = await app_mod._prepare_chat_model_load(
                model=None, runtime=None, provider=None,
                _caller_holds_inference_slot=True,
            )
        assert result["state"] == "ready"

    # A generous-but-bounded timeout: if the nested-acquire deadlock ever
    # regresses, this fails loud in ~2s instead of hanging the suite.
    asyncio.run(asyncio.wait_for(_scenario(), timeout=2.0))


def test_prepare_chat_model_load_without_the_flag_would_deadlock_against_a_held_slot(monkeypatch):
    """Sanity check on the test above: WITHOUT the flag (the pre-fix
    behavior), the same setup times out — proving the flag is what
    prevents the deadlock, not some other accidental factor."""
    import arail.portal.app as app_mod
    from arail.portal import scheduler

    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_STATE", dict(app_mod._CHAT_MODEL_LOAD_STATE))
    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_INFLIGHT", asyncio.Lock())
    monkeypatch.setattr(scheduler, "_SEM", None)
    monkeypatch.delenv("ARAIL_INFERENCE_CONCURRENCY", raising=False)
    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: object())

    async def _scenario():
        async with scheduler.inference_slot("admin-model-load"):
            await app_mod._prepare_chat_model_load(
                model=None, runtime=None, provider=None,
                _caller_holds_inference_slot=False,
            )

    import pytest
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(asyncio.wait_for(_scenario(), timeout=0.5))


def test_admin_models_load_endpoint_completes_a_non_streamed_load(monkeypatch, tmp_path):
    """End-to-end through the real HTTP handler, not just the helper
    function: /api/admin/models/load's non-streamed branch must complete,
    not hang."""
    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod
    from arail.portal import scheduler

    models_dir = tmp_path / "models"
    models_dir.mkdir()
    model_dir = models_dir / "Qwen3-8B-4bit"
    model_dir.mkdir()
    (model_dir / "model.safetensors").write_bytes(b"\0" * 1024)
    (model_dir / "config.json").write_text("{}")

    monkeypatch.setenv("ARAIL_MODELS_DIR", str(models_dir))
    monkeypatch.setattr(app_mod, "_MODELS_SCAN_CACHE", None)
    monkeypatch.setattr(app_mod, "_MODELS_SCAN_TS", 0.0)
    monkeypatch.setattr(app_mod, "_MODEL_LOAD_LOCK", asyncio.Lock())
    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_STATE", dict(app_mod._CHAT_MODEL_LOAD_STATE))
    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_INFLIGHT", asyncio.Lock())
    monkeypatch.setattr(scheduler, "_SEM", None)
    monkeypatch.setattr(app_mod, "_local_memory_snapshot", lambda: {
        "label": "Test", "gpu_label": None,
        "total_gb": 24.0, "used_gb": 6.0, "free_gb": 18.0,
    })
    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: object())

    client = TestClient(app_mod.app)
    r = client.post(
        "/api/admin/models/load",
        json={"model_id": "Qwen3-8B-4bit"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
