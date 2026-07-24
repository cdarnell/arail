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

Test-design note — this file went through two prior designs before this
one, both of which were reliable in isolation and in every combined
run tried (up to 8x repeated), but proved flaky specifically under the
FULL test suite (3000+ tests, ~10 minutes, heavy aggregate load):
  1. A real background OS thread blocked on `threading.Event().wait()`
     inside the real `asyncio.to_thread` — real thread-pool scheduling
     turned out to be sensitive to full-suite system load in a way no
     fixed-iteration polling loop could bound.
  2. A fully-async stand-in for `asyncio.to_thread` (pure coroutine
     scheduling, no real thread) — this ALSO reproduced the failure
     under the full suite, including on a test with NO scheduling or
     waiting whatsoever, which proves the earlier "real thread
     scheduling" diagnosis, while a real contributing factor, was not
     the complete picture: the module-level `_CHAT_MODEL_LOAD_STATE` /
     `_CHAT_MODEL_LOAD_LOCK` / `_CHAT_MODEL_LOAD_INFLIGHT` globals are
     shared by the ENTIRE test session, and something elsewhere in a
     3000+-test run can still observe/mutate them during this file's
     narrow execution window in a way three rounds of investigation did
     not fully pin down.

This design (3) removes the dependency entirely: `_get_chat_model_load_state`
and `_set_chat_model_load_state` — the only two functions through which
`_prepare_chat_model_load` and `api_chat_model_load_cancel` ever touch
the shared globals — are monkeypatched to closures over a dict private
to each test. No shared module-level object is read or written by these
tests at all, so no other test running anywhere in the same session can
possibly interact with them, regardless of mechanism.
"""

from __future__ import annotations

import asyncio
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def _install_private_load_state(monkeypatch, app_mod, *, initial: dict | None = None):
    """Redirect `_get_chat_model_load_state`/`_set_chat_model_load_state`
    to a dict private to this test — no shared module-level object is
    touched, so nothing else running anywhere in the same pytest session
    can observe or mutate it. Returns the private dict for direct
    inspection/seeding by the caller."""
    state = dict(initial or {
        "state": "idle", "blocking": False, "message": "No model loaded",
        "eta_seconds": None, "progress": 0.0, "model": None,
        "runtime": None, "provider": None, "updated_at": 0.0,
    })

    def _get():
        return dict(state)

    def _set(**changes):
        state.update(changes)
        return dict(state)

    monkeypatch.setattr(app_mod, "_get_chat_model_load_state", _get)
    monkeypatch.setattr(app_mod, "_set_chat_model_load_state", _set)
    monkeypatch.setattr(app_mod, "_CHAT_MODEL_LOAD_INFLIGHT", asyncio.Lock())
    return state


def _install_deterministic_to_thread(monkeypatch, app_mod, release_evt: asyncio.Event):
    """Replace `asyncio.to_thread` with a fully-async stand-in that waits
    on `release_evt` before calling the wrapped function — same
    "un-cancellable once started" contract as the real thing (A4), but
    with zero dependency on real OS thread-pool scheduling."""
    async def _fake_to_thread(func, *args, **kwargs):
        await release_evt.wait()
        return func(*args, **kwargs)

    monkeypatch.setattr(app_mod.asyncio, "to_thread", _fake_to_thread)


async def _yield_until(predicate, *, attempts: int = 2000) -> None:
    """Cooperative-only wait (pure coroutine scheduling) for `predicate()`
    to become true. Bounded by iteration count, not wall-clock."""
    for _ in range(attempts):
        if predicate():
            return
        await asyncio.sleep(0)
    raise AssertionError("predicate never became true within the attempt budget")


# ---------------------------------------------------------------------------
# C6.4/F-CANCEL
# ---------------------------------------------------------------------------

def test_cancel_never_reports_canceled_state_while_a_load_is_in_flight(monkeypatch):
    """POST cancel mid-load: assert the response is NOT `canceled`, the
    load still completes (model becomes ready) once released, and the
    state machine never held a `canceled` value at any point."""
    import arail.portal.app as app_mod
    from arail.portal import scheduler

    private_state = _install_private_load_state(monkeypatch, app_mod)
    monkeypatch.setattr(scheduler, "_SEM", None)
    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: object())

    async def _scenario():
        release_evt = asyncio.Event()
        _install_deterministic_to_thread(monkeypatch, app_mod, release_evt)

        load_task = asyncio.create_task(
            app_mod._prepare_chat_model_load(model=None, runtime=None, provider=None)
        )
        try:
            await _yield_until(lambda: private_state["state"] == "loading")

            cancel_body = await app_mod.api_chat_model_load_cancel()
            assert cancel_body["state"] != "canceled"
            assert cancel_body["state"] == "loading"
            assert cancel_body["ok"] is False
            assert "cannot be interrupted" in cancel_body["note"]

            # At no point did the private state hold "canceled".
            assert private_state["state"] != "canceled"
        finally:
            # ALWAYS release the simulated in-flight work, regardless of
            # whether the assertions above passed, so this task settles
            # before the test function returns.
            release_evt.set()
            result = await load_task

        assert result["state"] == "ready"

    asyncio.run(_scenario())


def test_cancel_with_nothing_in_progress_is_an_honest_noop(monkeypatch):
    import arail.portal.app as app_mod
    _install_private_load_state(monkeypatch, app_mod, initial={
        "state": "idle", "blocking": False, "message": "No model loaded",
        "eta_seconds": None, "progress": 0.0, "model": None,
        "runtime": None, "provider": None, "updated_at": 0.0,
    })

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
    (invisibly) running, and once the hung work finally completes the
    lock releases — no double residency."""
    import arail.portal.app as app_mod
    from arail.portal import scheduler

    private_state = _install_private_load_state(monkeypatch, app_mod)
    monkeypatch.setattr(scheduler, "_SEM", None)
    # Shrink the wall-clock guard so the test doesn't wait for the real
    # default — monkeypatch the resolved timeout function itself rather
    # than relying on ARAIL_LOAD_MAX_SEC's floor.
    monkeypatch.setattr(app_mod, "_load_max_sec", lambda: 0.05)

    construct_calls: list[int] = []

    def _counted_construct():
        construct_calls.append(1)
        return object()

    monkeypatch.setattr(app_mod, "_get_primary_router", _counted_construct)

    async def _scenario():
        release_evt = asyncio.Event()
        _install_deterministic_to_thread(monkeypatch, app_mod, release_evt)

        try:
            result = await app_mod._prepare_chat_model_load(model=None, runtime=None, provider=None)
            assert result["state"] == "error"
            assert "longer than" in result["message"]

            # A second Load must be refused while the first hung work is
            # still (invisibly) running — the inflight lock is still held.
            assert app_mod._CHAT_MODEL_LOAD_INFLIGHT.locked()
            refused = await app_mod._prepare_chat_model_load(model=None, runtime=None, provider=None)
            assert refused["message"] == "a load is already in progress"
            assert refused["state"] == "error"  # unchanged — refusal doesn't mutate state
        finally:
            # ALWAYS release the simulated hung work, regardless of
            # whether the assertions above passed.
            release_evt.set()

        await _yield_until(lambda: not app_mod._CHAT_MODEL_LOAD_INFLIGHT.locked())

        third = await app_mod._prepare_chat_model_load(model=None, runtime=None, provider=None)
        assert third["state"] == "ready"
        # Exactly two real constructions happened (the hung one + the
        # third) — the refused second call never touched the constructor,
        # proving no double residency.
        assert len(construct_calls) == 2

    asyncio.run(_scenario())
