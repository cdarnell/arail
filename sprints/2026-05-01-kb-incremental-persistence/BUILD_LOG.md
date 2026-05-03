# Build log: KB incremental persistence

**Architecture:** [ARCHITECTURE.md](./ARCHITECTURE.md) at commit `4de4de1`
**Started:** 2026-05-01

## Plan

| # | Files | Change | Test | Commit ref |
|---|---|---|---|---|
| 1 | `sprints/2026-05-01-kb-incremental-persistence/BUILD_LOG.md` | Build log skeleton (this file) | — | — |
| 2 | `src/arail/pkb_index.py` | New module: `ensure_ready`, `schedule_upsert`, `_flush`, threading.Lock/Timer, merge_insert + delete fallback | test-first (unit) | — |
| 3 | `src/arail/pkb.py` | Widen `index_all` rows to include `mtime` + `source_kind`; add `write_buddy_dream` helper | alongside | — |
| 4 | `src/arail/pkb.py` | Wire `schedule_upsert` shim into six existing write helpers + new `write_buddy_dream` | alongside | — |
| 5 | `src/arail/agents/_builtin_buddy.py` | Refactor `BuddyAgent.dream` to call `pkb.write_buddy_dream` instead of `target.write_text` | alongside | — |
| 6 | `src/arail/portal/app.py` | Call `pkb_index.ensure_ready()` from `_startup()` hook | alongside | — |
| 7 | `tests/test_pkb_index.py` | Unit tests: dedup, path normalization, path traversal, delete-on-missing, legacy schema triggers rebuild, compatible schema reuses, staleness sweep, lancedb-unavailable is silent | new | — |
| 8 | `tests/test_pkb_index_integration.py` | Integration tests: round-trip < 10s, restart durability, cold-start fallback, concurrent writes, hot-write during cold-start | new | — |
| 9 | `tests/test_pkb_index_perf.py` | Performance smoke tests: burst coalescing (50 upserts → 1 merge_insert), single-write latency p95 ≤ 4s | new | — |
| 10 | `tests/test_pkb.py` | Add regression test: regex fallback still works after changes; ensure `write_buddy_dream` appears in search | addition | — |
| 11 | `BUILD_LOG.md` | Final summary | — | — |

## Execution

### Step 1 — BUILD_LOG.md skeleton
Commit: (this file, staged next)

## Spec issues
(none — plan is clean, proceeding to implementation)

## Architect feedback required
(empty)

## Final state
(to be filled at close)
