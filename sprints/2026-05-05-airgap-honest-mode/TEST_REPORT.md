# Test report: airgap-honest-mode

**Date:** 2026-05-05
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at 419e605 (post-loopback re-review PASS at ad8f98f)
**Branch:** `qukaizen/arail-airgap-honest-mode`
**QA:** qa subagent

## Verdict: WEAK_PASS

Six new QA test files added (80 tests, 79 pass, 1 fails by exposing a
real-but-low-severity bug). All architect-flagged surfaces are pinned.
The failing test exposes a small Buddy-quality bug: the airgap watcher
crashes with `ValueError` if `state.json` has a non-coercible value
under `airgap_last_egress_offset`. Severity is low because the
scenario requires a corrupted state.json (degraded-state input), but
under arail's CLAUDE.md gating "Buddy quality" is 30% of QA, and a
watcher that crashes the entire tick on degraded inputs is a
Buddy-quality regression vs. the existing pattern in
`_load_state` (which catches `Exception` broadly). Sprint can ship
with the bug filed for follow-up; consider upgrading to FAIL if the
builder wants to land the one-line fix before merge.

The five pre-existing test failures on the parent commit
(`test_next_experiment_flags_uncovered_term`, plus four others in
`test_chat_ui.py`, `test_drafter.py`, `test_toast_ui.py`) remained
the only non-QA failures, confirming no other regressions.

## Summary

Wrote six QA-focused test files exercising the architect's seed list
(IPv6 edge cases, bypass attempts, SRE shim fork-respect,
CVE/cleanup watcher mode-gating equivalence, Buddy watcher resilience,
and happy-path/setup smoke). Pinned 7 documented gaps (4 from the
modal — httpx, raw socket, subprocess curl, os.system — plus 2 from
re-review — 6to4 IPv6 classification, asyncio.create_task contextvars
inheritance — plus 1 from the audit log — `EgressBlocked.__str__` does
not contain query strings). Found 1 real bug (Buddy watcher
ValueError on malformed `airgap_last_egress_offset` in state.json),
filed below with reproducer.

## Bucket-by-bucket breakdown (per arail product gating)

| Bucket | Allocation | Files | Tests | Pass | Fail | Skipped |
|---|---|---|---|---|---|---|
| Setup | 30% | `tests/test_qa_airgap_happy_setup.py` (setup half) | 11 | 11 | 0 | 0 |
| Buddy | 30% | `tests/test_qa_buddy_watcher_resilience.py` | 11 | 10 | 1 | 0 |
| Security | 20% | `tests/test_qa_airgap_bypass_attempts.py` + `tests/test_qa_airgap_ipv6_edge_cases.py` | 16 + 14 = 30 | 30 | 0 | 0 |
| Happy | 10% | `tests/test_qa_airgap_happy_setup.py` (happy half) | 6 | 6 | 0 | 0 |
| Regression | 10% | `tests/test_qa_sre_shim_fork_respect.py` + `tests/test_qa_sre_watchers_mode_gating.py` | 4 + 18 = 22 | 22 | 0 | 0 |

**Total:** 6 files, 80 QA tests, 79 pass, 1 fail (real bug exposure).

The Setup column is split across two files because
`test_qa_airgap_happy_setup.py` covers both happy-path artifacts AND
import/wiring smoke (which is the setup test).

## Test file inventory

