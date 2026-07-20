"""Phase 0b (load/unload lifecycle honesty) — C6.4 honest Cancel
(F-CANCEL) and C6.5 bounded timeout that does not orphan a double load
(F-TIMEOUT-ORPHAN).

Sprint: 2026-07-20-model-ux-unification
Architecture: sprints/2026-07-20-model-ux-unification/ARCHITECTURE.md
Implementation-order step 12.

The load runs in a non-cancellable `asyncio.to_thread` (A4) — nothing
here can truly interrupt it. Resolution is honest absence + honest
endpoint: Cancel never reports a fake "canceled" state, and a timed-out
load's wall-clock guard reports `error` while the inflight lock stays
held until the background thread actually settles — so a second Load
cannot double-reside the model (the OOM vector on the 32 GB target).
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def _scoped_load_state(monkeypatch, app_mod):
    """Swap in a fresh copy of the load-state dict + a fresh inflight lock
    so this test's mutations never leak into other tests in the same
    process (see test_model_ux_phase0b_loadrace.py's identical note)."""
    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_STATE", dict(app_mod._CHAT_MODEL_LOAD_STATE))
    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_INFLIGHT", asyncio.Lock())


# ---------------------------------------------------------------------------
# C6.4/F-CANCEL
# ---------------------------------------------------------------------------

def test_cancel_never_reports_canceled_state_while_a_load_is_in_flight(monkeypatch):
    """POST cancel mid-load: assert the response is NOT `canceled`, the
    thread still completes (model becomes ready), and the state machine
    never had a `canceled` value at any point."""
    import arail.portal.app as app_mod
    from arail.portal import scheduler

    _scoped_load_state(monkeypatch, app_mod)
    monkeypatch.setattr(scheduler, "_SEM", None)

    async def _scenario():
        release = asyncio.Event()

        def _slow_construct(*a, **kw):
            # Runs in a worker thread via asyncio.to_thread — block on an
            # asyncio.Event from a thread by waiting on the underlying
            # threading primitive instead.
            release_evt.wait(timeout=5)
            return object()

        release_evt = threading.Event()
        monkeypatch.setattr(app_mod, "_get_primary_router", _slow_construct)

        load_task = asyncio.create_task(
            app_mod._prepare_chat_model_load(model=None, runtime=None, provider=None)
        )
        # Let the load actually start and reach "loading".
        for _ in range(100):
            if app_mod._get_chat_model_load_state()["state"] == "loading":
                break
            await asyncio.sleep(0.01)
        assert app_mod._get_chat_model_load_state()["state"] == "loading"

        cancel_body = await api_chat_model_load_cancel_direct(app_mod)
        assert cancel_body["state"] != "canceled"
        assert cancel_body["state"] == "loading"
        assert cancel_body["ok"] is False
        assert "cannot be interrupted" in cancel_body["note"]

        # The un-cancellable thread keeps running and completes normally.
        release_evt.set()
        result = await load_task
        assert result["state"] == "ready"

        # At no point did the module-level state hold "canceled".
        assert app_mod._get_chat_model_load_state()["state"] != "canceled"

    asyncio.run(asyncio.wait_for(_scenario(), timeout=5.0))


async def api_chat_model_load_cancel_direct(app_mod):
    """Call the cancel endpoint's handler function directly (bypassing
    TestClient, which would need its own event loop) — same code path."""
    return await app_mod.api_chat_model_load_cancel()


def test_cancel_with_nothing_in_progress_is_an_honest_noop(monkeypatch):
    import arail.portal.app as app_mod
    _scoped_load_state(monkeypatch, app_mod)
    app_mod._CHAT_MODEL_LOAD_STATE.update(state="idle", model=None)

    async def _scenario():
        body = await app_mod.api_chat_model_load_cancel()
        assert body["ok"] is False
        assert body["state"] == "idle"
        assert "no load in progress" in body["note"]

    asyncio.run(_scenario())


def test_cancel_endpoint_never_sets_a_canceled_state():
    """The docstring is allowed to mention "canceled" in prose (explaining
    what the endpoint used to lie about) — what must be absent is any
    actual state mutation to that value. Checked against the function
    body only (docstring stripped) via ast, not a naive source grep."""
    import ast
    import inspect
    import textwrap
    import arail.portal.app as app_mod

    src = textwrap.dedent(inspect.getsource(app_mod.api_chat_model_load_cancel))
    tree = ast.parse(src)
    fn = tree.body[0]
    body_without_docstring = fn.body[1:] if (
        fn.body and isinstance(fn.body[0], ast.Expr)
        and isinstance(fn.body[0].value, ast.Constant)
        and isinstance(fn.body[0].value.value, str)
    ) else fn.body
    body_src = "\n".join(ast.unparse(node) for node in body_without_docstring)

    assert "canceled" not in body_src
    assert "_set_chat_model_load_state" not in body_src, (
        "the cancel endpoint must never mutate _CHAT_MODEL_LOAD_STATE at "
        "all — it can only report, honestly, on what's already true"
    )


# ---------------------------------------------------------------------------
# C6.5/F-TIMEOUT-ORPHAN
# ---------------------------------------------------------------------------

def test_timed_out_load_reports_error_but_keeps_inflight_lock_until_thread_settles(monkeypatch):
    """Simulate a hung load: assert state reaches `error` within the
    configured timeout, a SECOND Load is refused while the first is still
    (invisibly) running, and once the hung thread finally completes the
    lock releases — no double residency."""
    import arail.portal.app as app_mod
    from arail.portal import scheduler

    _scoped_load_state(monkeypatch, app_mod)
    monkeypatch.setattr(scheduler, "_SEM", None)
    monkeypatch.setenv("ARAIL_LOAD_MAX_SEC", "5")  # floored to 5.0 by _load_max_sec

    construct_calls = []

    async def _scenario():
        release_evt = threading.Event()

        def _hung_construct(*a, **kw):
            construct_calls.append(1)
            release_evt.wait(timeout=5)
            return object()

        monkeypatch.setattr(app_mod, "_get_primary_router", _hung_construct)
        # Shrink the wall-clock guard so the test doesn't take 5s to run —
        # monkeypatch the resolved timeout function itself rather than
        # ARAIL_LOAD_MAX_SEC's floor.
        monkeypatch.setattr(app_mod, "_load_max_sec", lambda: 0.1)

        result = await app_mod._prepare_chat_model_load(model=None, runtime=None, provider=None)
        assert result["state"] == "error"
        assert "longer than" in result["message"]

        # A second Load must be refused while the first hung thread is
        # still (invisibly) running — the inflight lock is still held.
        assert app_mod._CHAT_MODEL_LOAD_INFLIGHT.locked()
        refused = await app_mod._prepare_chat_model_load(model=None, runtime=None, provider=None)
        assert refused["message"] == "a load is already in progress"
        assert refused["state"] == "error"  # unchanged — refusal doesn't mutate state

        # Let the hung thread finally finish; the lock must release, and a
        # THIRD load (now that the first has genuinely settled) succeeds.
        release_evt.set()
        for _ in range(200):
            if not app_mod._CHAT_MODEL_LOAD_INFLIGHT.locked():
                break
            await asyncio.sleep(0.01)
        assert not app_mod._CHAT_MODEL_LOAD_INFLIGHT.locked(), (
            "inflight lock never released after the hung thread settled"
        )

        third = await app_mod._prepare_chat_model_load(model=None, runtime=None, provider=None)
        assert third["state"] == "ready"
        # Exactly two real constructions happened (the hung one + the
        # third) — the refused second call never touched the constructor,
        # proving no double residency.
        assert len(construct_calls) == 2

    asyncio.run(asyncio.wait_for(_scenario(), timeout=5.0))
