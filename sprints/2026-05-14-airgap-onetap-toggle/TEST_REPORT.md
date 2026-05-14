# Test report: airgap-onetap-toggle

**Date:** 2026-05-14
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 60abfb9
**Verdict:** FAIL — stale prior-sprint QA test files (4) hardcode the 2-step token
protocol and break the regression slice. The sprint's *own* code is sound (29 sprint
tests + 24 new paranoid tests = 53/53 green). But QA allocation is 10% regression,
and the suite as a whole goes from 154 passing baseline to 35 failing tests on `main`
after this change. Fix is small (delete or rewrite the 4 stale files); routing back
to builder.

## TL;DR

- **24 new paranoid tests added** in `tests/test_qa_airgap_onetap_paranoid.py` — all pass.
- **No bugs found** in the new one-tap implementation. Every paranoid case the architect
  flagged (CSRF shapes, write-failure modes, stale-tab idempotence, probe-cache
  invariant, post-flip egress contract, two-tab race, audit-append failure, nav.js
  defenses) is now covered and green.
- **One regression-hygiene failure**: 4 prior-sprint QA test files (35 tests) still
  reference the removed `confirm_token` / 2-step protocol. ARCHITECTURE §Test-strategy
  §Regression said "Tests asserting `409 need_confirm` are **rewritten** to assert
  `200`" — that was done for the two sprint-test files but missed for the four
  prior-sprint QA files.

## Test inventory (new)

File: `tests/test_qa_airgap_onetap_paranoid.py` (24 tests, all PASS)

