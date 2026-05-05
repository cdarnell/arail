# Review: opencode in Workbench (Sprint 1)

**Date:** 2026-05-04
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 14fba3b
**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at 50ce5ad
**Reviewer:** architect (review mode)

## Verdict: PASS

No BLOCK findings. Two INFO notes recorded for future polish; neither
gates ship.

---

## Spec adherence

The implementation tracks the revised Path-A architecture closely:

- Three routes only (`GET /opencode`, `POST /api/opencode/start`,
  `POST /api/opencode/stop`) — no `/opencode/proxy/*`. Confirmed at
  `src/arail/portal/app.py:1235,1253,1266`.
- No reverse-proxy code, no `httpx` dependency. `pyproject.toml` shows
  no `httpx` add (verified via `grep`).
- No `OPENCODE_SERVER_PASSWORD` referenced anywhere outside the
  ARCHITECTURE.md decision and the service module docstring noting it
  is intentionally NOT set. `lab/data/secrets.env` carries no opencode
  key.
- Module surface matches §Interface contracts: `is_installed`,
  `is_running`, `start`, `stop`, `restart`, `_wait_ready`,
  `_compute_source_env`, `install_hint`, plus the `_lock`,
  `READINESS_PATH = "/doc"`, `HOST = "127.0.0.1"`, `PORT_DEFAULT = 4096`
  constants exactly as specified.
- Builder used FastAPI `Response(status_code=404)` rather than Flask
  `abort(404)`. The architecture doc was loose terminology
  ("Flask Response (404)") — the portal is FastAPI; this is the right
  call. Spec adherence preserved.

Drift: none worth blocking. All deferred items in BUILD_LOG.md match
ARCHITECTURE.md §Deferred.

---

## Code quality findings

- **[INFO]** `start()` and `_start_inner()` at
  `src/arail/portal/services/opencode.py:80-120` and `:217-243` are
  near-duplicates differing only in the `with _lock:` wrapper. The
  duplication is intentional (avoids re-entrant lock acquisition in
  `restart()`), and both branches are short, but a single
  `_do_start(port)` helper called from both wrappers would remove
  ~25 lines. Not blocking.
- **[INFO]** `_stop_unlocked()` runs `lsof -ti :<port>` three times
  (lines 141, 159, 167). Functionally fine; mildly inefficient and
  introduces three independent failure surfaces. A single bounded
  poll loop would be cleaner. Not blocking.
- Naming, complexity, and comments are otherwise good. `_log` is used
  consistently; comments reference the failure-mode IDs by number,
  which makes the cross-reference to ARCHITECTURE.md trivial.

---

## Security findings (paranoia checklist results)

1. **Gate airtightness (F-GATE-1/2/3) — PASS.**
   `_require_workbench()` at `app.py:1220` is the *first* statement of
   each of the three handlers (`app.py:1238, 1256, 1269`) — verified by
   reading each handler, not just the test. The gate body itself only
   reads `_visible_surfaces()` and constructs a `Response` — no
   logging, no body parse, no module import of `services.opencode`,
   no secret reads. The lazy `from arail.portal.services import
   opencode as oc` is below the gate in every handler, so min-tier 404s
   never even import the service module. F-GATE-3 is structurally
   closed, not just test-asserted.

2. **Iframe credentials (F-SEC-1) — PASS.**
   `templates/opencode.html:82` renders `src="http://127.0.0.1:{{ port }}/"`.
   No credential interpolation anywhere; `port` is the only variable.
   Test `test_max_tier_page_iframe_url_no_credentials` at
   `tests/portal/test_opencode_routes.py:112` asserts both the literal
   format and a regex-negation against `user:pass@`.

3. **No new secrets (F-SEC architecture decision) — PASS.**
   `lab/data/secrets.env` not modified for opencode. No
   `OPENCODE_SERVER_PASSWORD` written or referenced in code paths;
   only mentioned in the service module docstring noting its absence.

4. **Subprocess lifecycle — PASS.**
   - `start()` at `opencode.py:111` passes `--port str(port)`
     explicitly (default 4096). `--hostname HOST` (= `127.0.0.1`) is
     hard-coded — there is no env override for hostname (F-SEC-6
     defense-in-depth). Test at
     `tests/portal/test_opencode_service.py:157` asserts both flags
     present in the Popen argv with the correct following values.
   - `stop()` at `opencode.py:135` mirrors the Jupyter pattern:
     `lsof -ti` → SIGTERM → 2 s wait → SIGKILL stragglers. Returns
     the killed-pid list; never raises.
   - `is_running()` at `:67` is correctly documented as a TCP-only
     probe. Readiness uses `_wait_ready()` polling `GET /doc` per
     A9. Both are exercised by `test_wait_ready_polls_doc_endpoint`
     and `test_wait_ready_timeout`.

5. **Provider-switch hook — PASS.**
   `app.py:1009-1017`:
   - Spawned in a `daemon=True` thread; the response at line 1018
     does NOT await the restart. ✓
   - `if _oc.is_running()` guards the restart — opencode is NOT
     spawned just because chat switched provider. ✓
   - Outer `try/except Exception: pass` catches *and silences*
     restart failures; the comment explicitly names "provider switch
     must succeed even if restart wiring breaks." Restart errors are
     logged inside `restart()` itself (e.g. `_log.warning(...)`),
     not leaked to the chat response. ✓
   - The `if "notebooks" in _visible_surfaces():` outer guard
     prevents min-tier callers from triggering any opencode code at
     all on the provider switch. Bonus.

