# Build log: aerollm-kv-available-budget

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at commit 22b9688 (base)
**Branch:** `qukaizen/arail-kv-available-budget`
**Started:** 2026-05-26

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/router/backends.py` | Add four module-level constants + `_resolve_kv_budget()` pure function above AeroLLMBackend class | — | TBD |
| 2 | `tests/router/__init__.py`, `tests/router/test_aerollm_kv_budget.py` | Unit tests 1–11 + regression test 14 | test-first | TBD |
| 3 | `src/arail/router/backends.py` | Add `_emit_budget_activity()` method on AeroLLMBackend | — | TBD |
| 4 | `src/arail/router/backends.py` | Replace `kv_budget_pct_raw` block with resolver + emit | — | TBD |
| 5 | `tests/router/test_aerollm_backend_budget_emit.py` | Integration tests 12–13 | — | TBD |

## Execution

### Step 1 — constants + resolver
Commit: TBD

### Step 2 — unit tests
Commit: TBD

### Step 3 — emit method
Commit: TBD

### Step 4 — backend integration (replace kv_budget_pct_raw block)
Commit: TBD

### Step 5 — integration tests 12–13
Commit: TBD

## Architect feedback required

None.

## Final state

TBD after all steps complete.