| # | Test | Category | Covers |
|---|---|---|---|
| 1 | `test_origin_null_string_is_treated_as_same_origin` | Security | Pins documented CSRF gap: `Origin: null` (sandboxed iframe / Privacy Sandbox) has empty netloc, bypasses Origin gate, falls to bind-gate backstop |
| 2 | `test_cross_origin_different_port_rejected` | Security | Origin port shift caught by netloc inequality |
| 3 | `test_cross_origin_different_scheme_same_host_rejected` | Security | Pins scheme-agnostic Origin check (intentional today; flips when follow-up #1 Sec-Fetch-Site lands) |
| 4 | `test_cross_origin_malformed_no_netloc_passes` | Security | Garbage Origin → empty netloc → legacy-compat 200; bind-gate is backstop |
| 5 | `test_cross_origin_evil_subdomain_rejected` | Security | Cookie-tossing / suffix-match: `evil.testserver` ≠ `testserver` → 403 |
| 6 | `test_eisdir_envpath_is_directory` | Edge | Misconfigured `.env`-as-directory → 500 + no leak |
| 7 | `test_permission_error_caught_no_leak` | Security | `PermissionError` → 500 `{error:env_write_failed}`; path not in body |
| 8 | `test_unexpected_exception_does_not_propagate` | Security | Unexpected `RuntimeError` swallowed; no internal detail leaks |
| 9–12 | `test_cache_not_busted_on_{bind,csrf,invalid_target,writer}_reject` | Security | `invalidate_probe_cache()` fires only on successful flip — closes minor DoS / info-leak surface |
| 13 | `test_post_current_target_returns_200` | Edge / Regression | Stale-tab POST of already-current target is idempotent + audit-logged |
| 14 | `test_is_airgapped_reflects_flip_to_hybrid` | Buddy | `arail.airgap.is_airgapped()` reflects new mode on next call (no cache) |
| 15 | `test_is_airgapped_reflects_flip_back_to_airgapped` | Buddy | Reverse direction same contract |
| 16 | `test_status_endpoint_reflects_flip_immediately` | Buddy | `/api/airgap/status` returns post-flip mode within same session |
| 17 | `test_audit_failure_does_not_block_flip` | Security | If audit raises externally, `.env` was written first (order invariant) |
| 18 | `test_real_internal_audit_failure_returns_200` | Security | Read-only audit dir → internal swallow → 200 still returned; `.env` flipped |
| 19 | `test_nav_js_exists` | Happy | sanity |
| 20 | `test_nav_js_uses_textcontent_not_innerhtml_for_errors` | Security | XSS guard: no `innerHTML` writes near airgap code |
| 21 | `test_nav_js_no_residual_countdown_or_two_step_code` | Regression | `confirm_token`, `need_confirm`, `_countdownTimer`, `Confirm (3)` etc. absent |
| 22 | `test_nav_js_has_segmented_control_handler` | Happy | new segmented-control wiring present |
| 23 | `test_two_threads_opposite_targets_no_torn_write` | Edge / Concurrency | Opposite-target race: 2× 200, no torn `.env`, exactly 2 audit lines |
| 24 | `test_status_response_no_path_disclosure` | Security | `/api/airgap/status` body contains no filesystem paths |

## Failures (the 35 stale-test regressions)

| # | Test file | Symptom | Severity |
|---|---|---|---|
| 1 | `tests/test_qa_airgap_toggle_security.py` (~21 failures) | Hardcodes `confirm_token` / `_issue_token` / `need_confirm` from removed 2-step protocol; KeyErrors and 200-vs-409 mismatches | **Medium** — regression-hygiene; not a runtime bug, but the sprint's own architecture spec required these to be rewritten |
| 2 | `tests/test_qa_airgap_toggle_setup_happy.py` (~5 failures) | Asserts 409 on first POST, then re-POSTs with token; first POST now returns 200 directly | **Medium** — same root cause |
| 3 | `tests/test_qa_airgap_toggle_buddy.py` (~3 failures) | `_step1_get_token` helper expects 409+`confirm_token` body | **Medium** — same root cause |
| 4 | `tests/test_buddy_watcher_after_runtime_toggle.py` (~2 failures) | Calls the prior 2-step endpoint protocol | **Medium** — same root cause |

**Minimal repro for all 35:** `python -m pytest tests/test_qa_airgap_toggle_security.py -q`

**These are not bugs in the implementation.** They are stale tests that the sprint's
own §Test-strategy required to be rewritten. ARCHITECTURE.md line 354–356:
> "Tests asserting `409 need_confirm` are **rewritten** to assert `200`. Tests
> asserting `env_path` in the success body are **rewritten** to assert its absence."

Builder rewrote `test_airgap_toggle_endpoint.py` and `test_airgap_toggle_concurrency.py`
but missed these four prior-sprint `test_qa_*` files. Easy fix: either delete them
(coverage is replaced by the sprint-owned files + this new paranoid file) or rewrite
the 35 cases to one-tap protocol. Recommend deletion of `test_qa_airgap_toggle_security.py`,
`test_qa_airgap_toggle_setup_happy.py`, `test_qa_airgap_toggle_buddy.py`, and
`test_buddy_watcher_after_runtime_toggle.py` since the new paranoid file + sprint
files supersede their coverage.

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User input (`target` body field) | Verified rejection of: non-`{airgapped,hybrid}` strings, missing field, empty body, body-with-only-`confirm_token` (legacy), `confirm_token` of bytes/int/null types ignored | Clean — `body.get("target", "")` + `if target not in {airgapped,hybrid}` guard is the whole contract |
| CSRF | Verified Origin gate fires on: cross-host, different-port, different-subdomain. Pinned documented gaps: empty netloc (Origin:null, garbage), scheme-agnostic netloc compare. Bind-gate confirmed as backstop | Sound. Sec-Fetch-Site defer is documented as follow-up #1; threat model holds without it because cross-site `fetch()` and `<form>` POST both force-set Origin in modern browsers |
| File I/O (.env write) | Verified `EnvWriterError`, `PermissionError`, `RuntimeError`, and EISDIR (path-is-directory) all caught and reduced to `{"error":"env_write_failed"}` with no path/exception text in body | Clean — broad `except Exception` after `EnvWriterError` catches every failure mode |
| File I/O (audit) | Confirmed silent-swallow preserved per spec failure-mode #8; verified `.env` is written BEFORE audit append (order invariant matters for atomicity of the user-visible flip) | Acceptable; flagged as follow-up #3 if audit durability becomes a compliance concern |
| Probe cache | Confirmed `invalidate_probe_cache()` fires only on successful flip — not on bind-reject, CSRF-reject, invalid-target, or writer-failure paths | Clean |
| Path disclosure | Verified neither toggle nor status responses leak filesystem paths or exception text | Clean — 05-07 follow-up #2 closed |
| XSS | Verified nav.js does not use `innerHTML` for any airgap-related DOM write (regex scan); error strings are hard-coded client-side | Clean |
| Audit log permissions | Verified 0o600 on creation (existing test) | Clean |
| Crypto | N/A — no crypto in this surface (token machinery removed; nothing to verify) | N/A |
| Dependencies | No new deps added by this sprint | N/A |

## Performance

N/A — not on a hot path. Concurrency under contention covered by
`test_two_threads_opposite_targets_no_torn_write` (new) + existing 8-thread and
32-thread tests.

## Coverage delta

Before (sprint tests only): 29 passing (per BUILD_LOG.md).
After (sprint tests + this QA file): 53 passing.
Full airgap+buddy slice on `main`: 240 passing, 35 failing — see Failures table;
all 35 are stale prior-sprint files, not sprint regressions.

## Notes for the next QA pass

- The four stale `test_qa_airgap_*.py` files need to be deleted or migrated as part
  of the sprint-cleanup follow-up. They were a prior-sprint QA artifact pinned to
  the 2-step protocol; that protocol is gone.
- Documented CSRF gaps (`Origin: null`, malformed-netloc, scheme-agnostic) are now
  pinned by test. When follow-up #1 (Sec-Fetch-Site defense-in-depth) lands, those
  three pinned tests will need to flip.
- Modal-close mid-fetch behavior is asserted only by static analysis (no JS runtime
  in pytest). If a JS test harness lands later, that's the place to add a real
  promise-after-DOM-mutation test.
- Subprocess `LAB_MODE` staleness — out of scope this sprint, documented in modal
  copy. When the SIGUSR1 reload signal lands, add an integration test that flips
  mode and verifies a child process picks it up.

---

## Re-verification 2026-05-14

**Verdict:** PASS

### Pytest summary

Command: `pytest tests/test_qa_airgap_*.py tests/test_airgap_*.py tests/test_buddy_watcher_*.py -v`

Result: **184 passed, 0 failed, 6 warnings in 3.68s** (deprecation warnings only — `on_event`, SWIG; unrelated to this sprint).

### Deletion / migration spot-check

- `tests/test_qa_airgap_toggle_buddy.py` — gone (ls fails). Confirmed.
- `tests/test_buddy_watcher_after_runtime_toggle.py` — gone (ls fails). Confirmed.
- `tests/test_qa_airgap_toggle_security.py` — **still present**, but migrated in-place to one-tap protocol (326 lines, all passing). Builder report said "migrated" for this one, not "deleted" — consistent with commit `02d7038`.
- `tests/test_qa_airgap_toggle_setup_happy.py` — **still present**, migrated in-place (209 lines, all passing). Same story.

Builder's claim "9 migrated, 34 deleted, 16 kept" is internally consistent: the four "stale" files split as 2 deleted + 2 migrated.

### Security-coverage sample (5 sensitive deletions → matching new coverage)

| Deleted concern | Confirmed covered by |
|---|---|
| Cross-origin CSRF rejection | `test_qa_airgap_onetap_paranoid.py::test_cross_origin_different_port_rejected`, `…_different_scheme_same_host_rejected`, `…_evil_subdomain_rejected`; `test_airgap_toggle_endpoint.py::test_toggle_cross_origin_rejected` |
| Writer-failure path-disclosure leak | `test_airgap_toggle_endpoint.py::test_toggle_writer_failure_no_path_leak`; `test_qa_airgap_onetap_paranoid.py::test_status_response_no_path_disclosure`, `…_permission_error_caught_no_leak`, `…_unexpected_exception_does_not_propagate` |
| Bind-gate (loopback enforcement, LAN/IPv6) | `test_airgap_toggle_endpoint.py::test_toggle_bind_gate_lan`, `…_ipv4_lan`, `…_ipv6_loopback_ok`; `test_qa_airgap_ipv6_edge_cases.py` (full file) |
| Audit log integrity (`0600` mode, per-flip line) | `test_airgap_toggle_endpoint.py::test_audit_line_emitted_per_flip`, `…_audit_log_mode_600`; `test_qa_airgap_onetap_paranoid.py::test_audit_failure_does_not_block_flip`, `…_real_internal_audit_failure_returns_200` |
| Concurrent torn-write on opposite-target flips | `test_airgap_toggle_concurrency.py::test_two_threads_opposite_targets`, `…_8_threads_one_shot`, `…_env_writer_concurrent_no_torn_file`; `test_qa_airgap_onetap_paranoid.py::test_two_threads_opposite_targets_no_torn_write` |
| (bonus) Probe-cache invalidation gated by success | `test_qa_airgap_onetap_paranoid.py::test_cache_not_busted_on_bind_gate_reject`, `…_csrf_reject`, `…_invalid_target`, `…_writer_failure`; `test_airgap_toggle_endpoint.py::test_probe_cache_invalidated_on_flip` |
| (bonus) Buddy watcher fires only on real mode change | `test_buddy_watcher_after_onetap_toggle.py::test_watcher_fires_after_one_tap_toggle`, `…_no_fire_when_mode_unchanged`, `…_rapid_toggle_5x_no_double_fire` |

No coverage gaps surfaced in the sample.

### Ready to ship?

**Yes.** All 184 airgap-slice tests pass; the prior FAIL-causing stale 2-step protocol assertions are gone (either migrated or deleted); security surface is covered across CSRF, leak, bind-gate, audit, concurrency, cache-gating, and watcher dimensions. Cleared for `/sprint ship`.
