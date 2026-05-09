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

---

# Learning: canonical-vs-PKB agent de-duplication (Buddy + SRE)

**Date:** 2026-05-05 (updated same sprint)
**Sprint:** airgap-honest-mode

## The pattern

ARAIL ships two copies of each built-in agent body: the canonical package
module (`src/arail/agents/_builtin_*.py`, tracked in git) and the PKB
runtime copy (`lab/pkb/agents/<id>/<id>.py`, gitignored). `builtin_seed.py`
originally seeded the PKB copy via `shutil.copy(builtin, pkb_py)`.

The drift hazard: edits to the gitignored PKB copy survive on one workstation
but evaporate on `./arailctl reset pkb` or a clean install, when `builtin_seed.py`
re-copies the canonical over the PKB file.

## The fix (applied to both Buddy and SRE in this sprint)

Replace `shutil.copy` with a shim-template write. The PKB file becomes a
thin re-export:

```python
from arail.agents._builtin_sre import (  # noqa: F401
    sre, SREAgent, ...
)
```

The loader imports the PKB file by path; the re-export means `getattr(module,
"sre")` returns the same singleton as the canonical. One edit to the canonical
file lands everywhere. The user can still fork by replacing the shim with a
full body — the loader prefers the PKB copy, and the shim sentinel check
(first non-blank line) skips the rewrite if the user has already forked.

## What to watch for when adding a new built-in agent

1. Write the body in `src/arail/agents/_builtin_<id>.py` (canonical).
2. In `builtin_seed.py`, define `_<ID>_PKB_SHIM` + `_<ID>_PKB_SHIM_SENTINEL`.
3. `ensure_<id>_folder()` writes the shim, not `shutil.copy()`.
4. The shim re-export list must include every name the loader and any
   test file reaches for — grep for `mod.<name>` in test files that import
   by `spec_from_file_location` to find the full surface.
5. Add `tests/test_builtin_seed_<id>_shim.py` with identity assertions.

## Why SRE's shim surface is wider than Buddy's

`tests/test_sre_new_watchers.py` imports the PKB `sre.py` by file path and
calls private helpers (`_watch_dependency_vulnerabilities`, `_sre_lab_mode`,
etc.) directly on the module. The SRE shim must re-export all 16 names;
Buddy's shim re-exports only 8 public names because `test_buddy_suggesters.py`
imports the canonical by package path, not by file.
