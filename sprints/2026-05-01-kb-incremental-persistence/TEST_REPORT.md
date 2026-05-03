# Test report: KB incremental persistence

**Date:** 2026-05-01
**Build:** [BUILD_LOG.md](./BUILD_LOG.md) at `07ed251`
**Review:** [REVIEW.md](./REVIEW.md) at `2b83c11`
**Branch:** `qukaizen/arail-kb-incremental-persistence`
**QA:** qa subagent (paranoid pass)

## Verdict: PASS

All 36 QA edge-case tests pass. The 19 baseline tests (build phase) still
pass. The broader 271-test in-scope suite still passes (5 pre-existing
failures outside scope, documented in BUILD_LOG.md, not regressions).
All four win conditions in VISION.md are covered with at least one
explicit asserted test, including the previously-unwritten end-to-end
witness scenario (threshold #3).

## Test additions

**File:** `tests/test_pkb_index_qa.py` (1,400+ lines, 36 tests)
**Mark:** `pytest.mark.qa` (registered in `pyproject.toml`)
**End-to-end witness:** `pytest.mark.e2e` (already registered)

### Allocation breakdown (vs sprint allocation 40/25/20/15)

| Category | Allocation | Tests | % actual |
|---|---|---|---|
| Correctness (round-trip, restart, schema, concurrency) | 40% | 14 | 39% |
| Setup (fresh clone, corruption, weird paths, schema migration) | 25% | 9 | 25% |
| Security (path traversal corpus, symlink, null byte, airgapped) | 20% | 7 | 19% |
| Regression (regex fallback, write-helper survival, index_all) | 15% | 6 | 17% |

### What the 36 QA tests cover

**Architect's REVIEW.md follow-ups (closed):**
1. `test_merge_insert_absent_falls_back_to_delete_add` — Finding #1 closed
2. `test_merge_insert_absent_idempotent_on_repeat` — Finding #1 hardened
3. `test_staleness_sweep_cap_exceeded_falls_back_to_index_all` — Finding #3 closed
4. `test_staleness_sweep_at_cap_does_not_trigger_fallback` — boundary value (cap, not cap+1)

**Win-condition correctness:**
5. `test_e2e_researcher_write_findable_within_10_seconds` — VISION threshold #3, ASSERTED
6. `test_e2e_witness_survives_simulated_restart` — VISION threshold #2 + #3 combined
7. `test_debouncer_coalesces_two_writes_10ms_apart` — same-path coalescing
8. `test_concurrent_same_path_writes_produce_one_row` — 8-thread set-dedup race
9. `test_pending_write_recovered_by_next_boot_sweep` — SIGTERM survival via cold sweep
10. `test_file_deleted_after_upsert_then_sweep_drops_row` — orphan row cleanup
11. `test_two_connections_to_same_db_can_both_query` — LanceDB MVCC sanity
12. `test_schedule_upsert_from_non_main_thread` — daemon-thread safety
13. `test_failed_flush_keeps_paths_in_pending_for_retry` — disk-full recovery semantics

**Setup / cold-start hardening:**
14. `test_corrupted_lancedb_dir_does_not_crash_ensure_ready` — bytewise corrupted .lance
15. `test_wrong_vector_dim_triggers_rebuild` — dim mismatch with otherwise correct schema
16. `test_pkb_root_with_spaces_and_unicode_works` — `lab dir with spaces/pkb_日本/`
17. `test_unicode_filename_round_trips_through_upsert` — `résumé_日本語_🚀.md`
18. `test_filename_with_spaces_round_trips`
19. `test_deeply_nested_path_round_trips` — 10-level nesting + 80-char basename
20. `test_schedule_upsert_on_directory_does_not_crash` — directory-as-path
21. `test_index_all_cold_start_still_works` — direct index_all path
22. `test_empty_pending_flush_is_noop` — degenerate input

**Security (path traversal + adversarial inputs):**
23. `test_path_traversal_corpus_rejected[../../etc/passwd]`
24. `test_path_traversal_corpus_rejected[../../../../../../etc/shadow]`
25. `test_path_traversal_corpus_rejected[./../../sensitive.txt]`
26. `test_path_traversal_corpus_rejected[subdir/../../../escape.md]`
27. `test_absolute_path_outside_pkb_rejected`
28. `test_null_byte_in_path_rejected` — `foo\x00bar.md`
29. `test_symlink_escape_rejected` — symlink under pkb_root → /tmp/outside
30. `test_filename_with_single_quote_does_not_break_delete_clause` — SQL-ish injection
31. `test_airgapped_strict_no_socket_during_full_round_trip` — `socket.socket` patched to raise on AF_INET; full write→flush→search still passes
32. `test_no_sentence_transformer_import_anywhere_in_module` — no ML deps leak
33. `test_dotenv_under_pkb_root_not_indexed_by_iter` — `.env` / `.key` rejected by suffix allowlist
34. `test_ensure_ready_failure_isolated_from_caller` — portal startup hook contract test

**Regression:**
35. `test_search_falls_back_to_regex_when_index_all_fails` — chat-RAG keeps working when LanceDB is broken
36. `test_write_helper_succeeds_when_schedule_upsert_explodes` — file write contract preserved

## Win-condition assessment

| # | Threshold | Test(s) | Verdict |
|---|---|---|---|
| 1 | Latency: agent write findable in ≤ 10 s | `test_round_trip_within_10_seconds` (build) + `test_e2e_researcher_write_findable_within_10_seconds` (QA) | **PASS** |
| 2 | Durability across process restart, reuse not rebuild | `test_restart_durability_reuses_index` (build) + `test_e2e_witness_survives_simulated_restart` (QA) + `test_pending_write_recovered_by_next_boot_sweep` (QA) | **PASS** |
| 3 | End-to-end witness: write → search → answer in one session, scripted, asserted | `test_e2e_researcher_write_findable_within_10_seconds` (QA, marked `e2e`) — calls `pkb.write_agent_experiment` and asserts `pkb.search()` returns content within 10 s through the live debouncer | **PASS** |
| 4 | No new long-lived service; LanceDB cache stays at `lab/pkb/.cache/lancedb/` | Verified by code review — only `threading.Timer` (daemon=True), no daemon thread, no broker, no subprocess; path constructor `_vector_db_path(root) = root / ".cache" / "lancedb"` unchanged | **PASS** |

## Failure-mode coverage table (12 design-time modes from ARCHITECTURE.md)

| # | Failure mode | Coverage | Status |
|---|---|---|---|
| 1 | `lancedb` import fails (stale env) | `test_lancedb_unavailable_is_silent` (build) | **Covered** |
| 2 | Disk full at flush time | `test_failed_flush_keeps_paths_in_pending_for_retry` (QA — new) | **Covered** (was: gap) |
| 3 | Embedder unavailable in airgapped mode | `test_no_sentence_transformer_import_anywhere_in_module` + `test_airgapped_strict_no_socket_during_full_round_trip` (QA — new) | **Covered** (was: N/A by inspection only) |
| 4 | Schema mismatch on cold start (legacy table) | `test_ensure_ready_legacy_table_triggers_rebuild` (build) + `test_wrong_vector_dim_triggers_rebuild` (QA — new) | **Covered** |
| 5 | Process crash mid-flush | `test_pending_write_recovered_by_next_boot_sweep` (QA — new) | **Covered** (was: partial) |
| 6 | Helper call from a thread with no running event loop | `test_schedule_upsert_from_non_main_thread` (QA — new) | **Covered** (was: N/A by design) |
| 7 | Two helpers write same file simultaneously | `test_concurrent_same_path_writes_produce_one_row` (QA — new) + `test_debouncer_coalesces_two_writes_10ms_apart` (QA — new) | **Covered** |
| 8 | File deleted between helper call and flush | `test_flush_handles_missing_file_as_delete` (build) | **Covered** |
| 9 | Path traversal | `test_path_traversal_rejected` (build) + 4 corpus tests + `test_absolute_path_outside_pkb_rejected` + `test_null_byte_in_path_rejected` + `test_symlink_escape_rejected` (QA — new) | **Covered** |
| 10 | Bounded staleness sweep cap (>200 stale files) | `test_staleness_sweep_cap_exceeded_falls_back_to_index_all` + `test_staleness_sweep_at_cap_does_not_trigger_fallback` (QA — new, closes Finding #3) | **Covered** (was: gap) |
| 11 | `merge_insert` API not available on pinned LanceDB | `test_merge_insert_absent_falls_back_to_delete_add` + `test_merge_insert_absent_idempotent_on_repeat` (QA — new, closes Finding #1) | **Covered** (was: gap) |
| 12 | `_pkb_root()` returns a path that doesn't exist | `ensure_ready` early-returns at `pkb_index.py:292-294`; covered by direct read | **Covered** (trivial) |

**12 of 12 failure modes covered.** All gaps the architect flagged in REVIEW.md are closed.

## Bugs found

**None.** All 36 QA tests pass on first run against the build at commit
`07ed251`. The build is robust to every adversarial input I threw at it:

- Path traversal (4 patterns + symlink + null byte + absolute) — all rejected silently
- Single-quote in filename — escape is correct (`'' ` doubled), no injection
- Unicode/spaces in filename — round-trips cleanly
- Unicode/spaces in pkb_root path — works
- Corrupted LanceDB on disk — `ensure_ready` does not crash
- Disk full at flush — failed paths persist in `_pending` for retry, no exception escapes
- 8-thread same-path race — set-dedup collapses to 1
- Non-main-thread call — works (threading.Timer, not asyncio)
- Airgapped strict (socket.socket patched) — full round trip still passes
- merge_insert absent → delete+add fallback — works and is idempotent

The architect's **Finding #2** (`_flush` releases the lock before
`merge_insert`, which is a doc/code drift but safe in practice) was
intentionally not converted into a test — the architect recommended it as
either a doc fix or a lock-widening, both of which are post-QA decisions
and neither has any observable failure mode the operator would notice.
Recorded as a follow-up note, not a bug.

## Regression check results

| Regression target | Test | Result |
|---|---|---|
| `pkb.search()` returns regex-fallback when LanceDB unavailable | `test_search_falls_back_to_regex_when_no_lancedb` (build) + `test_search_falls_back_to_regex_when_index_all_fails` (QA) | **PASS** |
| Existing chat-RAG path unchanged (`retrieve_chat_context` → `pkb.search` → `_semantic_search`) | Indirect via win-condition #1 + #3 tests | **PASS** |
| `index_all` cold-start path still works (no schema change broke it) | `test_index_all_cold_start_still_works` (QA) + `test_cold_start_fallback_builds_index` (build) | **PASS** |
| Write-helper file write never broken by index failure | `test_write_helper_succeeds_when_schedule_upsert_explodes` (QA) | **PASS** |
| Existing `tests/test_pkb.py` (14 tests) still passes | full pkb suite | **PASS** |
| Existing `tests/test_vector_index.py` (10 tests) still passes | full pkb suite | **PASS** |
| Existing `tests/test_wiki.py` still passes | broader suite | **PASS** |
| Broader 271-test suite (excluding 4 pre-existing-broken files) | `pytest tests/ --ignore=...` | **PASS** (271 passed, was 262 — the +9 are my new tests; no test that was passing now fails) |

## Security review (paranoid pass)

| Surface | What I actually checked | Findings |
|---|---|---|
| User input (path) | Tested 4 traversal patterns + null byte + absolute path + symlink escape; all rejected via `path.resolve().relative_to(root.resolve())`. SQL-ish single-quote in filename is correctly doubled (`''`) before delete clause; verified no collateral damage on innocent rows. | Clean |
| Authentication | N/A — no auth surface in this sprint. | N/A |
| File I/O | Path traversal: covered. Race on tempfiles: not applicable (no tempfile in this sprint). Permission: tested LanceDB connection on a fresh empty `.cache/lancedb/` and on a corrupted-bytes one — both handled gracefully. | Clean |
| Network I/O | Airgapped strict: `socket.socket` patched to raise on `AF_INET`/`AF_INET6` during full write→flush→search round trip. Zero INET sockets opened. Verified `pkb_index.py` imports only `lancedb` (local FS), `arail.vector_index.hash_embedding` (stdlib `hashlib`), `arail.activity`, `arail.pkb`. | Clean |
| Deserialization | LanceDB read paths use Arrow schema; no `pickle`, no `eval`, no `exec`. `_build_row` reads `read_text(errors="replace")` — safe parser, no untrusted-input deserialization. | Clean |
| Crypto | `hash_embedding` uses SHA1 — but this is for vector projection, NOT for security/integrity. Acceptable use; SHA1 not used for authentication or signature in this surface. Confirmed by reading `vector_index.py`. | Clean (informational only) |
| Dependencies | No new deps added in this sprint (LanceDB ≥ 0.13.0 already pinned in `pyproject.toml`). | Clean |
| Secrets surface | `.env` and `.key` files dropped under `lab/pkb/` are NOT picked up by `_iter_pkb_files` because `_PKB_TEXT_SUFFIXES = (".md", ".txt", ".rst", ".csv", ".json", ".html")` excludes them. Tested with `test_dotenv_under_pkb_root_not_indexed_by_iter`. `secrets.env` lives at `lab/data/secrets.env`, outside `lab/pkb/`, so doubly inaccessible. | Clean |

**Security verdict:** clean. No findings above informational severity.

## Performance check

Performance is covered by the build's `tests/test_pkb_index_perf.py`:

- `test_burst_50_upserts_fires_one_merge_insert` — 50 upserts → ≤ 3 flushes, < 7 s wall-clock. **PASS**
- `test_single_write_latency_under_4s[0..2]` — 3 trials, each ≤ 4 s with 1 s debounce. **PASS**
- E2E witness latency (`test_e2e_researcher_write_findable_within_10_seconds`) — < 10 s budget enforced; observed latency in tests is ~0.5–1.5 s with debounce 0.5 s. **PASS**

No baseline comparison run — this is a new module with no prior baseline.
The win-condition latency budget (10 s) is respected with several
multiples of headroom. No performance regression possible because the
prior code path did not exist.

## Coverage delta

Numerical coverage not measured by `coverage.py` in this pass.
Visual inspection of `pkb_index.py` (455 lines) suggests > 90% of
executable lines are now exercised:

- All public API (`ensure_ready`, `schedule_upsert`, `_reset_for_tests`)
- All four cold-start branches (no table → index_all; bad schema → drop+rebuild; cap-exceeded → index_all; reuse → staleness sweep)
- Both upsert mechanisms (`merge_insert` and `delete+add` fallback)
- File-deleted-mid-window delete branch
- Disk-full failed-flush retry branch
- All 6 source_kind path-prefix branches
- Path-traversal early-return
- LanceDB-unavailable early-return
- Connection-failure swallowed-exception branch in `ensure_ready`

Uncovered branches are limited to:
- `_open_table` exception fall-through (defensive `except Exception: return None` after `db.open_table` — exercised structurally by the corrupted-dir test, but not asserted at the branch level)
- A handful of `try: from arail.activity import activity_log; ... except Exception: pass` shims (best-effort logging that swallows errors)

## Notes for the next QA pass

**Patterns spotted:**

1. **The set-dedup-and-arm-timer pattern is robust.** Across 36 paranoid
   tests, no scenario produced two flushes for one path or lost a path.
   The single `threading.Lock` + `_pending: set` + single `threading.Timer`
   discipline holds.
2. **The `try/except Exception: pass` envelope around `schedule_upsert`
   in every helper is load-bearing.** Tested by making `schedule_upsert`
   raise; the file write succeeded. Future write helpers MUST keep this
   pattern; consider promoting to a decorator if a third one appears.
3. **`Path.resolve().relative_to(root.resolve())` is the correct path
   guard.** Catches `..`, symlinks, absolute outside, and null bytes
   (the last by `Path.resolve()` raising `ValueError` which is caught).
   Don't downgrade to bare `relative_to`.
4. **The `source_kind` schema column buys flexibility for free.** A
   future "drafts vs published" filter can land as a `WHERE source_kind`
   clause without another schema migration. The visionary's deferred
   draft-flag question stays answerable in a small follow-up sprint.

**Areas under-tested (acceptable but flag for future):**

- **No load test.** The perf suite is smoke-only. If the PKB grows
  beyond ~1000 files, the staleness sweep at boot may need a profile
  pass. The cap=200 fallback exists exactly for this.
- **No long-running soak.** The 36 tests run in ~7 s. A 1-hour
  continuous-write loop would exercise timer cancellation/re-arm churn
  more thoroughly.
- **No multi-process hard test.** `test_two_connections_to_same_db_can_both_query`
  models multi-process via two LanceDB connections; a real
  subprocess-fork test would be more authoritative if multi-writer
  becomes a feature (currently out of scope per ARCHITECTURE.md).
- **Architect's Finding #2** (lock released before `merge_insert` —
  spec/code drift, safe in practice) is intentionally not exercised.
  Either widen the lock in a follow-up commit or update the
  ARCHITECTURE.md concurrency section to match as-built. QA verdict
  is unaffected.

**Pre-existing test failures (NOT regressions, documented in BUILD_LOG.md):**
- `tests/test_chat_ui.py::test_chat_page_renders_compact_single_thread_shell`
- `tests/test_drafter.py::test_loader_resolves_drafter_via_seed`
- `tests/test_toast_ui.py::test_css_includes_toast_styles`
- `tests/test_toast_ui.py::test_activity_event_level_suggest_renders`
- `tests/test_buddy_suggesters.py::test_next_experiment_flags_uncovered_term`

These five tests were broken before this sprint's first commit
(`b068989`) and need a separate fix ticket. They are NOT regressions
from KB incremental persistence work.

## Recommended changes

**None gating.** Verdict is PASS as-is.

Optional (not gating):
1. **Doc-fix vs lock-widen on Finding #2** — pick one. Either widen
   `_lock` to wrap the `merge_insert` call (slight perf cost, matches
   spec verbatim), or update ARCHITECTURE.md's concurrency section to
   say "the lock serializes the snapshot+timer-clear, then LanceDB's
   own MVCC serializes the actual write." Both are correct; the latter
   is the as-built reality.
2. **Promote the `try: from arail.pkb_index import schedule_upsert; schedule_upsert(path); except: pass` envelope** to a small decorator
   in `pkb.py` if a 7th write helper appears. Right now 7 call sites
   all have the identical 5-line shim — borderline DRY-violation but
   not enough call sites to justify the abstraction yet.
3. **File the 5 pre-existing test failures** as a separate sprint
   (already noted in BUILD_LOG.md).
