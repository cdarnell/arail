# Build log: opencode in Workbench

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at commit 50ce5ad
**Started:** 2026-05-04
**Finished:** 2026-05-04

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `BUILD_LOG.md` | Skeleton — this file | — | c7eaf48 |
| 2 | `src/arail/portal/services/__init__.py` | New package init | — | 8816ade |
| 2 | `src/arail/portal/services/opencode.py` | New service module: is_installed, is_running, start, stop, restart, _wait_ready, _compute_source_env, install_hint, module-level Lock | unit tests first | 8816ade |
| 3 | `tests/portal/__init__.py` | New test package init | — | 8816ade |
| 3 | `tests/portal/test_opencode_service.py` | Unit tests for opencode service module (16 tests) | — | 8816ade |
| 4 | `src/arail/portal/app.py` | _require_workbench helper + 3 routes: GET /opencode, POST /api/opencode/start, POST /api/opencode/stop | integration tests | b60917b |
| 4 | `src/arail/portal/app.py` | Extend /api/notebooks/status with 5th opencode entry | integration tests | b60917b |
| 4 | `src/arail/portal/app.py` | Extend /api/system/health with opencode in optional_services | integration tests | b60917b |
| 4 | `src/arail/portal/app.py` | providers_active hook — fire-and-forget opencode restart | lifecycle tests | b60917b |
| 5 | `src/arail/portal/templates/opencode.html` | New 3-state template (not-installed / installed-not-running / running+iframe) | integration tests | 9ed8445 |
| 6 | `src/arail/portal/templates/notebooks.html` | Add 5th opencode card; rename heading to Workbench | regression tests | 9ed8445 |
| 6 | `src/arail/portal/templates/_nav.html` | Rename Notebooks link text to Workbench | regression tests | 9ed8445 |
| 7 | `tests/portal/test_opencode_routes.py` | Integration tests for routes + gate + iframe URL (17 tests) | — | 048b897 |
| 8 | `tests/portal/test_opencode_lifecycle.py` | Lifecycle tests (port busy, restart, lock, log rotation, wait_ready) (8 tests) | — | 048b897 |

## Execution

### Step 1 — BUILD_LOG.md skeleton
Committed c7eaf48. No delta from plan.

### Step 2 — Service module + unit tests
Committed 8816ade.

Created `src/arail/portal/services/` package (new; no pre-existing services directory).

Key implementation notes:
- `_compute_source_env()` uses lazy import of `_load_active_provider` / `_provider_token` from `app.py` to avoid circular import at module load time.
- `restart()` acquires `_lock` once and calls `_stop_unlocked()` + `_start_inner()` (private variants that assume lock held) to prevent double-locking deadlock.
- `_wait_ready()` uses `requests` (already in pyproject.toml per A10) with 1.0 s per-call timeout; polls every 200 ms.
- Log rotation uses `Path.rename()` before opening log file; rotate-on-open not rotate-on-close.
- `is_running()` uses `socket.create_connection` (not asyncio) because the service module runs in threads, not the async event loop.

One test fix during development: `test_start_command_pins_port_and_hostname` initially imported `subprocess` after the monkeypatch line (UnboundLocalError). Fixed by importing first and then patching the module attribute directly.

16 unit tests green.

### Step 3 — Route registration with gate (app.py)
Committed b60917b.

`_require_workbench()` uses `fastapi.Response(status_code=404)` (not `abort()`  which is a Flask pattern — FastAPI uses direct Response objects). Gate is the first call in all three handlers, before any logging, body parse, or subprocess touch (F-GATE-3).

`providers_active` hook: fire-and-forget daemon thread with bare `try/except Exception: pass` wrapper as specified. Import of `opencode` module is inside the try block so even ImportError (e.g. dep not installed) is swallowed.

`/api/notebooks/status`: 5th entry appended only when `"notebooks" in _visible_surfaces()` so min-tier callers never see it. Concurrent TCP probe added to the `asyncio.gather()` call (now 4 probes instead of 3).

`/api/system/health`: `opencode_port` added to port vars, `opencode_up` added to the `asyncio.gather()` call (now 9 probes), `"opencode": opencode_up` appended to `optional_services`.

### Step 4 — Templates
Committed 9ed8445.

`opencode.html`: 3-state UX cloned from `marimo.html` pattern. Iframe src is rendered as `http://127.0.0.1:{{ port }}/` — the port comes from the route handler which reads `OPENCODE_PORT` env (same source as `start()`), preventing drift. No credentials in URL (F-SEC-1).

`notebooks.html`: heading renamed Workbench; 5th card added with `style="display:none"` — revealed by `setCard()` JS when the status API returns the opencode entry (max-tier confirmation from server side). Title tag updated to match.

`_nav.html`: single-word change `Notebooks` → `Workbench`.

### Step 5 — Integration + lifecycle tests
Committed 048b897.

17 integration tests (test_opencode_routes.py) + 8 lifecycle tests (test_opencode_lifecycle.py) = 25 new tests.

All must-pass items from ARCHITECTURE.md §Test strategy covered:
- F-GATE-1, F-GATE-2, F-GATE-3 ✓
- F-SEC-1, F-SEC-2, F-SEC-3, F-SEC-6 ✓
- F-PROC-1, F-PROC-2, F-PROC-4, F-PROC-6 ✓
- F-RESTART-1, F-RESTART-2 ✓
- F-IFRAME-2, F-INSTALL-3 ✓
- F-CONFIG-1, F-CONFIG-2 ✓
- A1, A9 ✓
- Regression: existing notebook entry shapes unchanged ✓
- Regression: Workbench label in nav ✓

`test_wait_ready_timeout` uses a 0.8 s timeout (not 10 s) to keep the test suite fast.

## Architect feedback required

None. The architect's plan was implemented as-written. No contradictions discovered.

One probe result to document: the `_compute_source_env()` function imports from `arail.portal.app` at call-time (lazy import). The architect's spec says "Reads (no writes): _load_active_provider, _provider_token, _PROVIDER_META" — this is satisfied. The lazy import avoids the circular-import problem that would occur if `opencode.py` imported from `app.py` at module load time (since `app.py` imports from `services/`).

## Final state

**New tests:** 41 total (16 unit + 17 integration + 8 lifecycle)
**Full suite:** 554 passing, 5 pre-existing failures (test_toast_ui x2, test_chat_ui x1, test_drafter x1, test_buddy_suggesters x1 — none in this sprint's scope, all present before first commit)
**Coverage delta:** not measured (no coverage configured in test suite)
**Lines changed:**
  - `src/arail/portal/services/opencode.py` — 260 new lines
  - `src/arail/portal/app.py` — +126 / -32 lines
  - `src/arail/portal/templates/opencode.html` — 162 new lines
  - `src/arail/portal/templates/notebooks.html` — +55 / -4 lines
  - `src/arail/portal/templates/_nav.html` — 1 line changed
  - Tests — 641 new lines

**Commits:** 5 (c7eaf48, 8816ade, b60917b, 9ed8445, 048b897) + this update

**Deferred (per ARCHITECTURE.md §Deferred):**
- Version probe (F-INSTALL-2)
- Provider token redaction in opencode's own logs (F-SEC-4)
- `os.setsid` process group cleanup (F-PROC-3)
- PRIVACY.md trust-model note
- Skills folded into Agents (Sprint 2)
