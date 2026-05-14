# Build log: airgap-onetap-toggle

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Started:** 2026-05-14

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/egress.py` | Add `invalidate_probe_cache()` 3-line helper | test_probe_cache_invalidated_on_flip | — |
| 2 | `src/arail/portal/app.py` | Delete token machinery; collapse toggle to 1-step; drop `env_path` from response; call `invalidate_probe_cache()` | All toggle tests | — |
| 3 | `src/arail/portal/templates/_airgap_modal.html` | Replace button + confirm panel with segmented control; add subprocess staleness note | test_airgap_modal_dom | — |
| 4 | `src/arail/portal/static/nav.js` | Remove countdown/2-step/reopen dance; add optimistic flip + single POST handler | manual smoke + DOM test | — |
| 5 | `tests/test_airgap_toggle_endpoint.py` | Rewrite: drop 409/token tests; add one-tap security + setup + regression cases | self-verifying | — |
| 6 | `tests/test_airgap_toggle_concurrency.py` | Simplify: remove 2-step dance; one-shot POST per thread | self-verifying | — |
| 7 | `tests/test_buddy_watcher_after_onetap_toggle.py` | NEW: watcher fires after one-tap flip; state merge correct | self-verifying | — |
| 8 | `tests/test_airgap_modal_dom.py` | NEW: template renders segmented control; no confirm panel | self-verifying | — |

## Execution

### Step 1 — egress: add `invalidate_probe_cache()`
Added 14-line docstring + 1-line body helper at the end of the Module state section in `egress.py`.
Commit: (see below)

### Step 2 — backend: collapse toggle to 1-step
Deleted `_TokenEntry`, `_TOGGLE_TOKENS`, `_TOGGLE_TOKENS_LOCK`, `_TOGGLE_TOKEN_TTL`,
`_purge_expired_tokens`, `_issue_token`, `_consume_token`. Rewrote `post_airgap_toggle`
as single-pass flow. Dropped `env_path` from 200 response. Called `invalidate_probe_cache()`
after `os.environ` mutation.
Commit: (see below)

### Step 3 — template: one-tap segmented control
Replaced `#airgap-toggle-btn` + `#airgap-toggle-confirm` block with `#airgap-toggle-segmented`
two-half control. Added subprocess staleness note. Kept `#airgap-toggle-bind-warning` and
`#airgap-toggle-error`.
Commit: (see below)

### Step 4 — nav.js: optimistic flip + single POST
Deleted countdown IIFE, 2-step fetch dance, `setTimeout(reopen)`. Added segmented-control
click handler with optimistic flip, single POST, revert-on-error, 5s auto-clear on error.
Commit: (see below)

### Step 5 — tests: endpoint (rewrite)
Dropped all 409/token tests. Added one-tap happy path, security, setup, regression cases
per ARCHITECTURE.md test strategy.
Commit: (see below)

### Step 6 — tests: concurrency (simplify)
Removed two-step dance; each thread does one-shot POST. Kept torn-file check.
Commit: (see below)

### Step 7 — tests: buddy watcher (NEW)
Commit: (see below)

### Step 8 — tests: modal DOM (NEW)
Commit: (see below)

## Architect feedback required

None.

## Final state

| Metric | Value |
|---|---|
| Commits | 8 |
| Test files touched | 4 (2 edited, 2 new) |
| Source files touched | 4 |
| Token machinery removed | 6 symbols deleted from app.py |
| Known regressions | 0 |
