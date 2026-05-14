# Review: airgap-onetap-toggle

**Date:** 2026-05-14
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 1de7e85
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 1334ed1
**Reviewer:** architect (review mode)
**Commit range:** `e7d4301..HEAD` (8 commits)

## Verdict: PASS

All 15 failure modes in ARCHITECTURE.md map to code + tests. The token
machinery is cleanly removed (no residual references in `app.py`,
`nav.js`, or any test). Threat-model delta holds on inspection: CSRF
Origin gate + loopback-bind gate cover every real vector the token was
guarding; the same-origin unintended-click risk reduces to user
mis-click, which is now cheap to reverse (one tap back) and visible in
the audit log. Implementation order followed exactly per ARCHITECTURE
§"Recommended implementation order". 29/29 sprint tests pass locally
on the reviewer's run.

## Spec adherence

- Token symbols (`_TOGGLE_TOKENS`, `_TOGGLE_TOKENS_LOCK`,
  `_TOGGLE_TOKEN_TTL`, `_TokenEntry`, `_issue_token`, `_consume_token`,
  `_purge_expired_tokens`) — **all six gone** from `app.py`. `grep` for
  any of them yields zero matches.
- `confirm_token`, `need_confirm`, `countdown`, `_countdownTimer` — **zero
  matches** in `nav.js`. The two-step retry, the 3-second countdown, and
  the modal close-reopen `setTimeout` dance are all gone.
- `env_path` field — **dropped** from the success body (200 returns only
  `lab_mode`, `previous`, `took_effect_at`, `appended`); 05-07 follow-up
  #2 closed. (Local `env_path` variables for resolving the `.env` path
  remain — that's normal, not a leak.)
- Endpoint flow matches §Data-flow exactly: bind-gate → CSRF → parse →
  `set_env_var` → `os.environ` → `invalidate_probe_cache()` → audit →
  activity → 200.
