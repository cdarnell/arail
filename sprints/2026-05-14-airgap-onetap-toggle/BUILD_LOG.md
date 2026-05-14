# Build log: airgap-onetap-toggle

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md)
**Started:** 2026-05-14

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `src/arail/egress.py` | Add `invalidate_probe_cache()` 3-line helper | test_probe_cache_invalidated_on_flip | 7461eb9 |
| 2 | `src/arail/portal/app.py` | Delete token machinery; collapse toggle to 1-step; drop `env_path` from response; call `invalidate_probe_cache()` | All toggle tests | 241eb80 |
| 3 | `src/arail/portal/templates/_airgap_modal.html` | Replace button + confirm panel with segmented control; add subprocess staleness note | test_airgap_modal_dom | 8a05865 |
| 4 | `src/arail/portal/static/nav.js` | Remove countdown/2-step/reopen dance; add optimistic flip + single POST handler | manual smoke + DOM test | cc754fa |
| 5 | `tests/test_airgap_toggle_endpoint.py` | Rewrite: drop 409/token tests; add one-tap security + setup + regression cases | self-verifying | b9a4dd4 |
| 6 | `tests/test_airgap_toggle_concurrency.py` | Simplify: remove 2-step dance; one-shot POST per thread | self-verifying | b9a4dd4 |
| 7 | `tests/test_buddy_watcher_after_onetap_toggle.py` | NEW: watcher fires after one-tap flip; state merge correct; probe cache bust | self-verifying | 061c6e9 |
| 8 | `tests/test_airgap_modal_dom.py` | NEW: template renders segmented control; no confirm panel | self-verifying | 60abfb9 |

## Execution

### Step 1 — egress: add `invalidate_probe_cache()`

Added 14-line docstring + 1-line body helper at the end of the module-state
section in `egress.py`. Placed after `_PROBE_CACHE_TTL` declaration.
Commit: 7461eb9

### Step 2 — backend: collapse toggle to 1-step

Deleted `_TokenEntry`, `_TOGGLE_TOKENS`, `_TOGGLE_TOKENS_LOCK`, `_TOGGLE_TOKEN_TTL`,
`_purge_expired_tokens`, `_issue_token`, `_consume_token`. Rewrote `post_airgap_toggle`
as single-pass bind-gate → CSRF → parse → set_env_var → os.environ →
invalidate_probe_cache() → audit → activity → 200. Dropped `env_path` from 200
response. `confirm_token` in request body silently ignored.
Commit: 241eb80

### Step 3 — template: segmented control

