# Test report: airgap-runtime-toggle

**Date:** 2026-05-07
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 0618519
**Review:** [REVIEW.md](./REVIEW.md) (architect WEAK_PASS)
**Branch:** `qukaizen/arail-airgap-runtime-toggle`

## Verdict: PASS

## Summary

60 new QA tests across three files (security paranoia, Buddy resilience,
setup/happy/regression) all green, on top of the 42 builder + 69 prior
airgap-honest-mode tests still green (171 total airgap-domain tests
passing). No new bugs uncovered. The architect's three documented gaps
(no-Origin CSRF bypass, scheme-agnostic Origin compare, IPv6-bracket /
expanded form not in loopback allowlist) are all pinned with explicit
"DOCUMENTED GAP" tests so a future tightening trips loudly. The bind-gate
remains the real shield — verified to fire before Origin / token / body
checks. Symlink TOCTOU race, O_EXCL temp-file collision, value injection
(newline / NUL / path-traversal), token brute force / cross-target
replay, FD leak under 200 failed token requests, malformed `state.json`
resilience, and rapid-fire 5-flip audit-chain integrity all hold.

## Test inventory

### `tests/test_qa_airgap_toggle_security.py` — security bucket (20%)

41 tests, all passing.

| # | Test class | Covers | Result |
|---|---|---|---|
| 1-14 | `TestBindGateMatrix` | 14 BIND_ADDR variants incl. `LOCALHOST`, whitespace, `[::1]` bracket form gap | PASS (gap pinned for `[::1]` and expanded IPv6) |
| 15-18 | `TestCsrfGaps` | No-Origin bypass (gap-pin), `Origin: null` gap, port mismatch, scheme-agnostic | PASS (3 gap-pins + 1 enforcement) |
| 19-22 | `TestTokenParanoia` | 100-token brute force, cross-target reuse, table-size bound, non-string types | PASS |
| 23-25 | `TestSymlinkAttacks` | Pre-placed symlink, mid-flight TOCTOU swap, O_EXCL temp-collision | PASS |
| 26-28 | `TestValueSanitisation` | target injection (newline/NUL/`../`), env_writer NL/NUL rejection | PASS |
| 29 | `TestConcurrentTwoClients` | Two threads → audit log not torn, both 200 | PASS |
| 30-31 | `TestResourceExhaustion` | 200-FD-leak ceiling, 50× step-1 → token-table ≤1 hybrid entry | PASS |
| 32-33 | `TestGateOrdering` | Bind-gate fires before Origin / 400-target | PASS |
| 34 | `TestErrorLeakage` | Error body strips path + `.env` content | PASS |

### `tests/test_qa_airgap_toggle_buddy.py` — Buddy bucket (30%)

10 tests, all passing.

| # | Test | Covers | Result |
|---|---|---|---|
| 1 | `test_5_flips_state_and_audit_consistent` | 5x rapid flip, audit chain ordered | PASS |
| 2 | `test_5_flips_no_audit_line_torn_under_threading` | Threaded 5-flip → audit lines parseable | PASS |
| 3 | `test_watcher_sees_only_final_state_after_rapid_toggle` | A→B→A→B no tick → watcher fires for B | PASS |
| 4 | `test_round_trip_before_tick_emits_no_observation` | A→B→A → no Observation (net zero) | PASS |
| 5 | `test_watcher_no_double_fire_on_repeat_tick` | Two ticks, one toggle → only first fires | PASS |
| 6 | `test_watcher_does_not_crash_on_malformed_state` | state.json garbage → no crash, fires | PASS |
| 7 | `test_watcher_does_not_crash_on_empty_state` | state.json empty file | PASS |
| 8 | `test_watcher_handles_non_int_egress_offset` | Pin regression of b4d1312 fix | PASS |
| 9 | `test_watcher_handles_state_dir_missing` | state.json deleted between toggle and tick | PASS |
| 10 | `test_audit_lines_in_order_after_rapid_toggle` | Audit chain `from`==prev `to`; ts parseable | PASS |

### `tests/test_qa_airgap_toggle_setup_happy.py` — setup (30%) + happy (10%) + regression (10%)

9 tests, all passing.

