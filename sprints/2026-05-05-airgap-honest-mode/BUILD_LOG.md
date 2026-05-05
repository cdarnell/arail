# Build log: airgap-honest-mode

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at e91b07a
**Started:** 2026-05-05

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/airgap.py`, `tests/test_airgap_helpers.py` | New: single source of truth for egress policy | `tests/test_airgap_helpers.py` (new) | pending |
| 2 | `src/arail/egress.py`, `tests/test_egress_guard.py`, `tests/conftest.py` | New: HTTP-layer guard + audit log + bypass context | `tests/test_egress_guard.py` (new) | pending |
| 3 | `src/arail/agents/builtin_seed.py`, `tests/test_builtin_seed_buddy_shim.py` | Buddy repave: shim template replaces shutil.copy | `tests/test_builtin_seed_buddy_shim.py` (new) | pending |
| 4 | `src/arail/config.py`, `src/arail/research/program_drafter.py`, `src/arail/agents/curator.py`, `src/arail/agents/_builtin_sre.py`, `src/arail/agents/browser.py` | Consolidate LAB_MODE call sites | existing regression suite | pending |
| 5 | `src/arail/portal/app.py`, `src/arail/portal/templates/_airgap_modal.html`, `src/arail/portal/templates/_nav.html`, `src/arail/portal/templates/chat.legacy.html`, `src/arail/portal/static/nav.js` + other base templates | API route + modal UI | manual smoke | pending |
| 6 | `src/arail/agents/_builtin_buddy.py`, `tests/test_buddy_airgap_watcher.py` | Buddy watcher + drop LAB_INTERNET_ENABLED | `tests/test_buddy_airgap_watcher.py` (new) | pending |
| 7 | `src/arail/portal/app.py`, `src/arail/agents/loader.py` | Wire install_guard() at portal startup + loader | smoke test | pending |
| 8 | `README.md`, `docs/PRIVACY.md`, `docs/agents.md` | Verbatim doc replacement from §11 | — | pending |
| 9 | `src/arail/router/backends.py` | Add `# noqa-airgap: localhost-only` at lines 231, 440, 590 | — | pending |
| 10 | `learnings/2026-05-05-allow-egress-task-scope.md` | Contextvars/asyncio learning stub | — | pending |

## Execution

### Step 1 — Layer 1: airgap.py + test_airgap_helpers.py
Status: pending

### Step 2 — Layer 2: egress.py + test_egress_guard.py + conftest.py
Status: pending

### Step 3 — Buddy repave: builtin_seed.py shim + test_builtin_seed_buddy_shim.py
Status: pending

### Step 4 — Consolidate LAB_MODE call sites
Status: pending

### Step 5 — API + modal
Status: pending

### Step 6 — Buddy watcher
Status: pending

### Step 7 — Wire install_guard() to portal startup + loader
Status: pending

### Step 8 — Docs
Status: pending

### Step 9 — Audit comments (backends.py noqa)
Status: pending

### Step 10 — Learnings
Status: pending

## Architect feedback required
(none at this time)

## Final state
(to be filled after all steps complete)
