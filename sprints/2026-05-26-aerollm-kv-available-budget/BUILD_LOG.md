# Build log: aerollm-kv-available-budget

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at commit 22b9688 (base)
**Branch:** `qukaizen/arail-kv-available-budget`
**Started:** 2026-05-26

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/router/backends.py` | Add four constants + `_resolve_kv_budget()` pure function above AeroLLMBackend | — | 3ac1c06 |
| 2 | `tests/router/__init__.py`, `tests/router/test_aerollm_kv_budget.py` | Unit tests 1–11 + regression test 14 | test-first | 20515f9 |
| 3 | `src/arail/router/backends.py` | Add `_emit_budget_activity()` method on AeroLLMBackend | — | e30caad |
| 4 | `src/arail/router/backends.py` | Replace `kv_budget_pct_raw` block with resolver + emit | — | c153dba |
| 5 | `tests/router/test_aerollm_backend_budget_emit.py` | Integration tests 12–13 | — | e73e0da |

## Execution

### Step 1 — constants + resolver (commit 3ac1c06)

Added `_AEROLLM_KV_MIN_FLOOR_BYTES`, `_AEROLLM_KV_SAFETY_HEADROOM_BYTES`,
`_AEROLLM_KV_AVAILABLE_FRACTION`, `_AEROLLM_KV_PCT_DEFAULT`, and
`_resolve_kv_budget()` in the new "AeroLLM KV-budget resolution" section above
the class. All docstring rationale verbatim from ARCHITECTURE.md. No new
top-level imports (`psutil` inside try/except inside the function).
`python3 -c "import arail.router.backends"` clean.

### Step 2 — unit tests (commit 20515f9)

Created `tests/router/__init__.py` and `tests/router/test_aerollm_kv_budget.py`.
All 12 tests (tests 1–11 + test 14) pass immediately. Uses `monkeypatch` for env
and `unittest.mock.patch` for `psutil.virtual_memory`. No AeroLLMBackend instantiation.

### Step 3 — emit method (commit e30caad)

`_emit_budget_activity()` added after `_init_runtime`. Lazy-imports `arail.activity_log`.
Swallows both `ImportError` and any exception from `emit()`. Level: `"warn"` for
`source in {"floor", "unavailable"}`, `"info"` otherwise. Category: `"system"`.

### Step 4 — backend integration (commit c153dba)

Replaced the 18-line `kv_budget_pct_raw` block with 5 lines:
resolver call → conditional kwarg set → emit call. The resolver now runs
unconditionally (not gated on env var being set), so the default 0.60 path
also caps by available RAM. `kv_memory_budget` guaranteed `int` (resolver
always calls `int(raw_budget)` before returning).

### Step 5 — integration tests (commit e73e0da)

`tests/router/test_aerollm_backend_budget_emit.py` — 3 tests:

- Test 12: singleton emit fires once only.
- Test 13a: kwarg present and is int.
- Test 13b: kwarg absent when resolver returns None.

Uses fake aerollm_api via `sys.modules`; `_clear_shared` autouse fixture
resets singleton between tests.

## Test results

```text
tests/router/test_aerollm_kv_budget.py           12 passed
tests/router/test_aerollm_backend_budget_emit.py  3 passed
tests/router/ total:                             15 passed in 0.02s

tests/test_aerollm_tier_resolution.py            14 passed (regression: 14/14)