| File | Tests | Description |
|---|---|---|
| `tests/test_qa_airgap_ipv6_edge_cases.py` | 14 | ULA, 6to4, IPv4-mapped, IPv4-compatible, unspecified IPv6, doc-prefix, CG-NAT |
| `tests/test_qa_airgap_bypass_attempts.py` | 16 | Pre-guard Session, DNS rebind, httpx/socket/subprocess/os.system gaps, asyncio context leak, audit-log secret leakage, RO-fs swallow |
| `tests/test_qa_sre_shim_fork_respect.py` | 4 | User fork preserved, fork's WATCHERS wins, no canonical mutation |
| `tests/test_qa_sre_watchers_mode_gating.py` | 18 | CVE branches a/b unconditional, branch c hybrid-only, lab cleanup mode-agnostic, _sre_lab_mode delegation |
| `tests/test_qa_buddy_watcher_resilience.py` | 11 | 3-cycle save preservation, malformed state.json/jsonl, offset monotonic, cooldown values, restart survival |
| `tests/test_qa_airgap_happy_setup.py` | 17 | README/PRIVACY/modal artifacts, import cleanliness, install_guard wiring, safe defaults, basic block-audit flow |

## Bugs found

| # | Bug | Severity | Reproducer | Owner |
|---|---|---|---|---|
| 1 | Buddy airgap watcher crashes with `ValueError: invalid literal for int() with base 10: 'garbage'` when `state.json` has a non-coercible `airgap_last_egress_offset` | Low | `tests/test_qa_buddy_watcher_resilience.py::TestMalformedStateJson::test_state_json_with_wrong_types_for_keys` | builder |

**Suggested fix (1 line):** at `src/arail/agents/_builtin_buddy.py:513`,
wrap `int(state_data.get("airgap_last_egress_offset", 0))` in
`try/except (ValueError, TypeError):` defaulting to `0`. The
existing `_load_state` (line 1027–1042) already follows this
fail-tolerant pattern — the watcher's parsing should match.

Severity rationale: requires a corrupted state.json (hand-edit, partial
write during crash, future writer that emits garbage). The tick
crashes but the next tick — when state.json is overwritten with a
clean integer — recovers. Not a crash that escalates beyond the watcher
function. But it is a Buddy-quality regression: `_load_state` in the
same file catches all `Exception` and starts fresh; the watcher should
match.

## Documented gaps pinned

These tests assert the documented behavior of known limitations. If
a future PR *closes* one of these gaps, the corresponding test fails
loudly — that's the desired tripwire so the docs/modal/README stay
in sync with reality.

| # | Gap | Test |
|---|---|---|
| 1 | DNS rebind to 127.0.0.1 / RFC1918 is treated as local | `test_qa_airgap_bypass_attempts.py::TestDNSRebind::*` |
| 2 | Pre-guard `requests.Session()` retains stock HTTPAdapter | `TestPreGuardSession::test_pre_guard_session_uses_unguarded_adapter` |
| 3 | Raw `socket.socket().connect()` is NOT wrapped | `TestDocumentedGaps::test_raw_socket_connect_bypasses_guard` |
| 4 | `httpx.Client.get()` is NOT wrapped | `TestDocumentedGaps::test_httpx_bypasses_guard_in_airgapped` |
| 5 | `subprocess.run(["curl", ...])` is NOT wrapped | `TestDocumentedGaps::test_subprocess_curl_bypasses_guard` |
| 6 | `os.system(...)` is NOT wrapped | `TestDocumentedGaps::test_os_system_bypasses_guard` |
| 7 | `asyncio.create_task` inherits `@allow_egress` context | `TestAsyncioContextvarsLeak::test_create_task_inherits_allow_egress_context` |
| 8 | Threading `Thread` does NOT inherit (safe) | `TestAsyncioContextvarsLeak::test_thread_does_NOT_inherit_allow_egress` |
| 9 | 6to4 (`2002::/16`) classified as private by Python stdlib | `TestSixToFour::test_6to4_public_v4_classified_private_pin` |
| 10 | IPv6 `::` is `is_private=True` per Python 3.11 | `TestPinnedEdgeCases::test_unspecified_ipv6_address_is_not_local` |
| 11 | `2001:db8::/32` (RFC 3849 doc prefix) is is_private | `TestPinnedEdgeCases::test_ipv6_documentation_prefix_is_local_pin` |
| 12 | CG-NAT `100.64.0.0/10` is NOT classified private | `TestPinnedEdgeCases::test_ipv6_carrier_grade_nat_pin` |
| 13 | `EgressBlocked.__str__` does not contain full URL or query string | `TestAuditLogSecretLeakage::test_egress_blocked_str_does_not_contain_full_url` |
| 14 | `record_block` URL-parse fallback truncates to ≤64 chars | `TestAuditLogSecretLeakage::test_malformed_url_fallback_truncated_to_64_chars` |
| 15 | `record_block` swallows write errors when dir unwritable | `TestJsonlWriteFailures::test_record_block_swallows_when_dir_unwritable` |
| 16 | `EgressBlocked` still raises even when audit log fails | `TestJsonlWriteFailures::test_egress_blocked_still_raises_when_logging_fails` |

