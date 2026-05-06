# Learning: allow_egress context manager and asyncio.create_task scope

**Date:** 2026-05-05
**Sprint:** airgap-honest-mode
**Context:** arail.egress.allow_egress() uses contextvars.ContextVar

## The subtlety

`contextvars.ContextVar` is scoped per-thread (in threading) and per-task (in asyncio). When you do:

```python
with allow_egress("test endpoint"):
    task = asyncio.create_task(some_coroutine())
    # <-- with-block exits here
await task  # task still sees the bypass
```

`asyncio.create_task()` copies the current `contextvars.Context` snapshot into the new task. This means the task inherits the bypass even after the with-block's `finally` has reset the var in the spawning frame.

## Why this is acceptable for v1

The only caller pattern in v1 is "save/test/list provider token" which awaits inline:

```python
with allow_egress("test the openrouter endpoint"):
    r = await some_awaitable()  # does NOT spawn a task
```

No `create_task` inside the with-block in v1. The risk is theoretical.

## What to watch for

If a future contributor writes:

```python
with allow_egress("reason"):
    asyncio.create_task(fetch_stuff())  # <-- DANGER
# with-block exits; task still has the bypass
```

The bypass will persist until the task completes or the event loop ends. This silently widens the blast radius beyond the intended scope.

## Mitigation for future async use

If you need to spawn a task inside an `allow_egress` block that should NOT carry the bypass:

```python
with allow_egress("reason"):
    # Reset the contextvar before spawning the task
    ctx = contextvars.copy_context()
    ctx.run(_allow_egress_var.set, None)
    task = asyncio.create_task(fetch_stuff(), context=ctx)
```

Or use `asyncio.run_coroutine_threadsafe` with an explicit context.

## Reference

- Python docs: https://docs.python.org/3/library/contextvars.html
- asyncio task context: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
- Sprint ARCHITECTURE.md §7 "asyncio subtlety" block