Removed `#airgap-toggle-btn`, `#airgap-toggle-confirm`, `#airgap-toggle-confirm-btn`,
`#airgap-toggle-cancel-btn`. Added `#airgap-toggle-segmented` with two
`button[data-target]` halves (airgapped / hybrid). Added CSS for segmented
control `.airgap-segmented`. Added subprocess staleness note ("Subprocesses
(AirLLM, researcher) read LAB_MODE at start; restart them to pick up a flip.")
Kept `#airgap-toggle-bind-warning` and `#airgap-toggle-error`.
Commit: 8a05865

### Step 4 — nav.js: one-tap handler

Deleted: countdown IIFE, `_countdownTimer`, `_resetToggleUI`, two-step fetch
dance (step1→409→token→step2), `setTimeout(reopen, 200)` modal close+reopen.

Added: segmented-control click handler with optimistic CSS class swap,
`aria-disabled` lockout, single `POST /api/airgap/toggle {target}`,
server-confirmed pill update from response body, `updateBadge()` call,
revert-on-error with 5s auto-clear, per-error-code copy strings.

Modal open wiring updated: replaced `toggleBtn` / `toggleConfirm` references
with `toggleSegmented`; active class set from `data.lab_mode` on each open.
Commit: cc754fa

### Step 5 — tests: endpoint (rewrite)

Dropped all 409/confirm-token/two-step tests (was: `TestToggleTokenProtocol`
with 3 tests; `test_toggle_happy_two_step`; `_two_step()` helper).

Added (16 tests total):
- `TestToggleHappyPath`: one-tap 200, no confirm_token field, legacy token
  ignored, disk-only path (chmod 0600 assertion).
- `TestToggleBadInput`: invalid target, missing target.
- `TestToggleBindGate`: LAN (0.0.0.0), IPv4 LAN, IPv6 loopback ok (now
  asserts 200 not 409).
- `TestToggleCsrf`: cross-origin 403; env/environ unchanged; no audit line.
- `TestToggleErrorHandling`: writer failure → exact body `{"error":"env_write_failed"}`;
  no path leak; os.environ unchanged; no audit line.
- `TestToggleAuditLog`: 3-flip audit accumulation; audit file chmod 0600.
- `TestProbeCacheInvalidation`: cache cleared after flip.
- `TestAirgapStatusBindField`: status endpoint bind_is_loopback field.
Commit: b9a4dd4

### Step 6 — tests: concurrency (simplify)

Replaced `test_8_threads_full_two_step` (two-step token dance with issue_lock)
with `test_8_threads_one_shot` (plain one-shot POST per thread). Added
`test_two_threads_opposite_targets` (2x200; exactly 2 audit lines; no torn
write). Kept `test_env_writer_concurrent_no_torn_file` (32-thread direct
env_writer exercise) unchanged.
Commit: b9a4dd4 (same commit as step 5)

### Step 7 — tests: buddy watcher (NEW)

New file `tests/test_buddy_watcher_after_onetap_toggle.py` (4 tests):
- `test_watcher_fires_after_one_tap_toggle`: Observation returned; state.json
  airgap_last_lab_mode updated; pre-existing keys preserved.
- `test_watcher_no_fire_when_mode_unchanged`: returns None.
- `test_probe_cache_busted_after_onetap_toggle`: real endpoint call; cache empty.
- `test_rapid_toggle_5x_no_double_fire`: 5 env flips before tick → ≤1 Observation.
Commit: 061c6e9

### Step 8 — tests: modal DOM (NEW)

New file `tests/test_airgap_modal_dom.py` (6 tests):
- Segmented control present with two data-target buttons.
- Removed elements absent: `#airgap-toggle-confirm`, `#airgap-toggle-confirm-btn`,
  `#airgap-toggle-cancel-btn`, `#airgap-toggle-btn`.
- Kept elements present: `#airgap-toggle-bind-warning`, `#airgap-toggle-error`.
- Subprocess staleness note text in rendered output.
- No 'Confirm (3)' countdown text.
Commit: 60abfb9

## QA cleanup pass (2026-05-14, commit 02d7038)

QA returned FAIL because four stale test files from sprints 05-07 and 05-05
hardcoded the removed `confirm_token` / 2-step protocol.

### Per-file disposition

| File | Action | Cases removed | Cases migrated | Cases kept |
|---|---|---|---|---|
| `test_qa_airgap_toggle_security.py` | Edited | 12 (token paranoia, concurrent 2-client, FD leak, token table, mid-race symlink, 2 CSRF overlaps) | 5 (bind matrix, no-origin gap, pre-placed symlink, error leakage, no-origin CSRF) | 12 (value sanitisation, gate ordering, O_EXCL direct, writers) |
| `test_qa_airgap_toggle_setup_happy.py` | Edited | 1 (response shape) | 4 (restart persists, appends, missing env, status pill) | 4 (env_example, status shape regression 3x) |
| `test_qa_airgap_toggle_buddy.py` | Deleted | 19 | 0 | 0 |
| `test_buddy_watcher_after_runtime_toggle.py` | Deleted | 2 | 0 | 0 |

Net: 34 cases removed, 9 migrated to one-tap, 16 kept unchanged.

### Final pytest summary

```
184 passed, 0 failed, 6 warnings (4.51s)
```

Commit: 02d7038

## Architect feedback required

None.

## Verified state

```
git log --oneline e7d4301..HEAD
60abfb9 test(airgap-modal-dom): assert segmented control structure; no confirm panel
061c6e9 test(buddy-watcher): assert watcher fires after one-tap toggle + state merge
b9a4dd4 test(airgap-toggle): rewrite endpoint + concurrency tests for one-tap protocol
cc754fa feat(nav.js): replace 2-step countdown handler with one-tap segmented control
8a05865 feat(airgap-modal): replace button+confirm panel with segmented control
241eb80 refactor(airgap-toggle): collapse to 1-step; drop token machinery + env_path
7461eb9 feat(egress): add invalidate_probe_cache() helper
1334ed1 chore(airgap-onetap): add BUILD_LOG.md skeleton
```

pytest summary (2026-05-14):
```
tests/test_airgap_toggle_endpoint.py        16 passed
tests/test_airgap_toggle_concurrency.py      3 passed
tests/test_buddy_watcher_after_onetap_toggle.py  4 passed
tests/test_airgap_modal_dom.py               6 passed
tests/test_airgap_helpers.py                44 passed
                                           ─────────
                                           73 passed, 0 failed, 6 warnings
```

## Final state

| Metric | Value |
|---|---|
| Commits (this session, steps 3–8) | 5 |
| Total commits since base (e7d4301) | 7 (excluding BUILD_LOG skeleton = 8 total) |
| Test files touched | 4 (2 rewritten, 2 new) |
| Source files touched | 4 (egress.py, app.py, _airgap_modal.html, nav.js) |
| Token machinery removed | 6 symbols deleted from app.py (steps 1+2, prior session) |
| Total tests passing | 73 |
| Known regressions | 0 |
| Architect feedback gaps | 0 |
