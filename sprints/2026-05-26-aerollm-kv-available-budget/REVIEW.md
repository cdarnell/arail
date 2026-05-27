# Review: aerollm-kv-available-budget

**Date:** 2026-05-26
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at ea85586
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Branch:** `qukaizen/arail-kv-available-budget` (commits 6213105..ea85586 atop 22b9688)

## Verdict: BLOCK

The math, resolver, gating, and test coverage are all correct and well-organized. However, `_emit_budget_activity()` is silently broken in two compounding ways: the import path it uses does not exist, and even if it did the `emit()` call signature is wrong. Because both errors are swallowed by bare `except`, every test still passes and the bug is invisible — but in production the activity-log line that the operator is supposed to see (the entire user-facing payoff of this sprint beyond the budget cap itself) will never fire. The two-line fix is mechanical, but it must land before /qa, because /qa is being asked to verify the activity feed shows the budget line on a live dev box — and right now it cannot.

## Risk checklist (from ARCHITECTURE.md §"Risks the reviewer will look for")

1. **Singleton gating** — ✓ confirmed. `backends.py:1482-1483` is the `if getattr(self, "_initialized", False): return` guard; the `_resolve_kv_budget()` call lives at `backends.py:1554` and `self._emit_budget_activity(reasoning)` at `backends.py:1557`, both *after* the guard. Integration test `test_budget_emit_called_once` asserts `mock_emit.assert_called_once_with(known_result)` across two `AeroLLMBackend()` calls — passing.
2. **Floor honored above env** — ✓ confirmed. `backends.py:_resolve_kv_budget` lines around the `raw_budget < _AEROLLM_KV_MIN_FLOOR_BYTES` check apply the floor *after* `min(ceil_total, ceil_available)`, so env-as-ceiling never bypasses the floor. Test 4 (`test_floor_applied_when_box_starved`) exercises this with available=3 GiB.
3. **`.available` not `.total`** — ✓ confirmed. Resolver reads `vm.available` for `ceil_available = available * _AEROLLM_KV_AVAILABLE_FRACTION - _AEROLLM_KV_SAFETY_HEADROOM_BYTES`. No reference to `swap_memory()` anywhere.
4. **No circular import** — ✓ confirmed for backends.py itself: `python3 -c "import arail.router.backends"` runs clean (BUILD_LOG step 1). But see Finding A below — the *runtime* lazy import inside `_emit_budget_activity` is broken for a different reason (wrong path), not circular-import related.
5. **Returned int, not float** — ✓ confirmed. `backends.py` resolver returns `int(raw_budget)` in the formula branch and `_AEROLLM_KV_MIN_FLOOR_BYTES` (int constant) in the floor branch. Test 11 asserts `isinstance(result["budget_bytes"], int)`. The `None` branches are also valid (caller skips `kv_memory_budget` entirely — see Finding D).
6. **Default path unchanged for happy 16 GB case** — ✓ confirmed. Test 14 asserts `total=16, available=14 → 9.6 GiB`, the exact legacy value.
7. **Activity log emission level** — ⚠ partial. The level-selection logic at `backends.py` in `_emit_budget_activity` is correct (`"warn" if source in {"floor", "unavailable"} else "info"`). However the call itself never reaches the activity bus — see Finding A. So the level is correct in code but unobservable in practice.
8. **No new env var invented** — ✓ confirmed. Only `AEROLLM_KV_BUDGET_PCT` is read by the resolver; the four constants are module-private and not env-overridable.
9. **`.env` line 184 area not modified** — ✓ confirmed. `git diff 22b9688..HEAD -- .env` is empty; `_AEROLLM_KV_PCT_DEFAULT = 0.60` matches the shipped default.
10. **No new top-level imports added to backends.py** — ✓ confirmed. `git diff 22b9688..HEAD -- src/arail/router/backends.py | grep -E "^\+import |^\+from "` returns empty. `psutil` lives inside the try/except inside `_resolve_kv_budget`; `arail.activity_log` (sic) is lazy inside `_emit_budget_activity`.

## Additional findings

### Finding A — BLOCK: `_emit_budget_activity` import path does not exist

`src/arail/router/backends.py` `_emit_budget_activity` does:

```python
from arail import activity_log  # noqa: PLC0415 — intentionally lazy
```

But `activity_log` is not a submodule of `arail`; it is a module-level singleton defined in `src/arail/activity.py:101` (`activity_log = ActivityLog()`). Reproduced:

```
$ python3 -c "from arail import activity_log; print(activity_log)"
ImportError: cannot import name 'activity_log' from 'arail' (.../src/arail/__init__.py)
```

Every other consumer in the repo uses the correct path: `pkb_index.py:239,323,381` and `wiki.py:665,689` all do `from arail.activity import activity_log`. The integration test does not catch this because it patches `_emit_budget_activity` itself rather than letting it run, so the broken import never executes.

**Fix:** change one line in `backends.py` `_emit_budget_activity` from `from arail import activity_log` to `from arail.activity import activity_log`.

### Finding B — BLOCK: `activity_log.emit()` call signature is wrong

Real signature (`src/arail/activity.py:50-51`):

```python
def emit(self, source: str, message: str,
         level: str = "info", data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
```

Builder's call:

```python
activity_log.emit(
    level=level,
    category="system",
    message=reasoning["reason"],
)
```

There is no `category` parameter; the correct first positional is `source`. Even if Finding A is fixed, this `emit(...)` raises `TypeError: emit() got an unexpected keyword argument 'category'` — which the bare `except Exception` swallows. Net: still no log line.

**Fix:** call as `activity_log.emit("aerollm", reasoning["reason"], level=level)` (matching the `"wiki"` / `"pkb"` source-string convention used elsewhere). The sprint spec uses the word "category" because that is the architect's mental model, but the codebase calls it `source`; the architect was sloppy here and the builder followed the spec verbatim. Adjust ARCHITECTURE.md risk-item #7 to reflect actual API.

### Finding C — WEAK: integration tests stub out `_emit_budget_activity`, hiding Findings A+B

`tests/router/test_aerollm_backend_budget_emit.py:98,128,156` all `patch.object(AeroLLMBackend, "_emit_budget_activity")`. This is correct for asserting *call count* and *kwarg wiring*, but it means the body of the method is never executed under test. Recommend an additional test that:

- Lets `_emit_budget_activity` run for real,
- Patches `arail.activity.activity_log.emit` with a `MagicMock`,
- Asserts that mock was called once with `source="aerollm"`, `level="info"`, and a message containing "KV budget resolved".

Without this test, Findings A+B would have shipped silently.

### Finding D — INFO: `kv_memory_budget` correctly absent (not None/0) when resolver returns None

`backends.py:1555-1556`:

```python
if reasoning["budget_bytes"] is not None:
    rt_kwargs["kv_memory_budget"] = reasoning["budget_bytes"]
```

Matches the spec — aerollm distinguishes "kwarg absent → auto-detect" from "kwarg=0 → no KV pool". Test 13b (`test_kv_memory_budget_kwarg_absent_when_resolver_returns_none`) asserts the kwarg is absent from the Runtime kwargs in the None path. Confirmed via `git show e73e0da`.

### Finding E — INFO: env-var whitespace handled

Resolver does `pct_raw = os.getenv("AEROLLM_KV_BUDGET_PCT", "").strip()`. `"  0.5  "` and `"0.5\n"` parse correctly. Not explicitly tested but the `.strip()` is present and `float()` would tolerate trailing newline anyway.

### Finding F — INFO: previous comment block intent preserved