- Modal copy ("Subprocesses (AirLLM, researcher) read LAB_MODE at
  start; restart them to pick up a flip.") present in template and
  tested (`test_modal_subprocess_staleness_note_present`).

## Failure-mode matrix

| # | Failure | Code | Test | Status |
|---|---|---|---|---|
| 1 | Rapid double-click race | `env_writer` per-path lock; client `aria-disabled` lockout (`nav.js:252-258`) | `test_8_threads_one_shot`, `test_two_threads_opposite_targets`, `test_env_writer_concurrent_no_torn_file` (32-thread) | OK |
| 2 | CSRF cross-origin | `app.py:6955-6962` | `test_toggle_cross_origin_rejected` (asserts 403, env unchanged, no audit line) | OK |
| 3 | POST with no Origin (legacy) | `if origin:` skipped → legacy-compat | covered by happy-path TestClient (no Origin header) | OK |
| 4 | Non-loopback bind | `app.py:6949-6953` | `test_toggle_bind_gate_lan`, `test_toggle_bind_gate_ipv4_lan`, `test_toggle_bind_gate_ipv6_loopback_ok` | OK |
| 5 | `.env` write fails | `app.py:6980-6985` (catch, return 500, skip environ/cache/audit/activity) | `test_toggle_writer_failure_no_path_leak` | OK |
| 6 | Optimistic UI on 5xx | `nav.js:303-318` reverts `_setActive(prevActive)` + `_updatePill(prevActive)` | DOM-test asserts segmented-control structure; runtime revert tested by inspection (no automated UI driver — acceptable, called out in §Manual smoke) | OK |
| 7 | Worker staleness | Modal copy | `test_modal_subprocess_staleness_note_present` | OK (documented limit) |
| 8 | Audit-log append fails | `_append_audit` retains broad-except + `_log.warning` (`app.py:6922-6923`) | Behavior preserved; not directly tested but unchanged from 05-07 | OK (preserved per spec) |
| 9 | `_PROBE_CACHE` retains stale | `invalidate_probe_cache()` called at `app.py:6989` | `test_probe_cache_invalidated_on_flip`, `test_probe_cache_busted_after_onetap_toggle` | OK |
| 10 | Modal closed mid-fetch | DOM mutations only touch elements via id-lookup; safe no-op if gone | Not explicitly tested (low-risk, defensive code present) | OK |
| 11 | Concurrent flips opposite directions | per-path env_writer lock | `test_two_threads_opposite_targets` (2x 200; exactly 2 audit lines; final state one-or-other) | OK |
| 12 | Legacy client sends `confirm_token` | Field ignored (only `target` read) | `test_toggle_legacy_confirm_token_field_ignored` | OK |
| 13 | Path leakage in 500 body | Body is `{"error":"env_write_failed"}` byte-exact | `test_toggle_writer_failure_no_path_leak` (assertEqual on body) | OK |
| 14 | `source_ip` always loopback | Acceptable | `test_audit_line_emitted_per_flip` checks shape | OK |
| 15 | XSS via error message | `nav.js:236` uses `el.textContent` (not innerHTML); error strings hard-coded client-side | DOM-test confirms structure; textContent usage by inspection | OK |

## Code quality findings

- [INFO] `nav.js` segmented-control IIFE is ~100 lines; readable, no
  helpers exceed ~10 lines. No duplication.
- [INFO] `post_airgap_toggle` is now ~90 lines including docstring and
  in-function imports. Cyclomatic complexity is low (linear gate chain
  with early returns). The in-function imports of `EnvWriterError`,
  `set_env_var`, `JSONResponse`, `invalidate_probe_cache`,
  `datetime/timezone` are pre-existing style in `app.py`; not a smell.
- [INFO] No orphaned CSS — `.airgap-segmented` is used; old confirm-panel
  classes are gone from the template.

## Security findings

- [INFO] Threat-model delta in ARCHITECTURE §"Threat-model delta" is
  sound as inspected. CSRF Origin + bind-loopback are present, ordered
  correctly (bind first so a LAN POST cannot even reveal whether the
  Origin gate would have fired), and the gates short-circuit before any
  state mutation.
- [INFO] `invalidate_probe_cache()` is a `dict.clear()` — thread-safe
  under the GIL, no lock needed.
- [INFO] Tokens in JSON body are still ignored (`body.get("target")`
  only); confirms forward-compat with 05-07 cached clients.
- [INFO] No path/exception text reaches the wire on 500.

## Test coverage assessment

- Sprint test files: 4 (2 rewritten, 2 new). Total airgap tests: 29
  passing (verified by reviewer running pytest).
- Failure-mode → test mapping: 13 of 15 modes have a direct assertion;
  mode #8 (audit silent-swallow) is unchanged from 05-07 so reusing
  prior regression coverage; mode #10 (modal-closed mid-fetch) relies on
  defensive id-lookups without an explicit test — acceptable for a
  cosmetic surface.
- Coverage on changed lines: very high (every branch in the new
  `post_airgap_toggle` has a test).

## Performance assessment

Not on a hot path; no benchmark needed. Concurrency under contention is
covered by the 8-thread one-shot and 32-thread env-writer tests.

## Tech debt delta

Matches ARCHITECTURE §"Tech debt" exactly:

- **Removed:** all six token symbols, countdown timer, modal
  close-reopen dance, confirm panel HTML/CSS, `env_path` from response,
  409 path entirely.
- **Repaid:** 05-07 follow-up #2 (`env_path` leak) closed.
- **Deferred (re-confirmed after seeing code):**
  - `Sec-Fetch-Site: same-origin` defense-in-depth. **Reviewer
    re-evaluation:** with the token gone, the Origin gate is now the
    sole browser-CSRF defense. A modern attacker page that omits the
    Origin header on a cross-site `fetch()` cannot do so (browsers
    force-set it on POST); a `<form>` cross-site POST also sets Origin.
    The risk delta from removing the token is therefore still
    acceptable. **Sec-Fetch-Site defer stands.** File as ticket.
  - 05-07 follow-up #3 (`_toggle_env_path()` parents-walk) untouched.
  - Subprocess `LAB_MODE` staleness — documented in modal copy.
  - `_append_audit` silent-swallow — preserved.

**Net debt:** Negative (debt removed > debt added). No new debt
introduced beyond what ARCHITECTURE pre-flagged.

## Required actions before merge

None. WEAK_PASS would have been the verdict if any of the deferred items
had grown teeth on inspection; they did not.

## Follow-up tickets (file before ship)

1. Add `Sec-Fetch-Site: same-origin` defense-in-depth check to
   `/api/airgap/toggle` (05-07 follow-up #1; re-confirmed by this
   review).
2. Future sprint: subprocess `LAB_MODE` reload signal (e.g. `SIGUSR1`
   handler in AirLLM / researcher).
3. Future sprint: hard-fail mode for `_append_audit` if audit
   durability becomes a compliance concern.

## Ready for QA?

**Yes.** Hand off to `qa` subagent with the arail QA allocation (30%
setup / 30% Buddy / 20% security / 10% happy / 10% regression). The
security minimum is already satisfied by sprint tests; QA should focus
on setup-on-clean-machine (the modal renders cleanly at first boot),
Buddy watcher behavior across real flips, and the manual smoke items
listed in ARCHITECTURE §Test-strategy → "Happy / UX" (force a 500 via
chmod, confirm UI reverts).
