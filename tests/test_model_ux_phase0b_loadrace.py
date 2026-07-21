"""Phase 0b (load/unload lifecycle honesty) — C6.2/F-LOADRACE: a chat
model load takes the shared inference slot, serializing against the
aeroLLM preload loop / an admin model load at default concurrency (A8).

Sprint: 2026-07-20-model-ux-unification
Architecture: sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md
Implementation-order step 11.
"""

from __future__ import annotations

import asyncio
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def test_chat_model_load_serializes_against_a_concurrent_heavy_slot_holder(monkeypatch):
    """With another caller already holding the (default capacity=1) heavy
    inference slot, a chat model load must wait for it rather than run
    concurrently — that's the whole point of F-LOADRACE."""
    import arail.portal.app as app_mod
    from arail.portal import scheduler

    monkeypatch.delenv("ARAIL_INFERENCE_CONCURRENCY", raising=False)
    # Reset the lazily-initialized semaphore so the test's env is honored
    # and previous tests' acquire/release history can't leak in.
    monkeypatch.setattr(scheduler, "_SEM", None)
    # This test performs a REAL _prepare_chat_model_load call, which
    # mutates the shared module-level _CHAT_MODEL_LOAD_STATE dict in
    # place. Swap in a scoped copy so monkeypatch's teardown restores the
    # original dict afterward — otherwise this test would leak a "ready"
    # state into every test that runs after it in the same session
    # (discovered while writing this test: it broke test_chat_ui.py's
    # cold-state assertion).
    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_STATE", dict(app_mod._CHAT_MODEL_LOAD_STATE))

    async def _scenario():
        order: list[str] = []
        release_preload = asyncio.Event()

        async def _fake_preload_holder():
            async with scheduler.inference_slot("aerollm-preload"):
                order.append("preload-acquired")
                await release_preload.wait()
                order.append("preload-released")

        def _fake_construct(*a, **kw):
            # _get_primary_router is called via asyncio.to_thread (a sync
            # callable), not awaited directly — must be a plain function.
            order.append("chat-load-ran")
            return object()

        monkeypatch.setattr(app_mod, "_get_primary_router", _fake_construct)

        preload_task = asyncio.create_task(_fake_preload_holder())
        for _ in range(50):
            if "preload-acquired" in order:
                break
            await asyncio.sleep(0.01)
        assert "preload-acquired" in order

        load_task = asyncio.create_task(
            app_mod._prepare_chat_model_load(model=None, runtime=None, provider=None)
        )
        # The chat load must NOT proceed while the preload slot is held.
        await asyncio.sleep(0.05)
        assert "chat-load-ran" not in order, (
            "chat model load ran concurrently with the preload-slot holder — "
            "F-LOADRACE not closed"
        )

        release_preload.set()
        await preload_task
        result = await load_task

        assert order == ["preload-acquired", "preload-released", "chat-load-ran"]
        assert result["state"] == "ready"

    asyncio.run(asyncio.wait_for(_scenario(), timeout=5.0))


def test_prepare_chat_model_load_source_takes_the_inference_slot():
    import inspect
    import arail.portal.app as app_mod
    src = inspect.getsource(app_mod._prepare_chat_model_load)
    assert 'scheduler.inference_slot("chat-model-load")' in src