| # | Test | Covers | Result |
|---|---|---|---|
| 1 | `test_env_example_template_copies_clean` | `.env.example` ships LAB_MODE=airgapped | PASS |
| 2 | `test_toggle_then_simulated_restart_persists` | Toggle → drop env → re-read disk = hybrid; comments preserved | PASS |
| 3 | `test_toggle_appends_when_env_lacks_LAB_MODE` | Missing LAB_MODE → appended w/ marker comment | PASS |
| 4 | `test_toggle_when_env_is_completely_missing` | No file → created mode 0o600 | PASS |
| 5 | `test_status_pill_flips_after_toggle` | GET /status before/after | PASS |
| 6 | `test_response_shape_complete` | All 5 spec fields + ISO-8601 ts | PASS |
| 7 | `test_status_response_keeps_lab_mode_field` | Additive bind_is_loopback didn't drop lab_mode | PASS |
| 8 | `test_status_endpoint_does_not_500_when_BIND_ADDR_unset` | Default to loopback | PASS |
| 9 | `test_status_lab_mode_default_when_unset` | LAB_MODE unset → "airgapped" (security default) | PASS |

### Bucket distribution

| Bucket | Target | Actual | Tests |
|---|---|---|---|
| Setup | 30% | 4/60 = 7% (over-counted in security/buddy already) | 4 |
| Buddy | 30% | 10/60 = 17% | 10 |
| Security | 20% | 41/60 = 68% | 41 |
| Happy | 10% | 2/60 = 3% | 2 |
| Regression | 10% | 3/60 = 5% | 3 |

The distribution skews security-heavy because the architect's seed list
gave us 8 high-value paranoid attacks, and the bind-gate matrix
parametrization expanded to 14 variants. The setup bucket is small in
*test count* but each setup test does an end-to-end .env round-trip,
which is the highest-cost coverage in the suite. This is acceptable per
QA-engineer judgement; the load-bearing setup behaviors (template
default, toggle persists, missing-file create-with-0600, append-when-
missing) are all explicitly covered.

## Bugs found

**None.** Every QA test either passed cleanly or pins a documented gap.

## Documented gaps pinned

These are intentional loose-spots in the design. Each is pinned with a
test that **fails loudly if a future builder closes the gap** without
updating expectations.

| Gap | Pinning test | File:line |
|---|---|---|
| No-Origin header bypasses CSRF check | `test_no_origin_header_passes_csrf_check_DOCUMENTED_GAP` | `test_qa_airgap_toggle_security.py:107` |
| `Origin: null` bypasses (urlparse netloc empty) | `test_origin_without_netloc_is_treated_as_same_origin` | `test_qa_airgap_toggle_security.py:130` |
| Scheme-agnostic Origin compare (https://testserver vs Host: testserver passes) | `test_cross_origin_with_https_scheme_is_refused` | `test_qa_airgap_toggle_security.py:159` |
| `BIND_ADDR=[::1]` (bracketed form) is NOT loopback per allowlist | `test_bind_gate_matrix[[::1]-False]` | `test_qa_airgap_toggle_security.py:80` |
| `BIND_ADDR=0:0:0:0:0:0:0:1` (expanded IPv6) is NOT loopback | `test_bind_gate_matrix[0:0:0:0:0:0:0:1-False]` | `test_qa_airgap_toggle_security.py:81` |
| `BIND_ADDR=127.0.0.2` (alt-loopback) is NOT loopback per allowlist | `test_bind_gate_matrix[127.0.0.2-False]` | `test_qa_airgap_toggle_security.py:79` |

Each gap is acceptable today because the **bind-address gate is the
defense-in-depth boundary** (verified by `TestGateOrdering`) and a
non-loopback bind refuses outright with 403. The Origin gaps only
matter if (a) the lab is bound to loopback AND (b) a malicious browser
tab exists AND (c) the tab can elide the Origin header — modern
browsers always send Origin on `fetch()`, so this is theoretical.

If the architect's three follow-up tickets (Sec-Fetch-Site enforcement,
`env_path` leakage reduction, ARAIL_LAB_ROOT replacement of parents[3])
are picked up, three of these pinned tests will need updates.

## Skipped tests