scripts/setup.sh: bash -n passes
python3 -c "import arail.router.backends": clean (no circular imports)
```

## Deviations from ARCHITECTURE.md

None. All behavior matrix rows implemented. All 14 tests listed in ARCHITECTURE.md
implemented (tests 1–11, 12, 13 as 13a+13b, 14). Architect split test 13 into
two assertions (kwarg present / kwarg absent) for clarity; both cover the spec intent.

## Items for reviewer attention

1. **Singleton gate** — resolver + emit are inside `__init__` after the `_initialized`
   guard. Grep `_resolve_kv_budget` in backends.py: exactly one call site.
2. **`int()` enforcement** — `budget_bytes` in resolver is always `int(raw_budget)` or
   `_AEROLLM_KV_MIN_FLOOR_BYTES` (already int). Test 11 asserts type explicitly.
3. **No new top-level imports** — `psutil` is inside try/except inside the function;
   `activity_log` is inside try/except inside `_emit_budget_activity`. Verified by
   import smoke test.
4. **`.env` line ~184 not modified** — `AEROLLM_KV_BUDGET_PCT` default of `0.60`
   is now the `_AEROLLM_KV_PCT_DEFAULT` constant, matching legacy value.
5. **Smoke test** — Builder does NOT run the portal (QA's domain per sprint
   instructions). Dev-box budget number to be filled in by QA from a live run.

## Architect feedback required

None.

## Final state

- 5 implementation commits (6 total including BUILD_LOG.md skeleton)
- 15 new tests: 12 unit + 3 integration; all passing
- Regression: `test_aerollm_tier_resolution.py` 14/14
- Files modified: `src/arail/router/backends.py` (+160 lines net after replacement)
- Files added: `tests/router/__init__.py`, `tests/router/test_aerollm_kv_budget.py`,
  `tests/router/test_aerollm_backend_budget_emit.py`
- No commented-out code; no TODO comments added (existing runtime-profile TODO preserved as-is)

---

## Revision pass (post-BLOCK)

**Date:** 2026-05-26
**Reviewer verdict:** BLOCK (Findings A + B in REVIEW.md)
**Commits in this pass:**

- `9a1c95b` — fix(aerollm): correct import path and emit() signature in _emit_budget_activity
- `e630c5d` — test(aerollm): add positive-path tests for _emit_budget_activity body (tests 14a+14b)

### What was fixed

**Finding A (BLOCK) — import path:**
Changed `from arail import activity_log` → `from arail.activity import activity_log` inside `_emit_budget_activity`. The former raises `ImportError` (swallowed silently by bare except); the latter is the correct path used by `pkb_index.py` and `wiki.py`.

**Finding B (BLOCK) — emit() call signature:**
Changed `activity_log.emit(level=level, category="system", message=reasoning["reason"])` → `activity_log.emit("aerollm", reasoning["reason"], level=level)`. The real signature is `emit(source, message, level="info", data=None)`; there is no `category` parameter. The `"aerollm"` source string matches the `"wiki"` / `"pkb"` convention.

**Finding D (recommended) — narrow bare except:**
Added `import logging` and `_log = logging.getLogger(__name__)` at module level (first use of logging in backends.py). Changed `except Exception: pass` to `except Exception as e: _log.warning("activity_log emission failed: %s", e)`.

### Import + signature confirmation

Final call form: `activity_log.emit("aerollm", reasoning["reason"], level=level)`
Sanity check: `python3 -c "from arail.activity import activity_log; print(activity_log)"` → `<arail.activity.ActivityLog object at 0x...>`

### New tests (14a + 14b)

Both tests in `tests/router/test_aerollm_backend_budget_emit.py` let `_emit_budget_activity` run for real (not patched out) and patch `arail.activity.activity_log.emit` with a `MagicMock`.

- **14a** — `source="default"`: asserts `mock_emit.assert_called_once()`, `args[0] == "aerollm"`, `"KV budget resolved" in args[1]`, `level="info"`.
- **14b** — `source="floor"` (via patched `_resolve_kv_budget`): asserts `level="warn"`.

### Verify-then-fix loop evidence

Ran a scratch simulation with the pre-fix broken import (`from arail import activity_log`). The `ImportError` is swallowed; `mock_emit` is never called. `assert_called_once()` would have raised `AssertionError`. Output:

```text
CONFIRMED: broken import → mock_emit.assert_called_once() would FAIL (ImportError swallowed)
```

The test is a meaningful guard against Findings A and B recurring.

### Test suite after revision pass

```text
tests/router/test_aerollm_kv_budget.py              12 passed
tests/router/test_aerollm_backend_budget_emit.py     5 passed  (3 original + 2 new)
tests/router/ total:                                17 passed in 0.03s

tests/test_aerollm_tier_resolution.py              14 passed (regression: 14/14)

python3 -c "import arail.router.backends": clean (no circular imports)
```

### What the reviewer should re-verify on a second pass

1. `_emit_budget_activity` in `backends.py` now does `from arail.activity import activity_log` (not `from arail import activity_log`) and calls `activity_log.emit("aerollm", reasoning["reason"], level=level)`.
2. Tests 14a and 14b are NOT patching `_emit_budget_activity` — they let the body run.
3. The `_log.warning(...)` fallback in the narrow except is wired to `_log = logging.getLogger(__name__)` at module level.
4. No other files were touched in this revision pass (scope check: only `src/arail/router/backends.py` and `tests/router/test_aerollm_backend_budget_emit.py`).
