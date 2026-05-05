# Build log: opencode in Workbench

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at commit 50ce5ad
**Started:** 2026-05-04

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `BUILD_LOG.md` | Skeleton — this file | — | — |
| 2 | `src/arail/portal/services/__init__.py` | New package init | — | — |
| 2 | `src/arail/portal/services/opencode.py` | New service module: is_installed, is_running, start, stop, restart, _wait_ready, _compute_source_env, install_hint, module-level Lock | unit tests first | — |
| 3 | `tests/portal/__init__.py` | New test package init | — | — |
| 3 | `tests/portal/test_opencode_service.py` | Unit tests for opencode service module | — | — |
| 4 | `src/arail/portal/app.py` | Add _require_workbench helper + 3 routes: GET /opencode, POST /api/opencode/start, POST /api/opencode/stop | integration tests | — |
| 4 | `src/arail/portal/app.py` | Extend /api/notebooks/status with 5th opencode entry | integration tests | — |
| 4 | `src/arail/portal/app.py` | Extend /api/system/health with opencode in optional_services | integration tests | — |
| 4 | `src/arail/portal/app.py` | providers_active hook — fire-and-forget opencode restart | lifecycle tests | — |
| 5 | `src/arail/portal/templates/opencode.html` | New 3-state template (not-installed / installed-not-running / running+iframe) | integration tests | — |
| 6 | `src/arail/portal/templates/notebooks.html` | Add 5th opencode card; rename heading to Workbench | regression tests | — |
| 6 | `src/arail/portal/templates/_nav.html` | Rename Notebooks link text to Workbench | regression tests | — |
| 7 | `tests/portal/test_opencode_routes.py` | Integration tests for routes + gate + iframe URL | — | — |
| 8 | `tests/portal/test_opencode_lifecycle.py` | Lifecycle tests (port busy, restart, lock, log rotation, wait_ready) | — | — |

## Execution

### Step 1 — BUILD_LOG.md skeleton
Committed.

## Architect feedback required
<none yet>

## Final state
TBD