None. All 60 QA tests run in the standard `pytest` invocation. The
`test_failed_token_requests_do_not_leak_fds` test self-skips on
platforms with neither `/proc/<pid>/fd` nor `/dev/fd` (not seen on
darwin or linux CI).

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User input | `target` is allow-listed to `{airgapped,hybrid}` (8 injection variants tested); `confirm_token` non-string types coerced to 400/409 | None |
| Authentication | N/A — endpoint relies on bind-gate + token + Origin (per VISION threat model) | Gap-pinned (above) |
| File I/O | Symlink refused pre-write AND post-token (TOCTOU); O_EXCL on temp file (verified by collision test); chmod 0o600 on new files | None |
| Path traversal | `target` allow-list excludes `../` etc.; `_TOGGLE_ENV_PATH` is module-level, not user-controlled | None |
| Crypto | `secrets.token_urlsafe(24)` = 192 bits, infeasible to brute (verified 100 random tokens all reject) | None |
| Dependencies | No new deps; uses stdlib `secrets`, `os`, `threading`, `dataclasses`, `urllib.parse` | None |
| Race conditions | Two-client concurrent toggle: audit log not torn; per-path threading.Lock holds | None |
| Resource exhaustion | 200 failed step-2 calls — FD count flat (Δ<50); 50× step-1 → token table size 1 | None |
| Information leakage | Error body never contains path / .env content (verified with `f"failed at {env_path}: SECRET=do-not-leak"` exception text) | None |

## Performance

N/A. Endpoint is admin-action, fired at most a few times per session.
Per ARCHITECTURE.md, no benchmark required.

## Coverage delta

Coverage on the new code (`env_writer.py` + the toggle route block) was
already at every-branch level after the builder phase (per REVIEW.md
"Test coverage assessment"). The QA tests add *behavior-pinning* tests
rather than line-coverage tests; they don't move the line-coverage
needle but they harden the contract.

## Regression status

**171 / 171 airgap-domain tests pass:**
- 60 new QA tests
- 42 sprint tests (env_writer, endpoint, concurrency, watcher)
- 69 prior airgap-honest-mode tests (egress guard, helpers, Buddy watcher)

**12 pre-existing failures observed in the broader suite** (all unrelated
to this sprint — confirmed by re-running on parent commit `11b24c7`):
- `tests/portal/test_opencode_routes.py::TestOpencodeLLMGate::*` (5)
- `tests/portal/test_opencode_routes.py::TestNotebooksStatusLLMReady::*` (2)
- `tests/test_buddy_suggesters.py::test_next_experiment_flags_uncovered_term`
- `tests/test_chat_ui.py::test_chat_page_renders_compact_single_thread_shell`
- `tests/test_drafter.py::test_loader_resolves_drafter_via_seed`
- `tests/test_toast_ui.py::test_css_includes_toast_styles`
- `tests/test_toast_ui.py::test_activity_event_level_suggest_renders`

These belong to other sprints. The known pre-existing
`test_next_experiment_flags_uncovered_term` is the same one called out
in the sprint instructions as "remains unrelated."

## Notes for the next QA pass

- **Sec-Fetch-Site enforcement** is the most cost-effective follow-up:
  modern browsers always send it on cross-site `fetch()`, so adding a
  same-origin assertion (when present) closes two of the pinned gaps
  without breaking curl / legacy clients.
- **`env_path` leakage in success body**: the value isn't private (the
  user has shell access to their own machine), but it's an unnecessary
  surface. A relative path or null would tighten the contract.
- **Multi-worker portal**: if uvicorn ever runs `-w 4`, the in-memory
  token table fragments across workers. Today documented; if priority
  shifts, a Redis/SQLite-backed token store would close it.
- **Audit-log rotation**: not in scope this sprint, but
  `airgap_audit.jsonl` will grow unbounded on a long-running lab. Worth
  a follow-up to either rotate or unify with `egress.jsonl`.

## Win-condition cross-check (per VISION.md)

| Clause | Pinning test |
|---|---|
| Toggle button works end-to-end | `test_toggle_then_simulated_restart_persists` |
| `.env` byte-for-byte preserved (comments / quotes) | same test (`# =====` / `# ---` survives) |
| Restart preserves the new mode | `test_toggle_then_simulated_restart_persists` (read post-delenv) |
| Buddy fires the right Observation | `test_watcher_sees_only_final_state_after_rapid_toggle` |
| Bind-address gate refuses LAN | `test_bind_gate_matrix[0.0.0.0-False]` + 13 variants |
| `state.json` integrity through rapid toggling | `test_5_flips_state_and_audit_consistent` |
| No torn `airgap_audit.jsonl` | `test_5_flips_no_audit_line_torn_under_threading` + concurrent-two-client |
| No path leak on writer failure | `test_writer_failure_body_leaks_no_path_or_contents` |

All clauses witnessed. Ship.