The old `kv_budget_pct_raw` block (8-line comment + 18-line logic) is replaced with a new 6-line comment that explains the new semantics (cap by available, ceiling-against-total). The architectural rationale that survived (`AEROLLM_KV_BUDGET_PCT` semantics, why we override aerollm's own 80% default) is repeated in the new comment with the new math. No useful context was lost.

### Finding G — INFO: constants are module-private and stay that way

`grep -rn "_AEROLLM_KV_" src tests` returns hits only inside `backends.py` and `test_aerollm_kv_budget.py` (the test imports them explicitly for arithmetic). No leak into other modules.

### Finding H — INFO: psutil import-error path tested via `sys.modules`, not real `pip uninstall`

Test 8 (`test_psutil_import_error`) sets `sys.modules["psutil"] = None`, which causes `import psutil` inside the resolver to raise `ImportError: import of psutil halted; None in sys.modules`. This covers the resolver's try/except branch correctly. Test 9 covers the call-time failure. The sprint spec called for both; both exist.

### Finding I — INFO: log message is one-line human-readable

Sample from resolver: `"KV budget resolved to 15.50 GiB (source=default, total=36.0 GiB, available=20.0 GiB)"`. Not a raw dict dump; contains GiB number and source. Good.

### Finding J — INFO: `Optional` and `Any` already imported

`backends.py:17`: `from typing import Any, Iterator, Optional`. The resolver's `Optional[str]` and `dict[str, Any]` annotations do not require new imports.

## Test coverage assessment

15 new tests pass (12 unit + 3 integration). Coverage on `_resolve_kv_budget` is comprehensive — every branch in the behavior matrix has a test. Coverage on `_emit_budget_activity` is **zero in practice** because both integration tests patch it out; this is the gap that allowed Findings A+B to ship. Existing regression `test_aerollm_tier_resolution.py` (14 tests) still passes per BUILD_LOG.

## Performance assessment

N/A. Resolver runs once per process per model at backend first-init, computing trivial arithmetic on two psutil reads. No hot-path cost.

## Tech debt delta

Matches ARCHITECTURE.md prediction (net slightly negative). No unanticipated debt added by the builder *except* the masked-by-bare-except issue: the `except Exception: pass` pattern in `_emit_budget_activity` is what hid Findings A and B from every test run. Recommend, after fixing A+B, narrowing the bare except to `except Exception as e: _log.warning(...)` so future signature drift is at least visible in uvicorn logs.

## Required actions before merge (BLOCK)

1. **Fix the import path** in `src/arail/router/backends.py` `_emit_budget_activity`: replace `from arail import activity_log` with `from arail.activity import activity_log`.
2. **Fix the `emit()` call signature**: replace the broken `emit(level=..., category=..., message=...)` call with `activity_log.emit("aerollm", reasoning["reason"], level=level)`.
3. **Add a positive-path test** for `_emit_budget_activity` that lets the method body execute and asserts on a patched `arail.activity.activity_log.emit`. Without this, Findings A+B can recur.
4. **(Optional but recommended)** narrow the bare-except inside `_emit_budget_activity` to log at warning level so silent signature/import drift is at least visible in uvicorn output.

After 1+2+3 land, no re-review is needed for those specific changes — the new test will be the gate. /qa can then proceed.

## Recommended QA focus (after the BLOCK items are addressed)

- **Activity-feed live check (the headline acceptance test):** start the portal, send one chat turn through aerollm/maximus, confirm the activity feed surfaces a `source="aerollm", level="info"` line with the resolved GiB number. Without this, /qa cannot certify the user-visible behavior the sprint promised.
- **Live floor-case stress:** intentionally inflate memory pressure (open ~20 Chrome tabs + a `stress -m` worker) on the 36 GB dev box, then construct the backend, and verify the activity feed shows `level="warn"` with `source=floor` and `kv_memory_budget` near 2 GiB. The floor-warn path is the loudest signal operators get; only unit tests cover it today.
- **psutil-uninstalled smoke:** the sprint spec explicitly asked /qa to `pip uninstall psutil` in a scratch venv and verify the portal still boots, warn fires, aerollm auto-detects. The unit test mocks this; the live test exercises the lazy-import-failure path.
- **AEROLLM_KV_BUDGET_PCT=0 in `.env`:** confirm the activity log shows the "ignored invalid env" note and the resolver falls back to 0.60.
- **Regression: 16 GB Mac happy path:** confirm `kv_memory_budget` resolves to ~9.6 GiB, identical to the pre-sprint value.

## Files reviewed

- `/Users/netsushi/ProJects/arail/sprints/2026-05-26-aerollm-kv-available-budget/SPRINT.md`
- `/Users/netsushi/ProJects/arail/sprints/2026-05-26-aerollm-kv-available-budget/ARCHITECTURE.md`
- `/Users/netsushi/ProJects/arail/sprints/2026-05-26-aerollm-kv-available-budget/BUILD_LOG.md`
- `/Users/netsushi/ProJects/arail/src/arail/router/backends.py` (final state, lines 1273–1620 region)
- `/Users/netsushi/ProJects/arail/src/arail/activity.py` (to verify the emit signature and module path)
- `/Users/netsushi/ProJects/arail/tests/router/test_aerollm_kv_budget.py`
- `/Users/netsushi/ProJects/arail/tests/router/test_aerollm_backend_budget_emit.py`
- Commits 3ac1c06, e30caad, c153dba (via `git show`); branch log 22b9688..HEAD via `git log --oneline`
- `src/arail/pkb_index.py` and `src/arail/wiki.py` (sampled, to confirm the canonical `from arail.activity import activity_log` import path)