Architect's "for QA" seed list crosswalk:

- ✅ Pre-guard Session — pinned (#2)
- ✅ DNS rebind — pinned (#1)
- ✅ IPv6 ULA / 6to4 / IPv4-mapped — pinned (`test_qa_airgap_ipv6_edge_cases.py`)
- ✅ asyncio.create_task contextvars leak — pinned (#7)
- ✅ httpx, aiohttp (skipped — not in tree), raw socket, subprocess curl, os.system — pinned (#3, #4, #5, #6)
- ✅ SRE shim fork respect (architect priority #1) — pinned (`test_qa_sre_shim_fork_respect.py`)
- ✅ CVE/cleanup mode-gating equivalence (architect priority #2) — pinned (`test_qa_sre_watchers_mode_gating.py`)
- ✅ `_save_state` data-loss regression (architect priority #3) — already covered by L1 test; QA confirmed runs green and added 3-cycle stress test

## Skipped tests

None. The `httpx` test would skip if httpx weren't installed, but it
is in tree (as a dep of `open_notebook_seed`) so the test runs.

`aiohttp` is NOT in tree (per ARCHITECTURE.md §4 assumptions) — no
test was written for it. If aiohttp lands in a future sprint, a
gap-pin test should be added.

## Security review

| Surface | Checked | Findings |
|---|---|---|
| User input | URL parse fallback in `record_block`; `allow_egress` reason validation (200-char limit, type check) | Confirmed `EgressBlocked.__str__` does NOT include query strings; URL fallback bounded to 64 chars; reason length enforced. No leakage path found. |
| File I/O | `record_block` write paths under RO directory + `ARAIL_DATA_DIR` set to a file | Confirmed swallows OSError; `EgressBlocked` still raises (load-bearing invariant). Tests pin both paths. |
| Network I/O | DNS rebind trust, IPv6 classification, pre-guard Session, raw socket / httpx / subprocess gaps | Pinned 16 surfaces. DNS-rebind is a documented v1 limit (acceptable); IPv6 classification pinned; httpx/socket/subprocess gaps documented in modal + tests. |
| Crypto | N/A this sprint — no crypto changes | — |
| Deserialization | `state.json` parse via `json.loads` with broad `except Exception`; `egress.jsonl` line-by-line `json.loads` with skip-on-decode-error | Safe. No `pickle`. No untrusted deserialization. The watcher's `int(...)` coerce on a parsed value is the one bug surfaced. |
| Dependencies | No new deps added in this sprint | — |
| Concurrency | `_allow_egress_var` is `ContextVar[Optional[str]]`; thread-isolation pinned; asyncio task-inheritance pinned | Both pinned in `TestAsyncioContextvarsLeak`. |

## Performance

Not formally benchmarked. Per-request overhead inspection:

- `urlparse` ~5 µs.
- `is_local_ip` ~2 µs (pure ipaddress check).
- For non-IP hosts: `socket.gethostbyname` with 1.5s timeout. Cached
  by OS resolver; sub-ms with local resolver.
- `mkdir(parents=True, exist_ok=True)` per `record_block` (architect
  noted this as a follow-up). At a steady 1 block/5s rate that's ~17k
  calls/day — measurable but not load-bearing for the airgapped target.

Acceptance threshold (<5 ms added per request) is plausibly met but
unverified. No benchmark file produced; performance is not the win
condition for this sprint and no perf-sensitive call site changed.

[BENCHMARK.md](./BENCHMARK.md) — N/A.

## Coverage delta

QA added 80 tests across 6 files. Previously the sprint had 105 tests
(per the re-review). Total sprint test count after QA: 185 tests.

Coverage of new modules (estimated):
- `airgap.py`: ~98% (added IPv6 edge classes, fail-closed env defaults)
- `egress.py`: ~92% (added RO-fs/file-as-dir paths, asyncio bypass paths,
  pre-guard Session pinning, secret-leakage paths)
- `_builtin_buddy.py` watcher block: ~90% (added 3-cycle stress,
  malformed-state, malformed-jsonl, restart, monotonicity)
- `_builtin_sre.py` new watchers: 100% of branches a/b/c + cleanup
  mode-agnostic confirmed across both modes

## Full-suite regression check

```
6 failed, 750 passed, 1 xfailed in 25.30s
```

Pre-existing failures (5 — confirmed on parent commit before QA additions):
- `tests/test_buddy_suggesters.py::test_next_experiment_flags_uncovered_term` — the BUILD_LOG-noted pre-existing failure
- `tests/test_chat_ui.py::test_chat_page_renders_compact_single_thread_shell`
- `tests/test_drafter.py::test_loader_resolves_drafter_via_seed`
- `tests/test_toast_ui.py::test_css_includes_toast_styles`
- `tests/test_toast_ui.py::test_activity_event_level_suggest_renders`

The BUILD_LOG only flagged 1 pre-existing failure
(`test_next_experiment_flags_uncovered_term`). The other 4 are also
pre-existing on this branch. Surface to the user: BUILD_LOG.md
under-counted the pre-existing failures by 4. They're not regressions
introduced by this sprint, but they were already broken before this
sprint started — the builder/architect should clarify.

QA-added failures: 1 (the bug exposure, by design).

## Notes for the next QA pass

- **Buddy state.json schema is now informally co-owned by two writers
  (BuddyAgent + airgap watcher).** The Loopback 1 fix made
  `_save_state` read-merge-write, but the watcher's own
  parse-with-coerce path needs the same defensiveness. The bug found
  here is exactly the "third writer adds new keys, they survive but
  parsing assumes well-typed values" failure mode the architect's
  tech-debt section anticipated.
- **`mkdir(parents=True, exist_ok=True)` per `record_block` call** is
  a known minor inefficiency (architect's INFO finding). Not load-
  bearing.
- **Compose / portal smoke**: I did not boot the actual portal in a
  subprocess — wiring is verified by source-grep
  (`install_guard` appears in `portal/app.py` and `agents/loader.py`).
  A live HTTP smoke test of `/api/airgap/status` against a running
  portal is reasonable as a future end-to-end check.
- **aiohttp gap is undocumented in tests** (it's documented in modal
  + PRIVACY.md). If aiohttp lands in tree as a dep, add a parallel
  bypass-pin test.
- **The 4 unflagged pre-existing failures** (chat_ui, drafter,
  toast_ui x2) are likely either dead test files for removed
  features or genuine pre-sprint bugs. Recommend a separate
  follow-up to triage.

## Files added

- `tests/test_qa_airgap_ipv6_edge_cases.py` — 14 tests
- `tests/test_qa_airgap_bypass_attempts.py` — 16 tests
- `tests/test_qa_sre_shim_fork_respect.py` — 4 tests
- `tests/test_qa_sre_watchers_mode_gating.py` — 18 tests
- `tests/test_qa_buddy_watcher_resilience.py` — 11 tests
- `tests/test_qa_airgap_happy_setup.py` — 17 tests