6. **Workbench rename consistency — PASS.**
   - `_nav.html:48` — link text "Workbench". ✓
   - `notebooks.html:6` `<title>` — "Workbench". ✓
   - `notebooks.html:38` `<h1>` — "Workbench". ✓
   - The status JSON `name` fields for the existing three notebooks
     remain the per-notebook product names ("jupyter", "marimo",
     "open-notebook"); the *page* is Workbench, the *cards* keep
     their identities. Correct.
   - `_nav.html:5` keeps the legacy comment-string
     "dashboard | knowledge | notebooks | research | chat" — comment
     text only, not user-visible. Acceptable.

7. **127.0.0.1 hostname pinning (F-SEC-6) — PASS.**
   Hard-coded at `opencode.py:111` (`"--hostname", HOST` where
   `HOST = "127.0.0.1"` at line 31). No env override path. Test
   covers it at `test_opencode_service.py:184`.

8. **No httpx dep added — PASS.**
   `grep -n httpx pyproject.toml` returned no match. The readiness
   probe uses `requests` per A10.

9. **Test coverage for must-pass items — PASS.**

   | Must-pass item             | Test                                                                 |
   |---|---|
   | F-GATE-1, F-GATE-2          | `test_min_tier_404_all_three_routes` (parametrized over 3 routes)    |
   | F-GATE-3                    | `test_min_tier_no_side_effects` (asserts `activity_log.emit` not called) |
   | F-SEC-1                     | `test_max_tier_page_iframe_url_no_credentials` (regex + literal)     |
   | F-SEC-2                     | `test_compute_source_env_never_logged`                               |
   | F-SEC-3                     | `test_status_does_not_leak_token`                                    |
   | F-SEC-6                     | `test_start_command_pins_port_and_hostname`                          |
   | A1 (--port required)        | same test as F-SEC-6                                                 |
   | A9 (/doc readiness)         | `test_wait_ready_polls_doc_endpoint` + `test_wait_ready_timeout`     |
   | F-PROC-1                    | `test_wait_ready_timeout`                                            |
   | F-PROC-2                    | `test_start_returns_error_if_port_busy`                              |
   | F-PROC-4                    | `test_concurrent_restart_serializes`                                 |
   | F-PROC-6                    | `test_log_rotation_at_10mb`                                          |
   | F-RESTART-1                 | `test_provider_switch_succeeds_when_restart_fails` + `test_restart_after_provider_switch` |
   | F-RESTART-2                 | `test_restart_picks_up_new_env`                                      |
   | F-INSTALL-3                 | `test_install_hint_per_platform` (parametrized darwin/linux/wsl/windows) |
   | F-CONFIG-1                  | `test_compute_source_env_my_machine_default_base`                    |
   | F-CONFIG-2                  | `test_compute_source_env_cloud_no_token`                             |
   | F-IFRAME-2                  | `test_max_tier_page_csp_allows_iframe`                               |

   Every must-pass row has a green test. No gaps.

10. **Pre-existing failures untouched — PASS.**
    `git diff --name-only c7eaf48^ 14fba3b -- tests/` returns only
    the three new opencode test files plus `tests/portal/__init__.py`.
    None of the 5 reported failing test files (test_toast_ui,
    test_chat_ui, test_drafter, test_buddy_suggesters) appear in the
    diff. Builder's "pre-existing" claim verified.

---

## Test coverage assessment

41 new tests (16 unit / 17 integration / 8 lifecycle), all green per
BUILD_LOG.md. Every failure-mode row from §Failure modes that has a
"Test:" entry in §Detection has a corresponding test, named above.
Coverage on changed lines was not measured (no coverage tool wired
into this repo's suite), but spot-reading the module shows every
public function and every error branch reachable from the test set.

Gaps (acceptable):

- F-PROC-3 (orphan child on portal crash) — explicitly deferred
  per ARCHITECTURE.md §Deferred. Same posture as Jupyter today.
- F-SEC-4 (token in opencode's own subprocess logs) — deferred,
  outside our control.
- F-INSTALL-2 (binary too old) — deferred.

These are all in the "Deferred to Sprint 2" list in ARCHITECTURE.md
and are not new debt.

---

## Performance assessment

Not applicable. opencode is interactive, not throughput. No hot path.

---

## Tech debt delta

Matches ARCHITECTURE.md §Tech debt prediction. Two micro-items
observed that could be folded into a future cleanup pass (`start` /
`_start_inner` duplication; `lsof` triple-call in `_stop_unlocked`)
but neither was unanticipated — both are direct consequences of the
"avoid re-entrant lock acquisition" decision the architect specified.
Net debt: as predicted, slightly negative (proxy-shaped debt avoided).

---

## Required actions before merge

None. Ship it.

Optional follow-ups (file as Sprint 2 candidates, not gating):

1. Refactor `start()` / `_start_inner()` to share a single `_do_start`
   helper to eliminate the ~25 lines of duplicated body.
2. Collapse the three `lsof -ti` shell-outs in `_stop_unlocked()`
   into a single bounded poll.
3. Address the §Deferred list (F-PROC-3 process supervision,
   F-SEC-4 token redaction, F-INSTALL-2 version probe, PRIVACY.md
   trust-model note) when the Workbench surface graduates from
   "blueprint surface" to "documented operator workflow."
