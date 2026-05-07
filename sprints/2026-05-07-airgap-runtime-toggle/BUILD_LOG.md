# Build log: airgap-runtime-toggle

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 809d9c8
**Started:** 2026-05-07

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/env_writer.py`, `tests/test_env_writer.py` | NEW: pure env-file parser + atomic writer | test-first, all parser branches | TBD |
| 2 | `tests/test_airgap_toggle_concurrency.py` | NEW: 8-thread concurrent two-step flow test | test-first (concurrency) | TBD |
| 3 | `src/arail/portal/app.py` | EDIT: POST /api/airgap/toggle + bind_is_loopback in /api/airgap/status | endpoint + token table | TBD |
| 4 | `tests/test_airgap_toggle_endpoint.py` | NEW: full endpoint matrix (happy path, bind gate, CSRF, token expiry/replay) | after endpoint | TBD |
| 5 | `tests/test_buddy_watcher_after_runtime_toggle.py` | NEW: end-to-end watcher behavior after toggle | after endpoint | TBD |
| 6 | `src/arail/portal/templates/_airgap_modal.html` | EDIT: toggle section HTML | manual smoke | TBD |
| 7 | `src/arail/portal/static/nav.js` | EDIT: toggle handler + 3s countdown + 409→token→retry | manual smoke | TBD |
| 8 | `README.md`, `docs/PRIVACY.md` | EDIT: toggle documentation paragraph | docs | TBD |

## Execution

### Step 1 — env_writer.py + test_env_writer.py
<what was done; deltas from plan>
Commit: TBD

### Step 2 — test_airgap_toggle_concurrency.py (test-first for concurrency)
Commit: TBD

### Step 3 — POST /api/airgap/toggle + bind_is_loopback field
Commit: TBD

### Step 4 — test_airgap_toggle_endpoint.py
Commit: TBD

### Step 5 — test_buddy_watcher_after_runtime_toggle.py
Commit: TBD

### Step 6 — _airgap_modal.html toggle section
Commit: TBD

### Step 7 — nav.js toggle handler + countdown
Commit: TBD

### Step 8 — README.md + docs/PRIVACY.md documentation
Commit: TBD

## Architect feedback required
<empty>

## Final state
<pending>
